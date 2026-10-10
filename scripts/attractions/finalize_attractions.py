"""Deterministic evidence-only attraction curation and persistent final source union."""
import json
from pathlib import Path
import re
from difflib import SequenceMatcher
import pandas as pd
from shapely import wkt
from shapely.geometry import Point
from scripts.shared.restaurant_matching import normalize_name, coordinate_distance
from scripts.attractions.match_attractions_kaggle import CP_DTYPES
from scripts.attractions.explore_attractions import markdown_table

ROOT=Path(__file__).resolve().parents[2]
RULES=ROOT/'data/metadata/attraction_auto_curation_rules.csv'
CATEGORIES=ROOT/'data/metadata/attraction_category_mapping.csv'
REGISTRY=ROOT/'data/metadata/attraction_id_registry.csv'
SCHEMA=['attraction_id','name','category','subcategory','borough','latitude','longitude','source','source_id','is_landmark',
 'landmark_source','landmark_source_id','tourist_relevance_source','facility_type','facility_domain_code','facility_domain_label',
 'commonplace_filter_decision','curation_candidate_id','kaggle_name_support','landmark_evidence']


def present(v):return v is not None and not pd.isna(v) and str(v).strip()!=''


def load_rules(path=RULES):
    rules=pd.read_csv(path,dtype='string',keep_default_na=False)
    if rules.rule_id.duplicated().any() or not rules.signal.isin(['positive','negative','normalization']).all():raise ValueError('Invalid auto rules')
    for pattern in rules.pattern:re.compile(pattern)
    return rules


def normalize_alias(name,rules):
    name=normalize_name(name) or ''
    for rule in rules.loc[rules.signal.eq('normalization')].itertuples():name=re.sub(rule.pattern,rule.category,name)
    return name


def find_alias(candidate,base,rules,geometries=()):
    names={normalize_alias(candidate['candidate_name'],rules)}
    names.update(normalize_alias(e['name'],rules) for e in json.loads(candidate.get('landmark_evidence') or '[]'))
    supported=[]
    for row in base.to_dict('records'):
        if not all(present(v) for v in [candidate.get('latitude'),candidate.get('longitude'),row.get('latitude'),row.get('longitude')]):continue
        distance=coordinate_distance(candidate,row)
        contained=any(g.covers(Point(float(row['longitude']),float(row['latitude']))) for g in geometries)
        if distance>150 and not contained:continue
        other=normalize_alias(row['name'],rules)
        score=max(SequenceMatcher(None,n,other,autojunk=False).ratio() for n in names)
        exact=other in names
        if (score>=.94 and distance<=50) or (exact and (distance<=150 or contained)):
            supported.append(dict(source_id=str(row['source_record_id']),name=row['name'],distance=distance,similarity=score,contained=contained))
    supported.sort(key=lambda e:(-e['similarity'],e['distance'],e['source_id']))
    return supported


def curate(shortlist,base,rules,landmarks):
    lookup={(r['source'],str(r['landmark_source_id'])):r for r in landmarks.to_dict('records')}
    records=[]
    for row in shortlist.to_dict('records'):
        origin=row['candidate_origin'];scope='REVIEW' if origin.startswith('COMMONPLACE_REVIEW') else ('EXCLUDE' if origin.startswith('COMMONPLACE_EXCLUDE') else ('SCENIC' if origin=='UNMATCHED_SCENIC_LANDMARK' else 'INDIVIDUAL'))
        evidence=json.loads(row['landmark_evidence']);geometries=[];eligible=bool(evidence)
        for item in evidence:
            source=lookup.get((item['source'],str(item['source_id'])))
            eligible &= source is not None and source.get('active_designated')==True
            if source is not None and present(source.get('geometry_wkt')):geometries.append(wkt.loads(source['geometry_wkt']))
        name=normalize_name(row['candidate_name']) or ''
        scoped=rules.loc[rules.scope.map(lambda value:scope in value.split('|'))]
        positive=[r for r in scoped.loc[scoped.signal.eq('positive')].itertuples() if re.search(r.pattern,name)]
        negative=[r for r in scoped.loc[scoped.signal.eq('negative')].itertuples() if re.search(r.pattern,name)]
        aliases=find_alias(row,base,rules,geometries)
        decision='DO_NOT_ADD';rule='NO_POSITIVE_SIGNAL';reason='No explicit visitor-facing rule; uncertainty defaults to exclusion';target=None
        if len(aliases)==1:
            decision='ALIAS_OF_EXISTING';rule='STRONG_NAME_LOCATION_ALIAS';reason='Unique exact/near-exact name with close coordinates or exact-name polygon agreement';target=aliases[0]['source_id']
        elif len(aliases)>1:rule='AMBIGUOUS_ALIAS';reason='Multiple strong existing identities; conservative exclusion without forced resolution'
        elif not eligible:rule='INELIGIBLE_LANDMARK';reason='No eligible designated source evidence'
        elif scope=='SCENIC':decision='ADD';rule='DESIGNATED_SCENIC';reason='Eligible curated scenic designation is structured visitor-relevance evidence'
        elif negative:rule='NEGATIVE_SIGNAL';reason='Negative wording blocks additions, including conflicts with positive signals'
        elif scope=='REVIEW' and row.get('landmark_supported')==True:decision='ADD';rule='LANDMARK_SUPPORTED_REVIEW';reason='Confident eligible LPC match to CommonPlace REVIEW without explicit negative infrastructure/residential wording'
        elif positive:decision='ADD';rule=positive[0].rule_id;reason=positive[0].reason
        category=positive[0].category if positive else ('park' if scope=='SCENIC' else 'historic_site')
        records.append(dict(row,auto_decision=decision,auto_rule=rule,auto_reason=reason,alias_target=target,
            positive_signals=';'.join(r.rule_id for r in positive),negative_signals=';'.join(r.rule_id for r in negative),
            alias_evidence=json.dumps(aliases,sort_keys=True),rule_category=category))
    return pd.DataFrame(records).drop(columns=['manual_decision','manual_reason','manual_notes'],errors='ignore')


