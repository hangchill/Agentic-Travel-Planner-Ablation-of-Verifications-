"""Stream Google Local metadata and conservatively link only frozen application entities."""
from collections import Counter,defaultdict
from difflib import SequenceMatcher
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import tempfile
import pandas as pd
from scripts.shared.restaurant_matching import normalize_name,normalize_address,normalize_zipcode,coordinate_distance
from scripts.reviews.download_reviews import ROOT,RAW,download
from scripts.attractions.explore_attractions import markdown_table

CLEAN=ROOT/'data/interim/google_local_ny_metadata_clean.csv'
REPORTS=ROOT/'data/reports/audit/reviews'
REGISTRY=ROOT/'data/metadata/google_local_entity_registry.csv'
SOURCE='google_local_2021'
GRID=.002
STATUSES=['MATCHED','AMBIGUOUS','UNMATCHED','REJECTED']
CLEAN_COLUMNS=['gmap_id','name','name_normalized','alias_normalized','address','address_normalized','zipcode','latitude','longitude','categories_raw','avg_rating','num_reviews','price_raw','hours_raw','listing_state','url','source','source_row']
GENERIC={'park','playground','garden','museum','church','restaurant','cafe','bar','sports','field','library','beach','monument'}
CATEGORY_PATTERNS={'park':r'park|tourist attraction','garden':r'garden|park|tourist attraction','museum':r'museum|tourist attraction','theater':r'theater|theatre|performing|concert|cinema',
 'sports':r'sports|athletic|field|stadium|court|park|recreation','zoo':r'zoo|animal park|tourist attraction','beach':r'beach|park',
 'landmark':r'landmark|monument|memorial|tourist attraction','historic_site':r'landmark|historical|library|tourist attraction',
 'religious_site':r'church|cathedral|synagogue|temple|mosque','transport_landmark':r'station|terminal|bridge|landmark|tourist attraction',
 'amusement':r'amusement|theme park|tourist attraction','market':r'market|food','other_attraction':r'tourist attraction|landmark'}


def present(v):return v is not None and not pd.isna(v) and str(v).strip()!=''


def coordinates(row):
    try:
        lat,lon=float(row.get('latitude')),float(row.get('longitude'))
        return (lat,lon) if math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180 else None
    except (TypeError,ValueError):return None


def json_lines(path):
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for number,line in enumerate(stream,1):
            if not line.strip():continue
            row=json.loads(line)
            if not isinstance(row,dict):raise ValueError(f'Non-object metadata row {number}')
            yield number,row


def alias_name(value):
    name=normalize_name(value) or ''
    name=re.sub(r'^the\s+','',name)
    for pattern,replacement in [(r'\bft\b','fort'),(r'\bst\b','saint'),(r'\btheatre\b','theater')]:name=re.sub(pattern,replacement,name)
    return name


def clean_address(value,name=None):
    if not present(value):return None
    raw=str(value).strip();parts=raw.split(',',1)
    if len(parts)==2 and normalize_name(parts[0])==normalize_name(name):raw=parts[1].strip()
    normalized=normalize_address(raw)
    if not normalized:return None
    tokens={'street':'st','avenue':'ave','road':'rd','boulevard':'blvd','place':'pl','lane':'ln','drive':'dr','north':'n','south':'s','east':'e','west':'w'}
    return ' '.join(tokens.get(t,t) for t in normalized.split())


def zipcode(address):
    if not present(address):return None
    match=re.search(r'\b(?:NY|NJ|New York|New Jersey)\s+(\d{5})(?:-\d{4})?\b',str(address),re.I)
    return match.group(1) if match else None


def bbox_for(entities,padding=.03):
    pairs=[coordinates(row) for row in entities.to_dict('records')];pairs=[p for p in pairs if p]
    if not pairs:raise ValueError('Canonical entities have no coordinates')
    return [min(p[0] for p in pairs)-padding,max(p[0] for p in pairs)+padding,min(p[1] for p in pairs)-padding,max(p[1] for p in pairs)+padding]


