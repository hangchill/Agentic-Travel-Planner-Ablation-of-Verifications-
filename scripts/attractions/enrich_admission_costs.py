"""Offline admission enrichment from checksum-verified public source snapshots."""
import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

from scripts.shared.restaurant_matching import normalize_name, coordinate_distance
from scripts.restaurants.download_restaurants_osm import validate_response

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data/raw/attractions/admission'
PREFIX = 'admission_price_'
FIELDS = [PREFIX + x for x in ('type', 'usd', 'min_usd', 'max_usd', 'raw',
          'source_type', 'source', 'observed_date', 'is_estimated', 'basis')]
TYPES = ('free', 'fixed', 'from', 'range', 'variable', 'pay_what_you_wish', 'paid_unknown', 'unknown')
PRIORITY = {'official': 0, 'wikidata': 1, 'osm': 2}
# Restrict fees to whole visitor attractions, never parking/toilets/transport/artwork.
TOURISM = {'museum', 'attraction', 'zoo', 'aquarium', 'theme_park', 'gallery', 'viewpoint'}
LEISURE = {'park', 'garden', 'nature_reserve'}
NUMBER = r'(?:\d+(?:\.\d{1,2})?)'
CURRENCY = r'(?:USD\s*|US\$\s*|\$\s*)'
AMOUNT = rf'(?:{CURRENCY}({NUMBER})|({NUMBER})\s*USD)'


def price(kind='unknown', exact=None, minimum=None, maximum=None):
    return {'type': kind, 'usd': exact, 'min_usd': minimum, 'max_usd': maximum}


def amount(text):
    match = re.fullmatch(AMOUNT, text.strip(), re.I)
    return str(Decimal(next(x for x in match.groups() if x is not None))) if match else None


def parse_price(raw='', fee='', *, admission_scope=True):
    """Strict USD admission grammar. Unparsed text never becomes a numeric estimate."""
    if not admission_scope:
        return price()
    text = str(raw or '').strip()
    lower = text.lower()
    fee = str(fee or '').strip().lower()
    if re.search(r'pay[- ]what[- ]you[- ](?:wish|want)|suggested (?:donation|contribution)', lower):
        # A suggested amount is not a minimum. Accept only an explicit minimum
        # in an otherwise unqualified pay-what-you-wish statement.
        minimum = None
        match = re.search(r'\bminimum\s+(.+?)\)?$', text, re.I)
        if match and not re.search(r'child|senior|resident|member|group|event', lower):
            minimum = amount(match.group(1))
        return price('pay_what_you_wish', minimum=minimum)
    if re.search(r'child|senior|resident|member|group|tour|exhibition|event|hour|day|vehicle|parking|toilet|internet', lower):
        return price('variable') if fee != 'no' or text else price()
    if fee == 'no' and not text:
        return price('free', '0')
    if lower in {'free', 'no charge', '0', '0 usd', '$0'}:
        return price('variable') if fee == 'yes' else price('free', '0')
    # Person units are allowed; temporal/group units are not.
    text = re.sub(r'\s*(?:/person|per person)\s*$', '', text, flags=re.I).strip()
    exact = amount(text)
    if exact is not None:
        if (fee == 'no' and Decimal(exact) != 0) or (fee == 'yes' and Decimal(exact) == 0):
            return price('variable')
        return price('free' if Decimal(exact) == 0 else 'fixed', exact)
    if text.lower().startswith('from '):
        minimum = amount(text[5:])
        if minimum is not None and fee != 'no':
            return price('from', minimum=minimum)
    # Require a currency; accept "$10–20", "10-20 USD", "$10-$20".
    match = re.fullmatch(rf'(?:{CURRENCY})?({NUMBER})\s*[-–]\s*(?:{CURRENCY})?({NUMBER})(?:\s*USD)?', text, re.I)
    if match and re.search(r'USD|\$', text, re.I) and fee != 'no':
        lo, hi = map(Decimal, match.groups())
        if lo <= hi:
            return price('range', minimum=str(lo), maximum=str(hi))
    if fee == 'no' and text:
        return price('variable')  # Contradictory/malformed free + charge evidence.
    if lower in {'variable', 'varies', 'conditional'} or ';' in text or '@' in text:
        return price('variable')
    return price('paid_unknown' if fee == 'yes' else 'unknown')


