"""Offline, deterministic OSM enrichment of a frozen canonical CSV."""
import csv
from difflib import SequenceMatcher
import io
import json
import math
from pathlib import Path

import pandas as pd

from scripts.shared.restaurant_matching import normalize_name, normalize_address, normalize_zipcode, coordinate_distance
from scripts.restaurants.download_restaurants_osm import CACHE, ROOT, validate_response
from scripts.restaurants.restaurant_hours import HOURS_FIELDS, add_hours_rows, hours_coverage, holiday_rule, load_holiday_calendar

CORE = ['restaurant_id','name','rating','rating_count','price_category','price_min','price_max',
        'price_open_ended','price_range_label','address','latitude','longitude','zipcode','url','source']
DIETS = ['vegetarian','vegan','halal','kosher','gluten_free']
RAW = ['opening_hours_raw','opening_hours_kitchen_raw','cuisine_raw']+[f'diet_{d}_raw' for d in DIETS]
EXTRA = ['opening_hours_raw','opening_hours_source','opening_hours_kitchen_raw','opening_hours_kitchen_source',
         'cuisine_raw','cuisine','cuisine_source']+[f'diet_{d}' for d in DIETS]+['dietary_source','osm_id','osm_type']
EXTRA += HOURS_FIELDS
CLEAN = ['osm_type','osm_id','osm_key','name','name_normalized','latitude','longitude',
         'address_house_number','address_street','address_postcode','address_city','address_normalized',*RAW,'source']
REPORT = ['restaurant_id','canonical_name','canonical_address','canonical_zipcode','canonical_latitude','canonical_longitude',
          'osm_key','osm_name','osm_address','osm_postcode','osm_latitude','osm_longitude',
          'distance_meters','match_method','match_confidence','match_status']
ENRICHMENT = ['restaurant_id','osm_type','osm_id','osm_key','osm_name','distance_meters',*RAW,
              'match_method','match_confidence','match_status']


def extract_elements(data):
    rows=[]
    unique={ (e['type'],e['id']):e for e in validate_response(data)['elements'] }
    for (kind, ident),e in sorted(unique.items()):
        tags=e.get('tags',{})
        if tags.get('amenity')!='restaurant':continue
        coords=e if kind=='node' else e.get('center',{})
        house=tags.get('addr:housenumber');street=tags.get('addr:street')
        address=' '.join(x for x in [house,street] if x) or None
        row=dict(osm_type=kind,osm_id=str(ident),osm_key=f'{kind}/{ident}',name=tags.get('name'),
            name_normalized=normalize_name(tags.get('name')),latitude=coords.get('lat'),longitude=coords.get('lon'),
            address_house_number=house,address_street=street,address_postcode=tags.get('addr:postcode'),
            address_city=tags.get('addr:city'),address_normalized=normalize_address(address),source='openstreetmap',
            opening_hours_raw=tags.get('opening_hours'),opening_hours_kitchen_raw=tags.get('opening_hours:kitchen'),
            cuisine_raw=tags.get('cuisine'))
        row.update({f'diet_{d}_raw':tags.get(f'diet:{d}') for d in DIETS})
        rows.append(row)
    return pd.DataFrame(rows,columns=CLEAN)


def cuisine_values(raw):
    return sorted(set(v.strip().lower() for v in raw.split(';') if v.strip())) if raw else None


def compatible_address(canonical, osm):
    address=normalize_address(canonical.address)
    street=normalize_address(osm.address_street)
    house=normalize_address(osm.address_house_number)
    # Require both house number and complete street tokens; no city-only agreement.
    return bool(address and street and house and (f' {house} {street} ' in f' {address} '))