def clean_metadata(path,entities,output=CLEAN):
    bounds=bbox_for(entities);keys=Counter();types=defaultdict(Counter);missing=Counter();empty=Counter();total=0;retained=0;valid=0;invalid=0
    output.parent.mkdir(parents=True,exist_ok=True);temporary=output.with_suffix('.csv.tmp')
    with tempfile.TemporaryDirectory() as directory:
        db=sqlite3.connect(str(Path(directory)/'counts.sqlite'))
        db.execute('CREATE TABLE ids (value TEXT PRIMARY KEY, n INTEGER, signature TEXT, conflict INTEGER)')
        db.execute('CREATE TABLE names (value TEXT PRIMARY KEY, n INTEGER)')
        with temporary.open('w',newline='') as destination:
            writer=csv.DictWriter(destination,fieldnames=CLEAN_COLUMNS);writer.writeheader()
            for number,row in json_lines(path):
                total+=1
                for key,value in row.items():
                    keys[key]+=1;types[key][type(value).__name__]+=1
                    if value is None:missing[key]+=1
                    if value in ('',[],{}):empty[key]+=1
                identity=row.get('gmap_id');name=row.get('name')
                if present(identity):
                    signature=hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                    db.execute('INSERT INTO ids VALUES (?,1,?,0) ON CONFLICT(value) DO UPDATE SET n=n+1,conflict=conflict OR signature!=excluded.signature',(str(identity),signature))
                if present(name):db.execute('INSERT INTO names VALUES (?,1) ON CONFLICT(value) DO UPDATE SET n=n+1',(str(name),))
                pair=coordinates(row);valid+=int(pair is not None);invalid+=int(pair is None)
                keep=pair is not None and bounds[0]<=pair[0]<=bounds[1] and bounds[2]<=pair[1]<=bounds[3]
                if not keep:continue
                retained+=1
                writer.writerow(dict(gmap_id=identity,name=name,name_normalized=normalize_name(name),alias_normalized=alias_name(name),address=row.get('address'),
                    address_normalized=clean_address(row.get('address'),name),zipcode=zipcode(row.get('address')),latitude=pair[0],longitude=pair[1],
                    categories_raw=json.dumps(row.get('category'),ensure_ascii=False),avg_rating=row.get('avg_rating'),num_reviews=row.get('num_of_reviews'),
                    price_raw=json.dumps(row.get('price'),ensure_ascii=False),hours_raw=json.dumps(row.get('hours'),ensure_ascii=False),listing_state=row.get('state'),url=row.get('url'),source=SOURCE,source_row=number))
                if total%10000==0:db.commit()
        db.commit()
        duplicates={v:n for v,n in db.execute('SELECT value,n FROM ids WHERE n>1 ORDER BY value')}
        conflicts=[v for v, in db.execute('SELECT value FROM ids WHERE conflict=1 ORDER BY value')]
        duplicate_names=db.execute('SELECT count(*),coalesce(sum(n),0) FROM names WHERE n>1').fetchone()
        stats={'raw_rows':total,'retained_nyc_rows':retained,'region_bbox_lat_min_max_lon_min_max':bounds,'bbox_padding_degrees':.03,
            'keys':sorted(keys),'types':{k:dict(v) for k,v in sorted(types.items())},
            'missing_or_null':{k:total-keys[k]+missing[k] for k in sorted(keys)},'empty_values':dict(sorted(empty.items())),
            'duplicate_gmap_id_values':len(duplicates),'duplicate_gmap_id_rows':sum(duplicates.values()),'conflicting_duplicate_gmap_ids':conflicts,
            'duplicate_name_groups':duplicate_names[0],'duplicate_name_rows':duplicate_names[1],'valid_coordinates':valid,'invalid_or_missing_coordinates':invalid}
        db.close()
    temporary.replace(output)
    return stats


def prepare_entities(restaurants,attractions):
    rows=[]
    for kind,frame in [('restaurant',restaurants),('attraction',attractions)]:
        for row in frame.to_dict('records'):
            identity=row[kind+'_id'];rows.append(dict(row,entity_type=kind,entity_id=identity,entity_name=row['name'],name_normalized=normalize_name(row['name']),
                alias_normalized=alias_name(row['name']),address_normalized=clean_address(row.get('address'),row['name']),zipcode=normalize_zipcode(row.get('zipcode'))))
    return pd.DataFrame(rows)


