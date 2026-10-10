"""Apply the single CommonPlace candidate-rule CSV; no deduplication or final IDs."""
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from scripts.attractions.explore_attractions import markdown_table, frequencies

ROOT = Path(__file__).resolve().parents[2]
CLEAN_FILE = ROOT/'data/interim/commonplace_attractions_clean.csv'
RULES_FILE = ROOT/'data/metadata/commonplace_attraction_filter.csv'
TAXONOMY_FILE = ROOT/'data/metadata/commonplace_taxonomy.csv'
KEYS = ['facility_type','facility_domain_code']
DECISIONS = ['INCLUDE','REVIEW','EXCLUDE','UNMAPPED']
SOURCE_DTYPES = {field:'string' for field in ['facility_type','facility_domain','borough_code',
    'source_record_id','source_place_id','source_agency_record_id']}
AUDIT_FIELDS = ['facility_type','facility_domain_code','facility_domain_label','row_count','decision','reason','example_names']


def load_rules(path=RULES_FILE,taxonomy_path=TAXONOMY_FILE):
    rules=pd.read_csv(path,dtype='string',keep_default_na=False)
    if rules.columns.tolist()!=[*KEYS,'facility_domain_label','decision','reason']:raise ValueError('Invalid rule schema')
    if rules[KEYS].duplicated().any() or rules.eq('').any().any():raise ValueError('Duplicate or empty rule fields')
    if not rules.decision.isin(DECISIONS[:-1]).all():raise ValueError('Invalid metadata decision')
    taxonomy=pd.read_csv(taxonomy_path,dtype='string').rename(columns={'facility_domain':'facility_domain_code'})
    labels=taxonomy.set_index(KEYS).facility_domain_label.to_dict()
    for row in rules.itertuples(index=False):
        key=(row.facility_type,row.facility_domain_code);expected=labels.get(key)
        if expected is None:
            if row.facility_domain_label!='UNKNOWN_UNDOCUMENTED' or row.decision!='REVIEW':
                raise ValueError('Undocumented pairs must be labelled UNKNOWN_UNDOCUMENTED and REVIEW')
        elif row.facility_domain_label!=expected:raise ValueError(f'Rule label conflicts with source taxonomy: {key}')
    return rules


def classify_rows(clean,rules):
    """Preserve all source fields/order; metadata alone determines selection."""
    if rules[KEYS].duplicated().any():raise ValueError('Nonunique taxonomy rules')
    if not rules.decision.isin(DECISIONS[:-1]).all():raise ValueError('Invalid decision')
    rows=clean.copy()
    rows['facility_type']=rows.facility_type.astype('string')
    rows['facility_domain_code']=rows.facility_domain.astype('string')
    right=rules.rename(columns={'facility_domain_label':'filter_domain_label',
        'decision':'attraction_filter_decision','reason':'attraction_filter_reason'})
    rows=rows.merge(right,on=KEYS,how='left',sort=False,validate='many_to_one')
    rows['attraction_filter_decision']=rows.attraction_filter_decision.fillna('UNMAPPED')
    rows['attraction_filter_reason']=rows.attraction_filter_reason.fillna('No rule exists for this exact type/domain pair; manual rule review required.')
    # Retain the original decoded source label and a separate policy label for honest unknowns.
    rows['facility_domain_label_raw']=rows.facility_domain_label
    rows['facility_domain_label']=rows.filter_domain_label.combine_first(rows.facility_domain_label)
    rows=rows.drop(columns='filter_domain_label')
    if len(rows)!=len(clean) or rows.source_record_id.tolist()!=clean.source_record_id.tolist():
        raise AssertionError('Source rows or order changed')
    assert rows.attraction_filter_decision.isin(DECISIONS).all()
    return rows


def sort_pool(frame):
    ordered=frame.assign(_type_order=pd.to_numeric(frame.facility_type,errors='coerce'),
        _domain_order=pd.to_numeric(frame.facility_domain_code,errors='coerce'))
    return ordered.sort_values(['_type_order','_domain_order','name','source_record_id'],kind='stable',na_position='last').drop(columns=['_type_order','_domain_order']).reset_index(drop=True)