def match_records(canonical, osm):
    """All plausible edges in a one-to-one conflict remain ambiguous; never force a winner.

    Reuse repository Haversine and normalization. The legacy 100m cutoff is refined
    into <=50m strong evidence and <=150m only with postcode/full street evidence.
    No automatic acceptance beyond 150m, even for same-name chain branches.
    """
    canonical=canonical.copy()
    canonical["latitude"]=pd.to_numeric(canonical.latitude,errors="raise")
    canonical["longitude"]=pd.to_numeric(canonical.longitude,errors="raise")
    records=[]; plausible=[]
    for _,o in osm.iterrows():
        edges=[]
        valid_coords=all(pd.notna(o[v]) and math.isfinite(float(o[v])) for v in ['latitude','longitude'])
        valid_coords=valid_coords and -90<=float(o.latitude)<=90 and -180<=float(o.longitude)<=180
        if not valid_coords:
            records.append(make_report(None,o,None,'invalid_coordinates',None,'REJECTED'));continue
        nearby=canonical.loc[canonical.latitude.sub(float(o.latitude)).abs().le(0.002) & canonical.longitude.sub(float(o.longitude)).abs().le(0.003)]
        for _,c in nearby.iterrows():
            distance=coordinate_distance(c,o)
            if distance>150:continue
            cname=normalize_name(c['name']);oname=o.name_normalized
            if not cname or pd.isna(oname) or not oname:continue
            exact=cname==oname
            ratio=SequenceMatcher(None,cname,oname,autojunk=False).ratio()
            same_zip=bool(normalize_zipcode(o.address_postcode) and normalize_zipcode(o.address_postcode)==normalize_zipcode(c.zipcode))
            address=compatible_address(c,o)
            # Different explicit house numbers indicate a different branch even nearby.
            house=normalize_address(o.address_house_number)
            canonical_address=normalize_address(c.address)
            conflict=bool(house and canonical_address and canonical_address.split()[0].isdigit() and house!=canonical_address.split()[0])
            method=None
            if not conflict:
                if exact and distance<=50:method='exact_name_close_coordinates'
                elif exact and same_zip:method='exact_name_postcode'
                elif exact and address:method='exact_name_address'
                elif ratio>=0.94 and distance<=50:method='fuzzy_name_close_coordinates'
                elif ratio>=0.94 and same_zip and address:method='fuzzy_name_strong_address'
            if method:
                edges.append(make_report(c,o,distance,method,1.0 if exact else round(ratio,6),'PENDING'))
            elif exact or ratio>=0.94 or distance<=50:
                records.append(make_report(c,o,distance,'conflicting_or_insufficient_evidence',ratio,'REJECTED'))
        if edges:plausible.extend(edges)
        else:records.append(make_report(None,o,None,'no_confident_candidate',None,'UNMATCHED'))
    canonical_counts={};osm_counts={}
    for r in plausible:
        canonical_counts[r['restaurant_id']]=canonical_counts.get(r['restaurant_id'],0)+1
        osm_counts[r['osm_key']]=osm_counts.get(r['osm_key'],0)+1
    for r in plausible:
        r['match_status']='MATCHED' if canonical_counts[r['restaurant_id']]==osm_counts[r['osm_key']]==1 else 'AMBIGUOUS'
    records.extend(plausible)
    # Source rows with rejected candidates are REJECTED; unmatched means no reviewed candidate.
    rejected_keys={r['osm_key'] for r in records if r['match_status']=='REJECTED'}
    records=[r for r in records if not (r['match_status']=='UNMATCHED' and r['osm_key'] in rejected_keys)]
    return pd.DataFrame(records,columns=REPORT).sort_values(['osm_key','restaurant_id','match_status'],na_position='last').reset_index(drop=True)


def make_report(c,o,distance,method,confidence,status):
    return dict(restaurant_id=None if c is None else c.restaurant_id,
        canonical_name=None if c is None else c['name'],canonical_address=None if c is None else c.address,
        canonical_zipcode=None if c is None else c.zipcode,canonical_latitude=None if c is None else c.latitude,
        canonical_longitude=None if c is None else c.longitude,osm_key=o.osm_key,osm_name=o['name'],
        osm_address=' '.join(str(o[x]) for x in ['address_house_number','address_street'] if pd.notna(o[x])),
        osm_postcode=o.address_postcode,osm_latitude=o.latitude,osm_longitude=o.longitude,
        distance_meters=distance,match_method=method,match_confidence=confidence,match_status=status)


