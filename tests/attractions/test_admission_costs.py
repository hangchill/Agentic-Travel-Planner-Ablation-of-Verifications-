"""Admission fixtures are local; these tests prohibit HTTP requests."""
import csv
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.attractions import enrich_admission_costs as e


@pytest.fixture(autouse=True)
def forbid_network():
    with patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden during admission tests')):
        yield


@pytest.mark.parametrize('raw,fee,kind,exact,lo,hi', [
    ('$25', 'yes', 'fixed', '25', None, None),
    ('20.50 USD/person', 'yes', 'fixed', '20.50', None, None),
    ('USD 12', '', 'fixed', '12', None, None),
    ('0.00 USD', 'yes', 'variable', None, None, None),
    ('pay what you wish (minimum $5)', '', 'pay_what_you_wish', None, '5', None),
    ('', 'no', 'free', '0', None, None),
    ('', 'yes', 'paid_unknown', None, None, None),
    ('', '', 'unknown', None, None, None),
    ('$10–20', 'yes', 'range', None, '10', '20'),
    ('10-20 USD', '', 'range', None, '10', '20'),
    ('from $15', '', 'from', None, '15', None),
    ('varies', 'yes', 'variable', None, None, None),
    ('adult $30; child $10', 'yes', 'variable', None, None, None),
    ('pay what you wish', '', 'pay_what_you_wish', None, None, None),
    ('suggested donation $20', '', 'pay_what_you_wish', None, None, None),
    ('banana $20 maybe', '', 'unknown', None, None, None),
    ('20 EUR', 'yes', 'paid_unknown', None, None, None),
    ('$20', 'no', 'variable', None, None, None),
    ('$40–10', 'yes', 'paid_unknown', None, None, None),
    ('-5 USD', 'yes', 'paid_unknown', None, None, None),
    ('NaN USD', '', 'unknown', None, None, None),
])
def test_price_grammar(raw, fee, kind, exact, lo, hi):
    assert e.parse_price(raw, fee) == e.price(kind, exact, lo, hi)


def canonical(aid='ATTR_0001', name='Visitor Museum', lat='40.75', lon='-74'):
    return dict(attraction_id=aid, name=name, latitude=lat, longitude=lon,
                source='nyc_commonplace', source_id=aid, category='museum')


def external(source='osm', eid='node/1', parsed=None, **extra):
    return e.record(source, eid, 'Visitor Museum', 40.75, -74,
        'https://example.org/admission', '2026-10-11', '$25', parsed or e.price('fixed', '25'),
        admission_scope=True, **extra)


def test_unrelated_fee_and_private_access():
    for tags in [dict(amenity='parking', fee='no'), dict(amenity='toilets', charge='$5'),
                 dict(tourism='museum', fee='no', access='private')]:
        records = e.normalize_osm({'elements': [dict(type='node', id=1, lat=40.75, lon=-74, tags=tags)]}, '2026-10-11')
        assert records[0]['price'] == e.price()
        assert e.match_records([canonical()], records)[0]['match_status'] == 'REJECTED'


def test_conditional_not_globally_free():
    r = e.normalize_osm({'elements': [dict(type='node', id=1, tags={'tourism': 'museum', 'fee': 'no', 'fee:conditional': 'yes @ (events)'})]}, '2026-10-11')[0]
    assert r['price']['type'] == 'variable'


def test_match_requires_name_and_location():
    assert e.match_records([canonical()], [external()])[0]['match_status'] == 'ACCEPTED'
    for change in [{'latitude': 40.9}, {'source_name': 'Other Museum'}, {'latitude': None}]:
        r = external()
        r.update(change)
        assert e.match_records([canonical()], [r])[0]['match_status'] == 'REJECTED'


def test_ambiguous_matches_not_applied():
    rows = [canonical(), canonical('ATTR_0002')]
    matches = e.match_records(rows, [external()])
    assert matches[0]['match_status'] == 'AMBIGUOUS'
    assert matches[0]['candidate_ids'] == ['ATTR_0001', 'ATTR_0002']
    selected, _ = e.select_costs(matches)
    assert not selected
    assert all(r['admission_price_usd'] == '' for r in e.enrich_rows(rows, selected))


def test_official_link_requires_real_source_id():
    r = external('official', 'offer/1', associated_source='nyc_commonplace', associated_source_id='ATTR_0001')
    assert e.match_records([canonical()], [r])[0]['match_status'] == 'ACCEPTED'
    r['associated_source_id'] = 'bogus'
    assert e.match_records([canonical()], [r])[0]['match_status'] == 'REJECTED'


def test_precedence_and_retained_conflict():
    osm = external()
    wd = external('wikidata', 'Q1$fee', e.price('paid_unknown'), linked_osm_id='node/1')
    official = external('official', 'offer', e.price('fixed', '30'), associated_source='nyc_commonplace', associated_source_id='ATTR_0001')
    for records in [[osm, wd, official], [official, wd, osm]]:
        selected, conflicts = e.select_costs(e.match_records([canonical()], records))
        assert selected['ATTR_0001']['price']['usd'] == '30'
        assert conflicts[0]['resolution'] == 'source_precedence'
        assert len(conflicts[0]['records']) == 3


