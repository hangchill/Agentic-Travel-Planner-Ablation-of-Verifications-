"""CommonPlace exploration only: preserve every row; no final IDs or inclusion rules."""
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from download_attractions import RAW_DIR, ROOT, SOURCE_URL, TAXONOMY_URL

FIELDS = {'name':'FEATURE NAME','facility_domain':'FACILITY DOMAINS','facility_type':'FACILITY TYPE',
          'borough_code':'BOROUGH CODE','source_agency':'SOURCE','source_record_id':'OBJECTID',
          'source_place_id':'PLACEID','source_agency_record_id':'SOURCE ID','geometry_raw':'the_geom'}
TOURISM_WORDS = ['museum','gallery','park','garden','zoo','aquarium','historic','landmark','monument',
                 'cultural','theater','theatre','performing','recreation','visitor','attraction']
NON_TOURISM_WORDS = ['school','education','government office','maintenance','utilities','storage',
                     'service facilities','administrative office']


def taxonomy_from_dictionary(text):
    """Decode only documented CommonPlace types and type-dependent domains."""
    type_line=next(line for line in text.splitlines() if line.startswith('| FACILITY_T |'))
    domain_line=next(line for line in text.splitlines() if line.startswith('| FACI_DOM |'))
    types={}
    for part in type_line.split('<br>'):
        part=part.split('|')[0]
        match=re.fullmatch(r'\s*(\d+)\s*=\s*([^|]+?)\s*',part)
        if match:types[match[1]]=match[2]
    if len(types)!=13:raise ValueError('Source dictionary type schema changed; inspect before decoding')
    labels={v:k for k,v in types.items()};current=None;rows=[]
    for part in domain_line.split('<br>'):
        part=part.split('|')[0].strip()
        if part in labels:current=labels[part];continue
        match=re.fullmatch(r'(\d+)\s+(?:=\s*)?([^|]+)',part)
        if match and current:
            rows.append({'facility_type':current,'facility_type_label':types[current],
                         'facility_domain':match[1],'facility_domain_label':match[2].strip(),'source_url':TAXONOMY_URL})
    if not rows:raise ValueError('No documented domains could be decoded')
    return pd.DataFrame(rows)


def clean_exploration(raw,taxonomy):
    missing=set(FIELDS.values())-set(raw.columns)
    if missing:raise ValueError(f'Missing actual source fields: {missing}')
    out=raw.rename(columns={v:k for k,v in FIELDS.items()})[list(FIELDS)].copy()
    coordinates=out.geometry_raw.str.extract(r'^POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)$')
    out['longitude']=pd.to_numeric(coordinates[0],errors='coerce')
    out['latitude']=pd.to_numeric(coordinates[1],errors='coerce')
    out['source_dataset']='nyc_commonplace'
    # Borough names are documented source code decodes; unsupported code 8 remains unlabeled.
    out['borough']=out.borough_code.map({'1':'Manhattan','2':'Bronx','3':'Brooklyn','4':'Queens','5':'Staten Island'})
    out=out.merge(taxonomy.drop(columns=['source_url','facility_type_label']),on=['facility_type','facility_domain'],how='left',validate='many_to_one',sort=False)
    out['facility_type_label']=out.facility_type.map(taxonomy[['facility_type','facility_type_label']].drop_duplicates().set_index('facility_type').facility_type_label)
    # All source columns retained verbatim as text, including IDs, geometry and taxonomy codes.
    for column in raw.columns:out['raw_'+column]=raw[column].array
    assert len(out)==len(raw)
    assert out.source_record_id.tolist()==raw['OBJECTID'].tolist()
    return out


def frequencies(series,label):
    counts=series.fillna('(missing)').value_counts(dropna=False).rename_axis(label).reset_index(name='count')
    counts['percentage']=counts['count']/len(series)*100
    return counts.sort_values(['count',label],ascending=[False,True]).reset_index(drop=True)