def frozen_projection(content):
    rows=list(csv.DictReader(io.StringIO(content)))
    if not rows or any(k not in rows[0] for k in CORE):raise ValueError('Missing frozen core columns')
    buffer=io.StringIO(newline='')
    writer=csv.writer(buffer,lineterminator='\n');writer.writerow(CORE)
    writer.writerows([[row[k] for k in CORE] for row in rows])
    return buffer.getvalue().encode()


def assert_frozen(before,after,expected_count=670):
    rows=list(csv.DictReader(io.StringIO(before)))
    if len(rows)!=expected_count or len({r['restaurant_id'] for r in rows})!=expected_count:
        raise AssertionError('Expected frozen 670 unique identities')
    if frozen_projection(before)!=frozen_projection(after):
        raise AssertionError('Frozen canonical values, identities or row ordering changed')


def merge_csv(content,enrichment):
    rows=list(csv.DictReader(io.StringIO(content)))
    columns=list(rows[0])
    unknown=[k for k in columns if k not in CORE+EXTRA]
    if unknown:raise ValueError(f'Unexpected legacy enrichment fields: {unknown}; explicit provenance review required')
    accepted=enrichment.loc[enrichment.match_status.eq('MATCHED')]
    if accepted.restaurant_id.duplicated().any() or accepted.osm_key.duplicated().any():raise ValueError('Nonunique accepted match')
    lookup=accepted.set_index('restaurant_id').to_dict('index')
    for row in rows:
        row.update({k:'' for k in EXTRA})
        e=lookup.get(row['restaurant_id'])
        if e is None:continue
        for field in ['opening_hours','opening_hours_kitchen']:
            raw=e[field+'_raw']
            if pd.notna(raw):row[field+'_raw']=raw;row[field+'_source']='openstreetmap'
        if pd.notna(e['cuisine_raw']):
            row['cuisine_raw']=e['cuisine_raw'];row['cuisine']=json.dumps(cuisine_values(e['cuisine_raw']),ensure_ascii=False)
            row['cuisine_source']='openstreetmap'
        for d in DIETS:
            if pd.notna(e[f'diet_{d}_raw']):row[f'diet_{d}']=e[f'diet_{d}_raw'];row['dietary_source']='openstreetmap'
        row['osm_id']=e['osm_id'];row['osm_type']=e['osm_type']
    rows=add_hours_rows(rows)
    buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=CORE+EXTRA,lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    result=buffer.getvalue();assert_frozen(content,result)
    return result