def assign_ids(keys,registry):
    if registry.canonical_key.duplicated().any() or registry.attraction_id.duplicated().any():raise ValueError('Duplicate registry identities')
    if not registry.attraction_id.str.fullmatch(r'ATTR_\d{4,}').all():raise ValueError('Invalid registry IDs')
    mapping=registry.set_index('canonical_key').attraction_id.to_dict()
    next_number=max([int(value.split('_')[1]) for value in mapping.values()],default=0)+1
    for key in sorted(set(keys)-set(mapping)):
        mapping[key]=f'ATTR_{next_number:04d}';next_number+=1
    result=pd.DataFrame(sorted(mapping.items(),key=lambda item:int(item[1].split('_')[1])),columns=['canonical_key','attraction_id'])
    return mapping,result


def build_union(base,audit,landmark_matches,categories):
    category_map=categories.set_index(['facility_type','facility_domain_code']).category.to_dict()
    rows=[];resolutions=[]
    def matched_evidence(identity):
        return [dict(source=r.landmark_source,source_id=str(r.landmark_source_id),name=r.landmark_name) for r in landmark_matches.loc[landmark_matches.commonplace_source_id.eq(identity)].itertuples() if str(r.match_status).startswith('MATCHED_')]
    for row in base.to_dict('records'):
        identity=str(row['source_record_id']);evidence=matched_evidence(identity)
        rows.append(dict(_key='commonplace:'+identity,name=row['name'],category=category_map[(str(row['facility_type']),str(row['facility_domain_code']))],
            subcategory=row['facility_domain_label'],borough=row['borough'],latitude=row['latitude'],longitude=row['longitude'],source='nyc_commonplace',source_id=identity,
            is_landmark=bool(evidence) or row['facility_domain_label']=='Official Landmark',landmark_source=' | '.join(sorted({e['source'] for e in evidence})) or None,
            landmark_source_id=' | '.join(sorted({e['source_id'] for e in evidence})) or None,tourist_relevance_source='commonplace_include',
            facility_type=row['facility_type'],facility_domain_code=row['facility_domain_code'],facility_domain_label=row['facility_domain_label'],
            commonplace_filter_decision='INCLUDE',curation_candidate_id=None,kaggle_name_support=False,landmark_evidence=json.dumps(evidence,sort_keys=True)))
    for row in audit.loc[audit.auto_decision.eq('ALIAS_OF_EXISTING')].to_dict('records'):
        target=next(r for r in rows if r['source_id']==row['alias_target'] and r['source']=='nyc_commonplace')
        combined=json.loads(target['landmark_evidence'])+json.loads(row['landmark_evidence'])
        target.update(is_landmark=True,landmark_source=' | '.join(sorted({e['source'] for e in combined})),landmark_source_id=' | '.join(sorted({str(e['source_id']) for e in combined})),
            landmark_evidence=json.dumps(combined,sort_keys=True),kaggle_name_support=bool(row.get('kaggle_name_support')))
        resolutions.append(dict(curation_candidate_id=row['curation_candidate_id'],candidate_name=row['candidate_name'],resolution='ALIAS_OF_EXISTING',target_key=target['_key'],reason=row['auto_reason']))
    for row in audit.loc[audit.auto_decision.eq('ADD')].sort_values('curation_candidate_id').to_dict('records'):
        cp=present(row.get('commonplace_source_id'));source='nyc_commonplace' if cp else row['landmark_source'];identity=str(row['commonplace_source_id'] if cp else row['landmark_source_id'])
        key='commonplace:'+identity if cp else source+':'+(str(row['lp_number']) if row['landmark_type']=='SCENIC' else identity)
        candidate_refs={(e['source'],str(e['source_id'])) for e in json.loads(row['landmark_evidence'])}
        duplicate=None
        for existing in rows:
            same_source=existing['_key']==key
            same_name=normalize_name(existing['name'])==normalize_name(row['candidate_name'])
            existing_refs={(e['source'],str(e['source_id'])) for e in json.loads(existing['landmark_evidence'])}
            distance=coordinate_distance(existing,row)
            if same_source or (same_name and (distance<=10 or (bool(candidate_refs&existing_refs) and distance<=50))):duplicate=existing;break
        if duplicate:
            resolutions.append(dict(curation_candidate_id=row['curation_candidate_id'],candidate_name=row['candidate_name'],resolution='FINAL_EXACT_DUPLICATE',target_key=duplicate['_key'],reason='Same source identity, exact normalized name within 10m, or same landmark identity/name within 50m'))
            # Source/landmark provenance of removed additions stays attached to retained identity.
            combined=json.loads(duplicate['landmark_evidence'])+json.loads(row['landmark_evidence'])
            duplicate.update(is_landmark=True,landmark_evidence=json.dumps(combined,sort_keys=True),landmark_source=' | '.join(sorted({e['source'] for e in combined})),landmark_source_id=' | '.join(sorted({str(e['source_id']) for e in combined})))
            continue
        evidence=json.loads(row['landmark_evidence'])
        category=category_map.get((str(row.get('facility_type')),str(row.get('facility_domain_code'))),row['rule_category'])
        if category=='other_attraction':category=row['rule_category']
        rows.append(dict(_key=key,name=row['candidate_name'],category=category,subcategory=row.get('facility_domain_label') if present(row.get('facility_domain_label')) else row['landmark_type'].lower()+'_landmark',
            borough=row['borough'],latitude=row['latitude'],longitude=row['longitude'],source=source,source_id=identity,is_landmark=True,
            landmark_source=' | '.join(sorted({e['source'] for e in evidence})),landmark_source_id=' | '.join(sorted({str(e['source_id']) for e in evidence})),
            tourist_relevance_source=row['auto_rule'],facility_type=row.get('facility_type'),facility_domain_code=row.get('facility_domain_code'),facility_domain_label=row.get('facility_domain_label'),
            commonplace_filter_decision=row.get('commonplace_filter_decision'),curation_candidate_id=row['curation_candidate_id'],kaggle_name_support=row.get('kaggle_name_support',False),landmark_evidence=row['landmark_evidence']))
    return pd.DataFrame(rows),pd.DataFrame(resolutions,columns=['curation_candidate_id','candidate_name','resolution','target_key','reason'])