def attraction_feature(tags):
    return (tags.get('tourism') in TOURISM or tags.get('leisure') in LEISURE) and not (
        tags.get('amenity') in {'parking', 'toilets', 'charging_station'} or tags.get('access') in {'private', 'no'})


def record(source, external_id, name, lat, lon, url, date, raw, parsed, **extra):
    return dict(external_source=source, external_id=external_id, source_name=name,
                latitude=lat, longitude=lon, source_url=url, observed_date=date,
                price_raw=raw, price=parsed, basis='general admission per person', **extra)


def normalize_osm(data, date):
    result = []
    for e in sorted(validate_response(data)['elements'], key=lambda x: (x['type'], x['id'])):
        tags = e.get('tags', {})
        if not any(k in tags for k in ('fee', 'charge', 'fee:conditional', 'charge:conditional')):
            continue
        scope = attraction_feature(tags)
        conditional = any(k in tags for k in ('fee:conditional', 'charge:conditional'))
        parsed = (price('variable') if conditional and scope else
                  parse_price(tags.get('charge', ''), tags.get('fee', ''), admission_scope=scope))
        point = e if e['type'] == 'node' else e.get('center', {})
        eid = f"{e['type']}/{e['id']}"
        result.append(record('osm', eid, tags.get('name', ''), point.get('lat'), point.get('lon'),
            f'https://www.openstreetmap.org/{eid}', date, json.dumps(tags, sort_keys=True, ensure_ascii=False),
            parsed, admission_scope=scope, wikidata_id=tags.get('wikidata', ''),
            reason='' if scope else 'not a public whole-attraction feature'))
    return result


def normalize_wikidata(data, date, osm_records):
    """P2555 is not automatically standard adult admission; preserve qualifiers."""
    links = defaultdict(list)
    for r in osm_records:
        if r.get('admission_scope') and re.fullmatch(r'Q\d+', r.get('wikidata_id', '')):
            links[r['wikidata_id']].append(r)
    result = []
    for qid, entity in sorted(data.get('entities', {}).items()):
        for claim in entity.get('claims', {}).get('P2555', []):
            if claim.get('rank') == 'deprecated':
                continue
            snak = claim.get('mainsnak', {})
            value = snak.get('datavalue', {}).get('value', {})
            qualifiers = claim.get('qualifiers', {})
            # Unresolved ticket/time qualifiers must not select an arbitrary adult price.
            parsed = price('variable' if qualifiers else 'paid_unknown')
            if not qualifiers and snak.get('snaktype') == 'novalue':
                parsed = price('free', '0')
            elif not qualifiers and isinstance(value, dict):
                try:
                    number = Decimal(value.get('amount', 'NaN'))
                    if number.is_finite() and number == 0:
                        parsed = price('free', '0')
                    # Positive unqualified fees lack an explicit adult/person basis;
                    # establish paid status only. No currency conversion or guessing.
                except InvalidOperation:
                    parsed = price()
            for link in links.get(qid, []):
                result.append(record('wikidata', claim.get('id', qid), link['source_name'],
                    link['latitude'], link['longitude'], f'https://www.wikidata.org/wiki/{qid}', date,
                    json.dumps(claim, sort_keys=True, ensure_ascii=False), parsed,
                    admission_scope=True, linked_osm_id=link['external_id'], wikidata_id=qid,
                    basis_verified=False))
                result[-1]['basis'] = 'ordinary admission; adult/person amount basis unverified'
    return result


def normalize_official(data, date):
    """Opt-in structured offers with an explicit associated source ID and price basis.

    Input records retain the source response/offer and URL. A name or asserted ATTR
    ID alone is insufficient: associated source + source_id must exist canonically.
    """
    result = []
    for item in data.get('records', []):
        basis = item.get('basis')
        scope = item.get('scope') == 'admission'
        verified = basis in {'standard adult per person', 'general admission per person'}
        parsed = parse_price(item.get('price_raw'), item.get('fee'), admission_scope=scope)
        if not verified and parsed['type'] not in {'unknown', 'paid_unknown'}:
            parsed = price('variable')
        result.append(record('official', item['external_id'], item.get('name', ''),
            item.get('latitude'), item.get('longitude'), item['source_url'], date,
            item.get('price_raw', ''), parsed, admission_scope=scope,
            associated_source=item.get('associated_source', ''),
            associated_source_id=str(item.get('associated_source_id', ''))))
        result[-1]['basis'] = basis or 'unverified ticket basis'
    return result