class CandidateIndex:
    def __init__(self,records):
        self.grid=defaultdict(list);self.names=defaultdict(list);self.addresses=defaultdict(list);self.ids={}
        for row in records:
            if not present(row.get('gmap_id')):continue
            self.ids[row['gmap_id']]=row
            if row.get('alias_normalized'):self.names[row['alias_normalized']].append(row)
            if present(row.get('address_normalized')):self.addresses[row['address_normalized']].append(row)
            pair=coordinates(row)
            if pair:self.grid[(math.floor(pair[0]/GRID),math.floor(pair[1]/GRID))].append(row)
    def candidates(self,entity):
        result={}
        pair=coordinates(entity)
        if pair:
            a,b=(math.floor(v/GRID) for v in pair)
            for i in range(a-2,a+3):
                for j in range(b-2,b+3):
                    for row in self.grid.get((i,j),[]):
                        if coordinate_distance(entity,row)<=150:result[row['gmap_id']]=row
        for row in self.names.get(entity['alias_normalized'],[]):result[row['gmap_id']]=row
        for row in self.addresses.get(entity.get('address_normalized'),[]):result[row['gmap_id']]=row
        url=str(entity.get('url') or '');found=re.search(r'0x[0-9a-f]+:0x[0-9a-f]+',url,re.I)
        if found and found[0] in self.ids:result[found[0]]=self.ids[found[0]]
        return [result[key] for key in sorted(result)]


def evaluate(entity,google):
    en=entity['name_normalized'] if present(entity.get('name_normalized')) else ''
    gn=google['name_normalized'] if present(google.get('name_normalized')) else ''
    alias_exact=bool(entity['alias_normalized']) and entity['alias_normalized']==google.get('alias_normalized')
    exact=bool(en) and en==gn
    similarity=SequenceMatcher(None,en,gn,autojunk=False).ratio()
    ea,ga=entity.get('address_normalized'),google.get('address_normalized')
    address_similarity=SequenceMatcher(None,ea,ga,autojunk=False).ratio() if present(ea) and present(ga) else None
    enumber=re.match(r'^\s*(\d+[a-z]?)\b',ea if present(ea) else '');gnumber=re.match(r'^\s*(\d+[a-z]?)\b',ga if present(ga) else '')
    same_number=bool(enumber and gnumber and enumber[1]==gnumber[1])
    strong_address=bool(address_similarity is not None and address_similarity>=.92 and same_number)
    compatible_address=bool(address_similarity is not None and address_similarity>=.85 and same_number)
    ez,gz=entity.get('zipcode'),google.get('zipcode');zip_match=present(ez) and present(gz) and ez==gz
    zip_conflict=present(ez) and present(gz) and ez!=gz
    distance=coordinate_distance(entity,google) if coordinates(entity) and coordinates(google) else None
    categories=str(google.get('categories_raw') or '').lower()
    category_support=bool(re.search(r'restaurant|cafe|coffee|bar|pub|diner|pizzeria|pizza|food',categories)) if entity['entity_type']=='restaurant' else bool(re.search(CATEGORY_PATTERNS.get(entity.get('category'),r'(?!)'),categories))
    generic=en in GENERIC or len(en)<=3
    direct=re.search(r'0x[0-9a-f]+:0x[0-9a-f]+',str(entity.get('url') or ''),re.I)
    direct_match=bool(direct and direct[0]==google['gmap_id'])
    confidence='LOW';method='INSUFFICIENT_EVIDENCE';reason='No defensible name/location combination'
    if distance is not None and distance>150:method='DISTANT_NAME_CANDIDATE';reason='Same/alias name or address is more than 150m away'
    elif entity['entity_type']=='restaurant' and zip_conflict:method='CONFLICTING_ZIP';reason='Conflicting explicit ZIP codes'
    elif direct_match and distance is not None and distance<=75 and (similarity>=.80 or compatible_address):confidence='HIGH';method='GMAP_ID_NAME_COORD';reason='Canonical Google Maps URL identity plus corroborating name/address and location'
    elif entity['entity_type']=='restaurant':
        if exact and not generic and distance is not None and distance<=30:confidence='HIGH';method='EXACT_NAME_COORD'
        elif exact and not generic and distance is not None and distance<=75 and (compatible_address or zip_match):confidence='HIGH';method='EXACT_NAME_COORD_ADDRESS' if compatible_address else 'EXACT_NAME_COORD_ZIP'
        elif exact and strong_address and (distance is None or distance<=150):confidence='HIGH';method='EXACT_NAME_ADDRESS'
        elif similarity>=.94 and not generic and distance is not None and distance<=30 and compatible_address:confidence='HIGH';method='FUZZY_NAME_COORD_ADDRESS'
        elif similarity>=.85 and not generic and strong_address and distance is not None and distance<=30:confidence='HIGH';method='STRONG_ADDRESS_COORD_NAME'
        elif (exact or similarity>=.90) and distance is not None and distance<=150:confidence='MEDIUM';method='NAME_COORD_AUDIT_ONLY'
    else:
        if exact and not generic and distance is not None and distance<=75:confidence='HIGH';method='EXACT_NAME_COORD'
        elif alias_exact and not generic and distance is not None and distance<=50:confidence='HIGH';method='NORMALIZED_ALIAS_COORD'
        elif similarity>=.95 and not generic and distance is not None and distance<=50:confidence='HIGH';method='NEAR_EXACT_NAME_COORD'
        elif similarity>=.90 and not generic and distance is not None and distance<=30 and category_support:confidence='HIGH';method='FUZZY_NAME_COORD_CATEGORY'
        elif (alias_exact or similarity>=.80) and distance is not None and distance<=150:confidence='MEDIUM';method='NAME_COORD_AUDIT_ONLY'
    if confidence!='LOW':reason='Name/location evidence satisfies documented '+confidence+' thresholds'
    # Equal/near names can still describe parent/constituent places. Distinct functional
    # words prevent relaxed fuzzy/alias acceptance without removing meaningful words.
    functions={'zoo','museum','playground','monument','memorial','carousel','garden','stadium'}
    mismatch=(set(en.split())&functions)!=(set(gn.split())&functions)
    if mismatch and not exact and confidence=='HIGH' and not direct_match:confidence='MEDIUM';method='CONSTITUENT_FUNCTION_AUDIT_ONLY';reason='Distinct functional name words may denote parent/child places'
    return dict(entity_type=entity['entity_type'],entity_id=entity['entity_id'],entity_name=entity['entity_name'],candidate_gmap_id=google['gmap_id'],
        google_name=google.get('name'),google_address=google.get('address'),google_latitude=google.get('latitude'),google_longitude=google.get('longitude'),
        google_categories=google.get('categories_raw'),google_listing_state=google.get('listing_state'),distance_meters=distance,name_similarity=round(similarity,6),
        address_similarity=round(address_similarity,6) if address_similarity is not None else None,category_compatible=category_support,
        match_method=method,match_confidence=confidence,match_status='MATCHED' if confidence=='HIGH' else ('UNMATCHED' if confidence=='MEDIUM' else 'REJECTED'),evidence_reason=reason,source=SOURCE)