def subtype_audit(classified,rules,decision):
    selected=classified.loc[classified.attraction_filter_decision.eq(decision)]
    records=[]
    # Include zero-row configured subtypes; no hidden rules omitted from the audit.
    for row in rules.loc[rules.decision.eq(decision)].itertuples(index=False):
        group=selected.loc[selected.facility_type.eq(row.facility_type) & selected.facility_domain_code.eq(row.facility_domain_code)]
        sample=group.sort_values(['source_record_id','name'],kind='stable').sample(n=min(5,len(group)),random_state=42)
        records.append(dict(facility_type=row.facility_type,facility_domain_code=row.facility_domain_code,
            facility_domain_label=row.facility_domain_label,row_count=len(group),decision=decision,reason=row.reason,
            example_names=json.dumps(sample.name.fillna('').tolist(),ensure_ascii=False)))
    return pd.DataFrame(records,columns=AUDIT_FIELDS).sort_values(['row_count','facility_type','facility_domain_code'],ascending=[False,True,True]).reset_index(drop=True)


def candidate_name_flags(candidates):
    """Exploratory flags do not affect inclusion; keywords are never filter rules."""
    patterns={'school_like':r'\b(?:school|academy|college|university|ps\s*\d+|is\s*\d+)\b',
        'office_like':r'\b(?:office|administration|administrative|headquarters)\b',
        'maintenance_service':r'\b(?:maintenance|storage|utility|utilities|service|comfort station|pump|depot)\b',
        'facility_like':r'\b(?:facility|building|station|annex|yard|garage|warehouse)\b'}
    result=candidates.copy();reasons=[]
    generic={'park','garden','museum','playground','pool','sports','landmark','point of interest','other','unknown'}
    for name in result.name.fillna(''):
        normalized=' '.join(str(name).casefold().split());flags=[]
        if normalized in generic or len(normalized)<=3:flags.append('very_generic_name')
        for label,pattern in patterns.items():
            if re.search(pattern,normalized):flags.append(label)
        reasons.append(';'.join(flags))
    result['name_review_flags']=reasons
    return result.loc[result.name_review_flags.ne('')].reset_index(drop=True)


def duplicate_statistics(pool):
    repeated=pool.name.notna() & pool.name.duplicated(keep=False)
    located=pool.loc[pool.name.notna() & pool.latitude.notna() & pool.longitude.notna()]
    same=located.duplicated(['name','latitude','longitude'],keep=False)
    locations=located.groupby('name').apply(lambda group:len(group[['latitude','longitude']].drop_duplicates()),include_groups=False)
    multiple=locations.loc[locations.gt(1)].index
    return {'unique_candidate_names':int(pool.name.nunique()),'repeated_name_groups':int(pool.loc[repeated,'name'].nunique()),
        'rows_with_repeated_names':int(repeated.sum()),'same_name_same_coordinates_rows':int(same.sum()),
        'same_name_different_coordinates_groups':len(multiple),'same_name_different_coordinates_rows':int(located.name.isin(multiple).sum())}


def build_artifacts(clean,rules):
    classified=classify_rows(clean,rules)
    pools={decision:sort_pool(classified.loc[classified.attraction_filter_decision.eq(decision)]) for decision in DECISIONS}
    if sum(len(pool) for pool in pools.values())!=len(clean):raise AssertionError('Classification accounting failed')
    audits={decision:subtype_audit(classified,rules,decision) for decision in DECISIONS[:-1]}
    return classified,pools,audits,candidate_name_flags(pools['INCLUDE'])