def coverage_report(osm,report,output,metadata,raw_data):
    lines=['## OpenStreetMap enrichment','', 'Retrieval succeeded; cached JSON was processed offline.',
           f'Raw restaurant records: {len(osm)}.', '', 'Retrieval metadata: `'+json.dumps(metadata,sort_keys=True)+'`','',
           '© OpenStreetMap contributors; [ODbL attribution](https://www.openstreetmap.org/copyright).',
           'Community-maintained data may be incomplete or stale. Hours are preserved verbatim, without parsing or repair.', '',
           '## Source coverage','']
    for label,fields in [('Opening hours',['opening_hours_raw']),('Kitchen hours',['opening_hours_kitchen_raw']),
                        ('Cuisine',['cuisine_raw']),('Any supported dietary tag',[f'diet_{d}_raw' for d in DIETS])]:
        lines.append(f'- {label}: {int(osm[fields].notna().any(axis=1).sum())} / {len(osm)}')
    all_diet_count=sum(any(k.startswith('diet:') for k in e.get('tags',{})) for e in raw_data['elements'])
    lines.append(f'- Any explicit diet:* tag (including unsupported kinds): {all_diet_count} / {len(osm)}')
    lines+=['','## Match statuses','', 'Candidate counts include rejected nearby pairs. Source counts use precedence MATCHED > AMBIGUOUS > REJECTED > UNMATCHED; each source is counted once.','']
    priority={'MATCHED':0,'AMBIGUOUS':1,'REJECTED':2,'UNMATCHED':3}
    source_status=report.assign(priority=report.match_status.map(priority)).sort_values('priority').drop_duplicates('osm_key')
    for status in priority:lines.append(f'- {status}: {int(report.match_status.eq(status).sum())} candidate/report rows; {int(source_status.match_status.eq(status).sum())} source records')
    lines+=['','## Canonical coverage','']
    for label,fields in [('Opening hours',['opening_hours_raw']),('Kitchen hours',['opening_hours_kitchen_raw']),
        ('Cuisine',['cuisine']),('Any dietary tag',[f'diet_{d}' for d in DIETS])]+[(d,[f'diet_{d}']) for d in DIETS]:
        lines.append(f'- {label}: {int(output[fields].ne("").any(axis=1).sum())} / 670')
    lines+=['','All 670 IDs, row order and all 15 frozen core columns passed byte-identical CSV-projection validation.',
        'Matching thresholds are heuristics: <=50m strong; <=150m requires exact name plus postcode/address, or fuzzy >=0.94 plus full address and postcode. No matches beyond 150m. Conflicting house numbers block acceptance.',
        'Confidence is an evidence score, not a calibrated probability. All one-to-many/many-to-one plausible conflicts stay AMBIGUOUS.',
        'No meal-cost estimate, cuisine-based dietary inference or custom opening-hours parser is used.','']
    source_ph=sum(holiday_rule(e.get('tags',{}).get('opening_hours'))['has_explicit_holiday_rule'] for e in raw_data['elements'])
    lines.append(f'Raw OSM schedules containing unquoted PH tokens: {source_ph} / {len(osm)}')
    from scripts.restaurants.preprocess_restaurants import canonical_report
    return canonical_report(output)+'\n'+'\n'.join(lines)+'\n'+hours_coverage(output.to_dict('records'))


def enrich_osm(canonical_path=ROOT/'data/processed/restaurants.csv',cache_path=CACHE):
    # Load/validate all cached input before touching existing outputs; never download in preprocessing.
    data=validate_response(json.loads(cache_path.read_text()))
    if not data.get('retrieval'):raise ValueError('Missing retrieval metadata')
    load_holiday_calendar()  # Validate static metadata before touching any outputs.
    content=canonical_path.read_text();assert_frozen(content,content)
    canonical=pd.read_csv(io.StringIO(content),dtype=str,keep_default_na=False)
    from scripts.restaurants.download_restaurants_osm import bounding_box
    if data['retrieval'].get('bounding_box')!=bounding_box(canonical):raise ValueError('OSM cache bounds do not cover this canonical input')
    osm=extract_elements(data);report=match_records(canonical,osm)
    enrichment=report.merge(osm[['osm_key','osm_type','osm_id',*RAW]],on='osm_key',how='left')[ENRICHMENT]
    merged=merge_csv(content,enrichment)
    output=pd.read_csv(io.StringIO(merged),dtype=str,keep_default_na=False)
    coverage=coverage_report(osm,report,output,data['retrieval'],data)
    files={ROOT/'data/reports/audit/restaurants/osm_matching_report.csv':report.to_csv(index=False),
        ROOT/'data/reports/audit/restaurants/osm_ambiguous_matches.csv':report.loc[report.match_status.eq('AMBIGUOUS')].to_csv(index=False),
        ROOT/'data/reports/restaurant_data_report.md':coverage,canonical_path:merged}
    for path,value in files.items():
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.tmp')
        temporary.write_text(value);temporary.replace(path)
    print(coverage)


if __name__=='__main__':enrich_osm()