def diagnose(entity,pairs):
    labels=[]
    if not coordinates(entity):labels.append('missing_coordinates')
    if entity['name_normalized'] in GENERIC or len(entity['name_normalized'] or '')<=3:labels.append('generic_name')
    if entity['entity_type']=='restaurant':
        if not present(entity.get('address_normalized')) or not re.search(r'\d',entity.get('address_normalized') or ''):labels.append('missing_or_weak_address')
        if re.search(r'\bNJ\b',str(entity.get('address') or '')):labels.append('non_New_York_address_source_split_limitation')
        if any('closed' in str(p.get('google_listing_state') or '').lower() for p in pairs):labels.append('possible_closed_listing_snapshot')
        if any(p['match_method']=='GMAP_ID_NAME_COORD' and p['name_similarity']<.9 for p in pairs):labels.append('possible_renamed_listing_same_google_id')
    else:
        if entity.get('category') in {'park','beach','garden'}:labels.append('large_geographic_feature_possible')
        if entity.get('category') in {'historic_site','landmark'}:labels.append('historic_site_may_not_be_standalone_business')
        if any(p['match_method']=='CONSTITUENT_FUNCTION_AUDIT_ONLY' for p in pairs):labels.append('constituent_vs_parent_possible')
    if pairs and not any(p['match_confidence']=='HIGH' for p in pairs):labels.append('name_or_location_difference_possible')
    if not pairs:labels.append('no_candidate_within_spatial_or_exact_name_block')
    return ';'.join(labels)