def test_same_authority_disagreement_never_picks_number():
    selected, conflicts = e.select_costs(e.match_records([canonical()], [external(), external(eid='node/2', parsed=e.price('free', '0'))]))
    assert selected['ATTR_0001']['price'] == e.price('variable')
    assert conflicts[0]['resolution'] == 'same_authority_variable'


def test_wikidata_positive_not_assumed_adult_price():
    osm = external(wikidata_id='Q1')
    data = {'entities': {'Q1': {'claims': {'P2555': [{'id': 'Q1$fee', 'mainsnak': {'datavalue': {'value': {'amount': '+25', 'unit': 'http://www.wikidata.org/entity/Q4917'}}}}]}}}}
    records = e.normalize_wikidata(data, '2026-10-11', [osm])
    assert records[0]['price'] == e.price('paid_unknown')
    # Qualifiers can concern discounts, ticket categories or time; do not ignore them.
    data['entities']['Q1']['claims']['P2555'][0]['qualifiers'] = {'P518': [{'snaktype': 'value'}]}
    assert e.normalize_wikidata(data, '2026-10-11', [osm])[0]['price'] == e.price('variable')


def test_wikidata_requires_accepted_osm_link():
    r = external('wikidata', 'Q1$fee', linked_osm_id='node/9')
    assert e.match_records([canonical()], [r])[0]['match_status'] == 'REJECTED'


def test_official_ticket_basis_not_silently_selected():
    data = {'records': [{'external_id': 'x', 'source_url': 'https://example.org', 'price_raw': '$12', 'scope': 'admission', 'basis': 'child ticket'}]}
    assert e.normalize_official(data, '2026-10-11')[0]['price'] == e.price('variable')


def test_snapshot_checksum_enforced(tmp_path):
    (tmp_path / 'osm.json').write_text('{"elements": []}')
    (tmp_path / 'retrieval_metadata.json').write_text(json.dumps({'sources': {'osm': {'file': 'osm.json', 'raw_sha256': 'bad', 'retrieved_at': '2026-10-11'}}}))
    with pytest.raises(ValueError, match='checksum'):
        e.load_snapshots(tmp_path)


def test_full_canonical_regeneration_preserves_all_old_fields(tmp_path):
    # Full row-count integration uses frozen identities and a tiny synthetic source,
    # never the live/raw local caches. Writes only to pytest's temporary directory.
    source = e.ROOT / 'data/processed/attractions.csv'
    with source.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    core = [{k: v for k, v in row.items() if k not in e.FIELDS} for row in rows]
    assert len(core) == len({r['attraction_id'] for r in core}) == 3066
    canonical_path = tmp_path / 'attractions.csv'
    e.write_csv(canonical_path, core, list(core[0]))
    raw = tmp_path / 'raw'
    raw.mkdir()
    first = core[0]
    body = json.dumps({'elements': [dict(type='node', id=1, lat=float(first['latitude']), lon=float(first['longitude']),
        tags={'name': first['name'], 'tourism': 'attraction', 'fee': 'no'})]}).encode()
    (raw / 'osm.json').write_bytes(body)
    (raw / 'retrieval_metadata.json').write_text(json.dumps({'sources': {'osm': {'file': 'osm.json', 'raw_sha256': hashlib.sha256(body).hexdigest(), 'retrieved_at': '2026-10-11T00:00:00Z'}}}))
    report = tmp_path / 'report.json'
    summary = e.run(canonical_path, raw, tmp_path / 'interim', report)
    before = canonical_path.read_bytes()
    interim_before = {p.name: p.read_bytes() for p in (tmp_path / 'interim').iterdir()}
    assert e.run(canonical_path, raw, tmp_path / 'interim', report) == summary
    assert canonical_path.read_bytes() == before
    assert {p.name: p.read_bytes() for p in (tmp_path / 'interim').iterdir()} == interim_before
    with canonical_path.open(newline='') as stream:
        enriched = list(csv.DictReader(stream))
    assert [{k: r[k] for k in core[0]} for r in enriched] == core
    assert enriched[0]['admission_price_usd'] == '0'
    assert all(r['admission_price_usd'] == '' for r in enriched if r['admission_price_type'] == 'unknown')
    assert summary['total'] == 3066


def test_shared_wikidata_identity_quarantined():
    rows = [canonical(), canonical('ATTR_0002', 'Other Museum')]
    a = external(wikidata_id='Q1')
    b = external(eid='node/2', wikidata_id='Q1')
    b['source_name'] = 'Other Museum'
    wd = external('wikidata', 'Q1$fee', linked_osm_id='node/1', wikidata_id='Q1')
    matches = e.match_records(rows, [a, b, wd])
    assert matches[-1]['match_status'] == 'AMBIGUOUS'
    assert matches[-1]['candidate_ids'] == ['ATTR_0001', 'ATTR_0002']


def test_wikidata_stale_snapshot_link_rejected(tmp_path):
    metadata = {'sources': {}}
    for source, data in [('osm', {'elements': []}), ('wikidata', {'entities': {}})]:
        body = json.dumps(data).encode()
        (tmp_path / f'{source}.json').write_bytes(body)
        metadata['sources'][source] = {'file': f'{source}.json', 'raw_sha256': hashlib.sha256(body).hexdigest(), 'retrieved_at': '2026-10-11'}
    metadata['sources']['wikidata']['linked_osm_sha256'] = 'stale'
    (tmp_path / 'retrieval_metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='different OSM'):
        e.load_snapshots(tmp_path)