def main():
    def read(path):return pd.read_csv(ROOT/path,dtype={**CP_DTYPES,'commonplace_source_id':'string','landmark_source_id':'string','lp_number':'string'},keep_default_na=True)
    base=read('data/interim/commonplace_attraction_candidates.csv');classified=read('data/interim/commonplace_attraction_classified.csv')
    if len(base)!=2901 or len(classified)!=20451 or classified.attraction_filter_decision.value_counts().to_dict()!={'INCLUDE':2901,'REVIEW':5790,'EXCLUDE':11760}:raise ValueError('Frozen base/classification changed')
    shortlist=read('data/reports/audit/attractions/final_attraction_curation.csv')
    if len(shortlist)!=257:raise ValueError('Expected preserved 257-row shortlist')
    landmarks=pd.concat([read('data/interim/individual_landmarks_clean.csv'),read('data/interim/scenic_landmarks_clean.csv')],ignore_index=True)
    audit=curate(shortlist,base,load_rules(),landmarks)
    categories=pd.read_csv(CATEGORIES,dtype='string');
    if categories[['facility_type','facility_domain_code']].duplicated().any():raise ValueError('Nonunique category mapping')
    universe,resolutions=build_union(base,audit,read('data/reports/audit/attractions/landmark_commonplace_matching_summary.csv'),categories)
    registry=pd.read_csv(REGISTRY,dtype='string') if REGISTRY.exists() else pd.DataFrame(columns=['canonical_key','attraction_id'])
    mapping,registry=assign_ids(universe._key.tolist(),registry);universe['attraction_id']=universe._key.map(mapping)
    universe=universe.sort_values('attraction_id',key=lambda col:col.str.split('_').str[1].astype(int)).reset_index(drop=True)
    if universe.attraction_id.duplicated().any() or universe._key.duplicated().any():raise AssertionError('Final identity collision')
    if len(universe.loc[universe.commonplace_filter_decision.eq('INCLUDE')])!=2901:raise AssertionError('Automatic base lost')
    universe=universe[SCHEMA]
    audit['alias_target_commonplace_source_id']=audit.alias_target
    audit['alias_target']=audit.alias_target.map(lambda value:mapping.get('commonplace:'+str(value)) if present(value) else None)
    resolutions['target_attraction_id']=resolutions.target_key.map(mapping)
    counts=audit.auto_decision.value_counts().reindex(['ADD','DO_NOT_ADD','ALIAS_OF_EXISTING'],fill_value=0)
    lines=['# Deterministic attraction finalization','',
        'The previous 257-row shortlist is preserved. Blank manual columns are superseded by deterministic auto decisions; no manual input or NEEDS_REVIEW state is required.',
        '## Accounting','',f'CommonPlace base: {len(base)}. Shortlist: {len(audit)}. Final attractions: {len(universe)}.',markdown_table(counts.rename_axis('auto_decision').reset_index(name='candidates')),'',
        '## Additions by origin','',markdown_table(audit.loc[audit.auto_decision.eq('ADD')].groupby('candidate_origin').size().reset_index(name='auto_add')),'',
        '## Additions by final category (after deduplication)','',markdown_table(universe.loc[universe.commonplace_filter_decision.ne('INCLUDE')].groupby('category').size().reset_index(name='added_rows')),'',
        '## Policy','',
        'Patterns, scopes, category signals and fort abbreviation normalization live in attraction_auto_curation_rules.csv. Facility categories use exact type/domain pairs in attraction_category_mapping.csv.',
        'Alias first: unique similarity >=0.94 within 50m; exact normalized name within 150m or exact-name polygon containment. Full candidate/landmark names are checked. Constituent-name suggestions from the earlier audit do not establish aliases. Multiple strong identities default to DO_NOT_ADD.',
        'Then designated Scenic ADD; matched eligible REVIEW ADD unless explicit negative wording; supported EXCLUDE and unmatched Individual require a positive visitor-facing whitelist signal. Negative wording blocks positive/negative conflicts. No name-only Kaggle evidence causes ADD.',
        'Source eligibility is validated against frozen landmark clean tables. Individual currency remains unverified because its source has no current flag. These rule-based choices are experimental visitor-relevance policy, not guarantees of public access.',
        'All 2,901 automatic INCLUDE source identities are retained, including pre-existing same-name/location records. Final duplicate checks remove only additions with same source key, exact normalized name within 10m, or same landmark identity and exact name within 50m; no fuzzy deduplication of the base.',
        'Duplicate/alias provenance is retained in attraction_duplicate_alias_audit.csv and the retained landmark_evidence field. Distinct physical locations remain separate.',
        '## Persistent IDs','',
        'attraction_id_registry.csv maps persistent canonical source keys to ATTR_ IDs. Existing assignments and retired keys remain; new keys append above the highest assigned number. IDs are never reassigned by output position. Scenic keys use LP designation numbers; CommonPlace and Individual use source IDs.',
        '## Final schema','',', '.join(SCHEMA),'',
        'No ratings, prices or opening hours are invented. Original CommonPlace decisions, facility taxonomy and landmark evidence remain provenance fields.',
        '## Duplicate and alias resolutions','',markdown_table(resolutions),'',
        'CommonPlace source/classification/rules, restaurant pipeline, previous shortlist and source audits remain unchanged. No commit or push.','']
    paths={REGISTRY:registry.to_csv(index=False),ROOT/'data/processed/attractions.csv':universe.to_csv(index=False),
        ROOT/'data/reports/audit/attractions/attraction_auto_curation_report.csv':audit.to_csv(index=False),
        ROOT/'data/reports/audit/attractions/attraction_auto_curation_report.md':'\n'.join(lines),
        ROOT/'data/reports/audit/attractions/attraction_duplicate_alias_audit.csv':resolutions.to_csv(index=False)}
    for path,content in paths.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    print(counts.to_string());print('Base:',len(base),'Final:',len(universe),'Removed duplicate additions:',int(resolutions.resolution.eq('FINAL_EXACT_DUPLICATE').sum()));print(universe.category.value_counts().to_string())

if __name__=='__main__':main()