def main():
    input_hash=hashlib.sha256(CLEAN_FILE.read_bytes()).hexdigest()
    clean=pd.read_csv(CLEAN_FILE,dtype=SOURCE_DTYPES)
    rules=load_rules();classified,pools,audits,name_review=build_artifacts(clean,rules)
    if len(classified)!=20451:raise ValueError('Expected frozen CommonPlace exploration snapshot with 20,451 rows')
    interim=ROOT/'data/interim';reports=ROOT/'data/reports/audit/attractions'
    paths={interim/'commonplace_attraction_classified.csv':classified.to_csv(index=False),
        interim/'commonplace_attraction_candidates.csv':pools['INCLUDE'].to_csv(index=False),
        reports/'commonplace_candidate_name_review.csv':name_review.to_csv(index=False)}
    for decision,filename in [('INCLUDE','included'),('REVIEW','review'),('EXCLUDE','excluded')]:
        paths[reports/f'commonplace_{filename}_subtypes.csv']=audits[decision].to_csv(index=False)
    included=pools['INCLUDE'];review=pools['REVIEW'];stats=duplicate_statistics(included)
    counts=pd.DataFrame([(decision,len(pools[decision])) for decision in DECISIONS],columns=['decision','row_count'])
    unknown=review.loc[review.facility_domain_label.eq('UNKNOWN_UNDOCUMENTED')]
    borough=frequencies(included.borough.fillna('missing/other'),'borough')
    lines=['# First CommonPlace attraction candidate universe','',
        'Candidate policy only: no final attraction IDs, processed attractions table, deduplication or additional POI sources.',
        'The metadata CSV is the single source of truth; joins use exact facility_type + facility_domain_code.',
        'REVIEW is never automatically promoted. Missing rules become UNMAPPED, never implicitly included/excluded.',
        f'Total source rows: {len(clean)}. Source/interim SHA-256: `{input_hash}`.',
        f'Rule SHA-256: `{hashlib.sha256(RULES_FILE.read_bytes()).hexdigest()}`.','',
        '## Decision accounting','',markdown_table(counts),'',
        '## Included subtypes','',markdown_table(audits['INCLUDE']),'',
        'Included broad facility types:',markdown_table(frequencies(included.facility_type_label,'facility_type_label')),'',
        '## Review subtypes','',markdown_table(audits['REVIEW']),'',
        '## Excluded subtypes','',markdown_table(audits['EXCLUDE']),'',
        '## Included borough distribution','',markdown_table(borough),'',
        '## Included examples','',markdown_table(included[['name','facility_type_label','facility_domain_label','borough','latitude','longitude']].head(20)),'',
        '## Borderline review examples','',markdown_table(review[['name','facility_type_label','facility_domain_label','borough','latitude','longitude']].head(20)),'',
        '## Undocumented taxonomy','',
        f'UNKNOWN_UNDOCUMENTED rows: {len(unknown)}. Their source subtype labels remain null in facility_domain_label_raw.',
        'The current undocumented pair is type 13/domain 5, classified REVIEW without inventing a meaning.',
        markdown_table(unknown[['facility_type','facility_domain_code','name','borough','latitude','longitude']].head(10)),'',
        '## Candidate duplicate-name analysis','',markdown_table(pd.DataFrame(stats.items(),columns=['metric','value'])),'',
        'Exact name/coordinate equality is used; no geographic tolerance, deduplication or canonical identity inference.',
        '## Candidate name inspection','',f'Flagged INCLUDE rows: {len(name_review)}. Flags are exploratory; none are removed.',
        markdown_table(name_review[['name','facility_domain_label','borough','name_review_flags']].head(30)),'',
        '## Policy limits','',
        'Library, cultural center/other, golf courses, playgrounds, pools, recreational centers/other, religious sites,',
        'markets/commercial centers, ferry landings, marinas, piers, bridges, water features and miscellaneous',
        'cemetery/morgue/other remain REVIEW. These are provisional taxonomy decisions, not visitor-quality judgments.',
        'Government and other ordinary facility categories can contain visitor-oriented individual features; inspect exclusion samples before finalizing policy.',
        'Examples use at most five source rows per configured subtype, seeded with 42 after sorting source IDs.',
        'All source identifiers/raw fields are retained. Restaurant inputs and outputs are not touched.','']
    paths[reports/'commonplace_attraction_filter_report.md']='\n'.join(lines)
    for path,content in paths.items():
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    if hashlib.sha256(CLEAN_FILE.read_bytes()).hexdigest()!=input_hash:raise AssertionError('Clean source changed')
    print(counts.to_string(index=False));print('\nIncluded subtypes:');print(audits['INCLUDE'].to_string(index=False))
    print('\nReview subtypes:');print(audits['REVIEW'][['facility_type','facility_domain_code','facility_domain_label','row_count']].to_string(index=False))
    print('\nBoroughs:');print(borough.to_string(index=False));print(json.dumps(stats,indent=2))
    print(f'Undocumented review rows: {len(unknown)}; name-review flags: {len(name_review)}')


if __name__=='__main__':main()