def category_masks(clean):
    # Only names of decoded categories actually present, never feature-name inference.
    labels=clean[['facility_type_label','facility_domain_label']].fillna('').agg(' '.join,axis=1)
    candidate=labels.str.contains('|'.join(TOURISM_WORDS),case=False,regex=True)
    non_tourist=labels.str.contains('|'.join(NON_TOURISM_WORDS),case=False,regex=True)
    return candidate,non_tourist


def deterministic_samples(clean,field,groups=None,n=5):
    frames=[]
    columns=['name','facility_domain','facility_domain_label','facility_type','facility_type_label',
             'borough','borough_code','latitude','longitude','source_record_id']
    for value,group in clean.groupby(field,dropna=False,sort=True):
        if groups is not None and value not in groups:continue
        frames.append(group.sort_values(['source_record_id','name'],kind='stable').sample(min(n,len(group)),random_state=42)[columns])
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=columns)


def markdown_table(frame):
    def display(value):return '' if pd.isna(value) else str(value).replace('|','\\|').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(map(str,frame.columns))+' |',
        '| '+' | '.join(['---']*len(frame.columns))+' |',
        *['| '+' | '.join(display(v) for v in row)+' |' for row in frame.itertuples(index=False,name=None)]])


def main():
    raw_file=RAW_DIR/'commonplace.csv';metadata=json.loads((RAW_DIR/'retrieval_metadata.json').read_text())
    if hashlib.sha256(raw_file.read_bytes()).hexdigest()!=metadata['raw_sha256']:raise ValueError('Raw cache checksum mismatch')
    raw=pd.read_csv(raw_file,dtype='string',keep_default_na=False).replace('',pd.NA)
    inferred=pd.read_csv(raw_file)
    schema=pd.DataFrame({'column':raw.columns,'inferred_dtype':[str(t) for t in inferred.dtypes],
                         'missing_count':raw.isna().sum().to_numpy(),'missing_percentage':raw.isna().mean().to_numpy()*100})
    taxonomy=taxonomy_from_dictionary((RAW_DIR/'source_dictionary.md').read_text())
    clean=clean_exploration(raw,taxonomy)
    domains=frequencies(clean.facility_domain,'facility_domain')
    types=frequencies(clean.facility_type,'facility_type')
    type_labels=taxonomy[['facility_type','facility_type_label']].drop_duplicates()
    types=types.merge(type_labels,on='facility_type',how='left',validate='one_to_one')
    boroughs=frequencies(clean.borough_code,'borough_code')
    boroughs['borough']=boroughs.borough_code.map({'1':'Manhattan','2':'Bronx','3':'Brooklyn','4':'Queens','5':'Staten Island'})
    combos=clean.groupby(['facility_domain','facility_type','facility_domain_label','facility_type_label'],dropna=False).size().reset_index(name='count')
    combos=combos.sort_values(['count','facility_type','facility_domain'],ascending=[False,True,True]).reset_index(drop=True)
    cross=pd.crosstab(clean.facility_domain.fillna('(missing)'),clean.facility_type.fillna('(missing)'))
    candidate,unlikely=category_masks(clean)
    same_location=clean.name.notna() & clean.latitude.notna() & clean.longitude.notna() & clean.duplicated(['name','latitude','longitude'],keep=False)
    location_counts=clean.loc[clean.name.notna() & clean.latitude.notna() & clean.longitude.notna()].groupby('name').apply(lambda g:g[['latitude','longitude']].drop_duplicates().shape[0],include_groups=False)
    different_location=clean.name.isin(location_counts[location_counts.gt(1)].index)
    valid=(clean.latitude.between(-90,90) & clean.longitude.between(-180,180)).fillna(False)
    coord_present=clean.latitude.notna() & clean.longitude.notna()
    duplicate_names=clean.name.notna() & clean.name.duplicated(keep=False)
    near_names=clean.name.str.strip().str.casefold().str.replace(r'\s+',' ',regex=True)
    near_groups=clean.assign(name_normalized=near_names).groupby('name_normalized').name.nunique()
    near_rows=near_names.isin(near_groups.loc[near_groups.gt(1)].index)
    report_dir=ROOT/'data/reports';report_dir.mkdir(parents=True,exist_ok=True)
    (ROOT/'data/interim').mkdir(parents=True,exist_ok=True)
    clean.to_csv(ROOT/'data/interim/commonplace_attractions_clean.csv',index=False)
    taxonomy.to_csv(ROOT/'data/metadata/commonplace_taxonomy.csv',index=False)
    outputs={'commonplace_schema.csv':schema,'commonplace_facility_domain_counts.csv':domains,
        'commonplace_facility_type_counts.csv':types,'commonplace_domain_type_counts.csv':combos,
        'commonplace_domain_samples.csv':deterministic_samples(clean,'facility_domain'),
        'commonplace_type_samples.csv':deterministic_samples(clean,'facility_type',set(types.head(30).facility_type)),
        'commonplace_same_name_same_location.csv':clean.loc[same_location,list(FIELDS)+['latitude','longitude']],
        'commonplace_same_name_different_location.csv':clean.loc[different_location,list(FIELDS)+['latitude','longitude']],
        'commonplace_near_duplicate_names.csv':clean.loc[near_rows,list(FIELDS)+['latitude','longitude']]}
    for name,frame in outputs.items():frame.to_csv(report_dir/name,index=False)
    cross.to_csv(report_dir/'commonplace_domain_type_crosstab.csv')
    overview={'row_count':len(raw),'raw_column_count':len(raw.columns),'interim_column_count':len(clean.columns),
        'exact_duplicate_rows':int(raw.duplicated().sum()),'unique_names':int(clean.name.nunique()),
        'rows_with_duplicate_names':int(duplicate_names.sum()),'duplicate_name_groups':int(clean.loc[duplicate_names,'name'].nunique()),
        'same_name_same_location_rows':int(same_location.sum()),'same_name_different_location_rows':int(different_location.sum()),
        'same_name_multiple_location_groups':int(location_counts.gt(1).sum()),
        'near_duplicate_name_variant_groups':int(near_groups.gt(1).sum()),
        'duplicate_objectid_rows':int(clean.source_record_id.duplicated().sum()),
        'duplicate_placeid_rows':int(clean.source_place_id.duplicated().sum()),
        'duplicate_agency_sourceid_rows':int(clean.loc[clean.source_agency_record_id.notna()].duplicated(['source_agency','source_agency_record_id']).sum()),
        'non_missing_complexid_rows':int(raw.COMPLEXID.notna().sum()),
        'shared_complexid_groups':int(raw.COMPLEXID.value_counts().gt(1).sum()),
        'coordinate_complete_rows':int(coord_present.sum()),'invalid_coordinate_rows':int((clean.geometry_raw.notna() & ~valid).sum()),
        'facility_domain_codes':int(clean.facility_domain.nunique()),'facility_types':int(clean.facility_type.nunique()),
        'unresolved_taxonomy_rows':int(clean.facility_domain_label.isna().sum()),
        'unsupported_borough_code_rows':int((clean.borough_code.notna() & clean.borough.isna()).sum()),
        'candidate_tourist_rows':int(candidate.sum()),'candidate_unlikely_rows':int(unlikely.sum())}
    lines=['# CommonPlace exploration — no canonical attractions dataset','',
        f'Source: [NYC Open Data CommonPlace]({SOURCE_URL}).',
        f'Dictionary: [CityOfNewYork metadata]({TAXONOMY_URL}).',
        'Only CommonPlace was downloaded; the dictionary documents this same source. No other POI source is merged.',
        f'Retrieval: `{metadata["retrieved_at"]}`; raw SHA-256: `{metadata["raw_sha256"]}`.','',
        '## Overview','',markdown_table(pd.DataFrame(overview.items(),columns=['metric','value'])),'',
        '## Actual schema and missingness','',markdown_table(schema),'',
        'FEATURE NAME → name; FACILITY DOMAINS → facility_domain code; FACILITY TYPE → facility_type code;',
        'BOROUGH CODE → borough_code; SOURCE → source_agency; OBJECTID → source_record_id;',
        'PLACEID → source_place_id; SOURCE ID → source_agency_record_id; the_geom → raw WKT and longitude/latitude.',
        'Raw codes and all 21 raw columns are retained. No missing values are imputed. No rows are filtered or deduplicated.',
        'Coordinates are parsed from the source WKT POINT longitude/latitude values; no geocoding is used.','',
        '## Facility taxonomy','',
        'Important: FACILITY TYPE is the broad category; FACILITY DOMAINS is a subtype code scoped to that type.',
        'Domain code 1 has different meanings across types. Never interpret a domain code independently.',
        'Decoded labels are source documentation, not final attraction categories. Unmapped codes remain null.',
        'The dictionary is older metadata; unresolved codes and future schema drift require review.','',
        '### Raw domain codes (all values)','',markdown_table(domains),'',
        '### Broad facility types (all values)','',markdown_table(types),'',
        '### Largest type-dependent domain combinations','',markdown_table(combos.head(30)),'',
        '## Borough distribution','',markdown_table(boroughs),'',
        'Unsupported borough code 8 is retained without inventing a borough name.','',
        '## Duplicate and feature identity exploration','',
        'Exact rows, names, OBJECTID, PLACEID, SOURCE+SOURCE ID and COMPLEXID are checked separately.',
        'Same-name coordinate equality is exact, with no distance tolerance or canonical merging.',
        'Repeated names may represent branches, constituents or generic labels. Shared COMPLEXID indicates grouping, not proof of identical features.',
        'Case/whitespace-only name variants are surfaced separately without merging; fuzzy/geographic identity resolution remains future work.','',
        '### Same name, same location examples','',markdown_table(clean.loc[same_location,['name','source_record_id','source_place_id','latitude','longitude']].head(10)),'',
        '### Same name, different location examples','',markdown_table(clean.loc[different_location,['name','source_record_id','source_place_id','latitude','longitude']].head(10)),'',
        '## Candidate tourist-relevant subset','',
        'Keyword matching uses only documented category labels actually observed in the source, not feature names.',
        'Keywords: '+', '.join(TOURISM_WORDS)+'. This is exploration only, not a final inclusion rule.',
        f'Candidate rows: {int(candidate.sum())}.','',
        'Candidate domain distribution:',markdown_table(frequencies(clean.loc[candidate,'facility_domain'],'facility_domain')),'',
        'Candidate type distribution:',markdown_table(frequencies(clean.loc[candidate,'facility_type_label'],'facility_type_label')),'',
        'Candidate categories:',markdown_table(combos.loc[combos.facility_type_label.str.contains('|'.join(TOURISM_WORDS),case=False) | combos.facility_domain_label.fillna('').str.contains('|'.join(TOURISM_WORDS),case=False)]),'',
        'Candidate examples:',markdown_table(clean.loc[candidate,['name','facility_type_label','facility_domain_label','borough','latitude','longitude']].head(10)),'',
        '## Exploratory potentially non-tourist categories','',
        'Keywords: '+', '.join(NON_TOURISM_WORDS)+'. Only actual documented categories are surfaced; no exclusion is applied.',
        f'Rows: {int(unlikely.sum())}.',markdown_table(frequencies(clean.loc[unlikely,'facility_domain_label'],'facility_domain_label')),'',
        '## Observations for future canonical design','',
        'CommonPlace covers far more than visitor attractions; counts alone do not establish tourist completeness.',
        'Paired taxonomy codes, repeated names, complex constituents and out-of-borough records require review.',
        'Source fields provide no opening hours, admission prices or visitor ratings; no such metadata was inferred.',
        'Source IDs are retained for traceability, not designated final attraction IDs.',
        'Deterministic samples use five rows per observed domain code/type, random_state=42, after sorting source IDs.',
        'No final inclusion/exclusion rule, final attraction ID or processed attraction table is produced.','']
    (report_dir/'commonplace_exploration_report.md').write_text('\n'.join(lines))
    print('Actual columns:',raw.columns.tolist());print(schema.to_string(index=False));print(json.dumps(overview,indent=2))


if __name__=='__main__':main()