def match_entities(entities,google,conflicting_ids=()):
    index=CandidateIndex(google);summaries=[];pairs=[]
    for entity in entities.to_dict('records'):
        candidates=[evaluate(entity,g) for g in index.candidates(entity)]
        # Only informative nearby name candidates, exact/alias distant candidates or
        # strong addresses enter pair audits; unrelated nearby businesses are not matches.
        candidates=[p for p in candidates if p['name_similarity']>=.50 or (p['address_similarity'] is not None and p['address_similarity']>=.85) or p['match_confidence']!='LOW']
        for p in candidates:
            if p['candidate_gmap_id'] in conflicting_ids:p.update(match_status='REJECTED',match_confidence='LOW',evidence_reason='Conflicting duplicate Google metadata identity')
        high=[p for p in candidates if p['match_confidence']=='HIGH'];medium=[p for p in candidates if p['match_confidence']=='MEDIUM']
        if len(high)==1 and not medium:summary=high[0].copy()
        elif high and (len(high)>1 or medium):
            for p in high+medium:p.update(match_status='AMBIGUOUS',evidence_reason='Multiple plausible Google business identities; no arbitrary winner')
            summary=dict(entity_type=entity['entity_type'],entity_id=entity['entity_id'],entity_name=entity['entity_name'],match_status='AMBIGUOUS',match_confidence='HIGH' if high else 'MEDIUM',match_method='MULTIPLE_PLAUSIBLE_CANDIDATES',evidence_reason='Multiple geographically/name-supported listings')
        elif len(medium)>1:
            for p in medium:p.update(match_status='AMBIGUOUS',evidence_reason='Multiple medium-confidence candidates')
            summary=dict(entity_type=entity['entity_type'],entity_id=entity['entity_id'],entity_name=entity['entity_name'],match_status='AMBIGUOUS',match_confidence='MEDIUM',match_method='MULTIPLE_MEDIUM_CANDIDATES')
        elif medium:summary=medium[0].copy()
        elif candidates:
            best=sorted(candidates,key=lambda p:(-p['name_similarity'],p['distance_meters'] if p['distance_meters'] is not None else float('inf'),p['candidate_gmap_id']))[0]
            summary=best.copy()
        else:summary=dict(entity_type=entity['entity_type'],entity_id=entity['entity_id'],entity_name=entity['entity_name'],match_status='UNMATCHED',match_confidence='LOW',match_method='NO_CANDIDATE')
        summary['diagnostic_flags']=diagnose(entity,candidates) if summary['match_status']!='MATCHED' else ''
        summary.setdefault('candidate_gmap_id',None)
        summaries.append(summary);pairs.extend(candidates)
    summary=pd.DataFrame(summaries);details=pd.DataFrame(pairs)
    collisions=[]
    accepted=summary.loc[summary.match_status.eq('MATCHED')]
    entity_lookup={(e['entity_type'],e['entity_id']):e for e in entities.to_dict('records')}
    for gmap,group in accepted.groupby('candidate_gmap_id'):
        if len(group)<=1:continue
        originals=[entity_lookup[(r.entity_type,r.entity_id)] for r in group.itertuples()]
        duplicate=all(e['alias_normalized']==originals[0]['alias_normalized'] and coordinate_distance(e,originals[0])<=30 for e in originals)
        classification='duplicate_canonical_entity' if duplicate else ('parent_child_attraction_issue' if all(e['entity_type']=='attraction' for e in originals) else 'matching_error_or_shared_representation_unproven')
        for row in group.to_dict('records'):
            collisions.append(dict(row,collision_classification=classification,collision_entity_count=len(group)))
        mask=summary.entity_id.isin(group.entity_id)&summary.entity_type.isin(group.entity_type)
        summary.loc[mask,['match_status','match_method','evidence_reason']]=['AMBIGUOUS','GMAP_ID_COLLISION',classification+'; shared representation is not auto-authorized']
        if not details.empty:
            dmask=details.entity_id.isin(group.entity_id)&details.entity_type.isin(group.entity_type)&details.candidate_gmap_id.eq(gmap)
            details.loc[dmask,['match_status','evidence_reason']]=['AMBIGUOUS',classification]
    return summary,details,pd.DataFrame(collisions,columns=list(summary.columns)+['collision_classification','collision_entity_count'])



def validate_registry(registry, entities):
    if registry[['entity_type','entity_id']].duplicated().any() or registry.gmap_id.isna().any() or registry.gmap_id.duplicated().any():
        raise AssertionError('Registry identity collision')
    valid=set(zip(entities.entity_type,entities.entity_id))
    if not set(zip(registry.entity_type,registry.entity_id)).issubset(valid):
        raise AssertionError('Registry contains unknown canonical identity')
    if not registry.match_confidence.eq('HIGH').all():
        raise AssertionError('Registry contains non-HIGH evidence')