def load_snapshots(directory):
    metadata = json.loads((directory / 'retrieval_metadata.json').read_text())
    records = []
    osm = []
    for source in ('osm', 'wikidata', 'official'):
        entry = metadata.get('sources', {}).get(source)
        if not entry:
            continue
        path = directory / entry['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['raw_sha256']:
            raise ValueError(f'{source} snapshot checksum mismatch')
        if source == 'wikidata' and entry.get('linked_osm_sha256') != metadata['sources'].get('osm', {}).get('raw_sha256'):
            raise ValueError('Wikidata snapshot belongs to a different OSM snapshot')
        data = json.loads(path.read_text())
        date = entry['retrieved_at'].split('T')[0]
        if source == 'osm':
            osm = normalize_osm(data, date)
            records.extend(osm)
        elif source == 'wikidata':
            records.extend(normalize_wikidata(data, date, osm))
        else:
            records.extend(normalize_official(data, date))
    return sorted(records, key=lambda r: (r['external_source'], r['external_id'], r.get('linked_osm_id', '')))


def match_records(rows, records):
    names = defaultdict(list)
    source_ids = defaultdict(list)
    for row in rows:
        names[normalize_name(row['name'])].append(row)
        source_ids[(row['source'], row['source_id'])].append(row)
    matches = []
    accepted_osm = {}
    accepted_qids = defaultdict(dict)
    # Wikidata is only propagated through a uniquely accepted OSM feature.
    for r in sorted(records, key=lambda x: (x['external_source'] == 'wikidata', x['external_source'], x['external_id'])):
        candidates = []
        method = 'none'
        distances = {}
        if r.get('admission_scope'):
            if r['external_source'] == 'official':
                candidates = source_ids.get((r.get('associated_source'), r.get('associated_source_id')), [])
                method = 'associated_source_id'
            elif r['external_source'] == 'wikidata':
                linked = accepted_osm.get(r.get('linked_osm_id'), [])
                candidates = list(accepted_qids.get(r.get('wikidata_id'), {}).values()) if linked and r.get('wikidata_id') else linked
                method = 'wikidata_via_accepted_osm_id'
            else:
                method = 'exact_normalized_name_within_100m'
                for row in names.get(normalize_name(r['source_name']), []):
                    if r.get('latitude') is None or r.get('longitude') is None or not row['latitude'] or not row['longitude']:
                        continue
                    d = coordinate_distance(r, {k: float(row[k]) for k in ('latitude', 'longitude')})
                    if d <= 100:
                        candidates.append(row)
                        distances[row['attraction_id']] = round(d, 3)
        status = 'ACCEPTED' if len(candidates) == 1 else 'AMBIGUOUS' if len(candidates) > 1 else 'REJECTED'
        if status == 'ACCEPTED' and r['external_source'] == 'osm':
            accepted_osm[r['external_id']] = candidates
            if r.get('wikidata_id'):
                accepted_qids[r['wikidata_id']][candidates[0]['attraction_id']] = candidates[0]
        # One audit row per external record; retain every ambiguous candidate ID.
        match = {'attraction_id': candidates[0]['attraction_id'] if status == 'ACCEPTED' else '',
            'external_source': r['external_source'], 'external_id': r['external_id'],
            'match_status': status, 'match_method': method,
            'match_score': distances.get(candidates[0]['attraction_id'], '') if len(candidates) == 1 else '',
            'source_name': r['source_name'], 'canonical_name': candidates[0]['name'] if len(candidates) == 1 else '',
            'candidate_ids': sorted(x['attraction_id'] for x in candidates),
            'record': r}
        matches.append(match)
    return matches


def select_costs(matches):
    grouped = defaultdict(list)
    for match in matches:
        if match['match_status'] == 'ACCEPTED' and match['record']['price']['type'] != 'unknown':
            grouped[match['attraction_id']].append(match['record'])
    selected, conflicts = {}, []
    for aid, records in sorted(grouped.items()):
        records.sort(key=lambda r: (PRIORITY[r['external_source']], r['external_id'], r['source_url']))
        top = [r for r in records if PRIORITY[r['external_source']] == PRIORITY[records[0]['external_source']]]
        signatures = {json.dumps(r['price'], sort_keys=True) for r in top}
        choice = dict(top[0])
        disagreement = len({json.dumps(r['price'], sort_keys=True) for r in records}) > 1
        if disagreement:
            conflicts.append({'attraction_id': aid, 'resolution': 'same_authority_variable' if len(signatures) > 1 else 'source_precedence', 'records': records})
        if len(signatures) > 1:
            choice['price'] = price('variable')
            choice['price_raw'] = json.dumps([r['price_raw'] for r in top], ensure_ascii=False)
            choice['source_url'] = ' | '.join(sorted({r['source_url'] for r in top}))
            choice['observed_date'] = max(r['observed_date'] for r in top)
        selected[aid] = choice
    return selected, conflicts


def enrich_rows(rows, selected):
    enriched = []
    for row in rows:
        output = {k: v for k, v in row.items() if k not in FIELDS}
        r = selected.get(row['attraction_id'])
        values = {**(r['price'] if r else price()), 'raw': r['price_raw'] if r else '',
            'source_type': r['external_source'] if r else '', 'source': r['source_url'] if r else '',
            'observed_date': r['observed_date'] if r else '', 'is_estimated': 'false',
            'basis': r['basis'] if r else ''}
        output.update({PREFIX + k: '' if v is None else str(v) for k, v in values.items()})
        enriched.append(output)
    return enriched


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ''.join(json.dumps(row, sort_keys=True, ensure_ascii=False) + '\n' for row in rows)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def coverage(rows, matches, conflicts):
    types = Counter(r[PREFIX + 'type'] for r in rows)
    exact = sum(r[PREFIX + 'usd'] != '' for r in rows)
    bounds = sum(r[PREFIX + 'usd'] != '' or r[PREFIX + 'min_usd'] != '' or r[PREFIX + 'max_usd'] != '' for r in rows)
    total = len(rows)
    return {'total': total, 'price_types': {t: types[t] for t in TYPES},
            'source_breakdown': dict(sorted(Counter(r[PREFIX + 'source_type'] or 'none' for r in rows).items())),
            'match_statuses': {s: sum(m['match_status'] == s for m in matches) for s in ('ACCEPTED', 'AMBIGUOUS', 'REJECTED')},
            'conflicts': len(conflicts), 'evidence_count': total - types['unknown'],
            'exact_count': exact, 'usable_bound_count': bounds,
            'evidence_coverage': (total-types['unknown'])/total,
            'exact_coverage': exact/total, 'usable_bound_coverage': bounds/total}


def run(canonical, raw, interim, report=None):
    with canonical.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 3066 or len({r['attraction_id'] for r in rows}) != 3066 or any(not re.fullmatch(r'ATTR_\d+', r['attraction_id']) for r in rows):
        raise ValueError('Expected 3,066 unique stable ATTR_ identities')
    records = load_snapshots(raw)
    matches = match_records(rows, records)
    selected, conflicts = select_costs(matches)
    output = enrich_rows(rows, selected)
    old_fields = [k for k in rows[0] if k not in FIELDS]
    if [{k: r[k] for k in old_fields} for r in rows] != [{k: r[k] for k in old_fields} for r in output]:
        raise ValueError('Non-cost attraction fields changed')
    write_jsonl(interim / 'admission_cost_records.jsonl', records)
    write_jsonl(interim / 'admission_cost_matches.jsonl', matches)
    write_jsonl(interim / 'admission_cost_conflicts.jsonl', conflicts)
    write_jsonl(interim / 'admission_cost_accepted.jsonl', [{'attraction_id': aid, **r} for aid, r in sorted(selected.items())])
    write_csv(canonical, output, old_fields + FIELDS)
    summary = coverage(output, matches, conflicts)
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canonical', type=Path, default=ROOT / 'data/processed/attractions.csv')
    parser.add_argument('--raw', type=Path, default=RAW)
    parser.add_argument('--interim', type=Path, default=ROOT / 'data/interim')
    parser.add_argument('--report', type=Path, help='Optional untracked on-demand JSON coverage report')
    args = parser.parse_args()
    print(json.dumps(run(args.canonical, args.raw, args.interim, args.report), indent=2))


if __name__ == '__main__':
    main()