def main():
    metadata=download();restaurants=pd.read_csv(ROOT/'data/processed/restaurants.csv',dtype={'restaurant_id':'string','zipcode':'string'})
    attractions=pd.read_csv(ROOT/'data/processed/attractions.csv',dtype={'attraction_id':'string','source_id':'string'})
    if len(restaurants)!=670 or len(attractions)!=3066:raise ValueError('Unexpected canonical entity counts')
    entities=prepare_entities(restaurants,attractions)
    stats=clean_metadata(RAW/metadata['filename'],entities)
    google=pd.read_csv(CLEAN,dtype={'gmap_id':'string','zipcode':'string'})
    # Identical duplicate IDs represent one Google listing; conflicting variants are blocked.
    google=google.drop_duplicates('gmap_id',keep='first').sort_values('gmap_id')
    summary,details,collisions=match_entities(entities,google.to_dict('records'),set(stats['conflicting_duplicate_gmap_ids']))
    accepted=summary.loc[summary.match_status.eq('MATCHED')&summary.match_confidence.eq('HIGH')].copy()
    registry_columns=['entity_type','entity_id','candidate_gmap_id','google_name','google_address','google_latitude','google_longitude','google_categories','match_method','match_confidence','distance_meters','name_similarity','source']
    registry=accepted.reindex(columns=registry_columns).rename(columns={'candidate_gmap_id':'gmap_id'}).sort_values(['entity_type','entity_id']).reset_index(drop=True)
    validate_registry(registry, entities)
    if REGISTRY.exists():
        old=pd.read_csv(REGISTRY,dtype='string');old_map=old.set_index(['entity_type','entity_id']).gmap_id.to_dict();new_map=registry.set_index(['entity_type','entity_id']).gmap_id.to_dict()
        # Existing associations may never silently change or disappear. New snapshots
        # requiring changes must be audited separately rather than overwriting identity.
        if any(new_map.get(key)!=value for key,value in old_map.items()):raise ValueError('Persistent registry association changed; resolve snapshot/policy changes explicitly')
    ambiguous=details.loc[details.match_status.eq('AMBIGUOUS')].copy() if not details.empty else details
    coverage=[]
    for kind,total in [('restaurant',670),('attraction',3066)]:
        group=summary.loc[summary.entity_type.eq(kind)];high=int(group.match_status.eq('MATCHED').sum())
        coverage.append(dict(entity_type=kind,total_entities=total,high_confidence_matches=high,medium_candidates=int(group.match_confidence.eq('MEDIUM').sum()),
            ambiguous=int(group.match_status.eq('AMBIGUOUS').sum()),unmatched=int(group.match_status.eq('UNMATCHED').sum()),rejected=int(group.match_status.eq('REJECTED').sum()),coverage_percent=100*high/total))
    attraction_summary=attractions.merge(summary.loc[summary.entity_type.eq('attraction')].drop(columns='source',errors='ignore'),left_on='attraction_id',right_on='entity_id',validate='one_to_one')
    def coverage_group(field):
        return attraction_summary.groupby(field,dropna=False).agg(total=('attraction_id','size'),matched=('match_status',lambda s:s.eq('MATCHED').sum())).assign(coverage_percent=lambda f:100*f.matched/f.total).reset_index()
    lines=['# Google Local 2021 entity matching','',
        '[Official source](https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/). Complete New York metadata only; no review download or extraction.',
        'Snapshot covers through September 2021 and is intentionally frozen for reproducibility: fixed offline corpus for experimental subjective-constraint evaluation.',
        '## Retrieval','',json.dumps(metadata,indent=2),'','## Streamed schema/quality inspection','',json.dumps(stats,indent=2),'',
        'Schema counters and duplicate-name/ID counts are disk-backed; JSON lines are streamed without retaining all state metadata. NYC rows are written incrementally, then loaded for spatially indexed matching.',
        'The geographic bounding box is derived from all canonical coordinates plus 0.03 degrees on every edge (~3km latitude). Boundary/New Jersey entities are preserved; New York-only source coverage may limit their matches. Invalid-coordinate metadata is accounted for but excluded from geographic matching.',
        '## Canonical coverage','',markdown_table(pd.DataFrame(coverage)),'',
        'MEDIUM candidates counts canonical audit summaries with medium evidence (including ambiguous medium cases); only unambiguous HIGH enters the registry.',
        '## Accepted match methods','',markdown_table(accepted.groupby(['entity_type','match_method']).size().reset_index(name='entities')),'',
        '## Attraction category coverage','',markdown_table(coverage_group('category')),'','## Attraction subcategory coverage','',markdown_table(coverage_group('subcategory')),'','## Attraction source coverage','',markdown_table(coverage_group('source')),'',
        '## Thresholds and identity policy','',
        'Restaurants: exact name <=30m; exact name <=75m with compatible address or same ZIP; exact name with strong numbered address <=150m or missing coordinates; fuzzy >=0.94 within 30m plus compatible numbered address; strong numbered address + name >=0.85 within 30m. Canonical Google Maps URL ID plus <=75m and name>=0.80 or compatible address is an additional explicit identity anchor.',
        'Attractions: exact name <=75m; deterministic leading-the/ft-fort/st-saint/theatre-theater aliases <=50m; near-exact >=0.95 within 50m; fuzzy>=0.90 within 30m plus category support. Generic names and distinct functional words prevent relaxed HIGH acceptance. Category never replaces name/location.',
        'Address normalization removes only an exact business-name prefix and standardizes common street/direction abbreviations. Compatible address >=0.85; strong >=0.92, both with agreeing leading street number. Explicit conflicting restaurant ZIPs and distances >150m block acceptance.',
        'Spatial cells 0.002 degrees, ±2-cell neighbors with exact <=150m distance filtering; global exact normalized-name and address blocks expose distant candidates. No fuzzy name-only matches.',
        'Multiple HIGH/medium plausible listings remain ambiguous. Any accepted gmap_id reused across canonical entities is blocked for ALL claimants and recorded for inspection. No shared representation is presumed legitimate.',
        'Duplicate canonical identities are flagged by exact normalized alias name and <=30m; other all-attraction collisions are potential parent/child issues, mixed collisions remain matching/shared-representation issues. These are diagnostic classifications, not source-data corrections.',
        'Persistent registry preserves existing entity → gmap_id associations across identical snapshots; conflicting/removal changes fail rather than silently replacing mappings.',
        '## Duplicate Google-ID mapping issues','',markdown_table(collisions),'',
        '## Restaurant nonmatched examples','',markdown_table(summary.loc[summary.entity_type.eq('restaurant')&summary.match_status.ne('MATCHED'),['entity_id','entity_name','match_status','diagnostic_flags']].head(25)),'',
        '## Attraction nonmatched examples','',markdown_table(summary.loc[summary.entity_type.eq('attraction')&summary.match_status.ne('MATCHED'),['entity_id','entity_name','match_status','diagnostic_flags']].head(25)),'',
        'Diagnostics identify possible gaps/name/location differences, not verified closures or absences. Listing-state evidence refers to the historical metadata snapshot.',
        '## Review extraction deferred','',
        'No restaurant_reviews.csv or attraction_reviews.csv is created. Future extraction will retain rating, review_text, timestamp/date, gmap_id and entity_id; reviewer names/profiles are unnecessary and will not enter downstream tables.',
        'Canonical restaurant/attraction data and prior source/enrichment/curation audits remain unchanged.','']
    artifacts={REGISTRY:registry.to_csv(index=False),REPORTS/'google_local_entity_matching_report.md':'\n'.join(lines),
        REPORTS/'google_local_ambiguous_matches.csv':ambiguous.to_csv(index=False),REPORTS/'google_local_gmap_id_collisions.csv':collisions.to_csv(index=False)}
    for kind in ['restaurant','attraction']:
        frame=summary.loc[summary.entity_type.eq(kind)].rename(columns={'entity_id':kind+'_id','entity_name':kind+'_name'})
        artifacts[REPORTS/f'google_local_{kind}_matching.csv']=frame.to_csv(index=False)
    for path,content in artifacts.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    print(pd.DataFrame(coverage).to_string(index=False));print('Raw metadata:',stats['raw_rows'],'NYC candidates:',stats['retained_nyc_rows'],'Registry rows:',len(registry),'collision claims:',len(collisions))

if __name__=='__main__':main()
