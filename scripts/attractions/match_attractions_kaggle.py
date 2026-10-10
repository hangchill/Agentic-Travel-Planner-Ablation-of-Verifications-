"""Audit-only curated tourist signal; never change CommonPlace decisions or identities."""
from difflib import SequenceMatcher
import hashlib
import json
import math
from pathlib import Path
import re

import pandas as pd

from scripts.attractions.download_attractions import ROOT, KAGGLE_RAW_DIR
from scripts.shared.restaurant_matching import normalize_name, normalize_address, normalize_zipcode, coordinate_distance
from scripts.attractions.explore_attractions import markdown_table

FUZZY_THRESHOLD = 0.94
DISTANCE_THRESHOLD = 50
STATUSES = ['MATCHED_INCLUDE','MATCHED_REVIEW','MATCHED_EXCLUDE','UNMATCHED','AMBIGUOUS','REJECTED']
CP_DTYPES = {field:'string' for field in ['facility_type','facility_domain','facility_domain_code','borough_code',
    'source_record_id','source_place_id','source_agency_record_id']}
REPORT_COLUMNS = ['kaggle_row_id','kaggle_name','kaggle_address','kaggle_zipcode','commonplace_source_id',
    'commonplace_name','commonplace_facility_type','commonplace_facility_type_label','commonplace_domain_code',
    'commonplace_domain_label','commonplace_borough','commonplace_filter_decision','commonplace_address',
    'commonplace_zipcode','distance_meters','match_method','match_confidence','match_status','matching_pass','evidence_reason']


def present(value):
    return value is not None and not pd.isna(value) and str(value).strip()!=''


def address_zip(value):
    if not present(value):return None
    # Only explicit NY/NYC address ZIP context; avoid mistaking building numbers for ZIPs.
    match=re.search(r'\b(?:NY|New York)\s+(\d{5})(?:-\d{4})?\b',str(value),re.I)
    return match[1] if match else None


def clean_kaggle(raw,filename='fixture',sheet='fixture',start=0):
    expected=['Tourist_Spot','Address','Zipcode']
    if raw.columns.tolist()!=expected:raise ValueError(f'Actual Kaggle schema differs; inspect before matching: {raw.columns.tolist()}')
    out=pd.DataFrame(index=raw.index)
    out['kaggle_row_id']=[f'KAGGLE_ROW_{start+i+1:04d}' for i in range(len(raw))]
    out['name_raw']=raw.Tourist_Spot;out['address_raw']=raw.Address;out['zipcode_raw']=raw.Zipcode
    out['name']=raw.Tourist_Spot.astype('string').str.strip();out['name_normalized']=out.name.map(normalize_name)
    out['address']=raw.Address.astype('string').str.strip();out['address_normalized']=out.address.map(normalize_address)
    out['zipcode']=raw.Zipcode.map(normalize_zipcode).astype('string')
    derived=out.address.map(address_zip).astype('string')
    missing=raw.Zipcode.isna() | raw.Zipcode.astype('string').str.strip().eq('').fillna(True)
    out.loc[missing,'zipcode']=derived.loc[missing]
    out['zipcode_origin']='source_zipcode'
    out.loc[missing & derived.notna(),'zipcode_origin']='explicit_address_zip'
    out.loc[out.zipcode.isna(),'zipcode_origin']=pd.NA
    out['source']='kaggle_tourist_locations';out['source_file']=filename;out['source_sheet']=sheet
    out['source_row_number']=list(range(2,2+len(raw)))
    return out.reset_index(drop=True)


def load_kaggle(raw_dir=KAGGLE_RAW_DIR):
    metadata=json.loads((raw_dir/'retrieval_metadata.json').read_text());frames=[];schema=[];offset=0
    for info in metadata['files']:
        path=raw_dir/info['filename']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Kaggle raw checksum changed')
        raw=(pd.read_excel(path,sheet_name=info['sheet'],dtype='string',keep_default_na=False)
            if path.suffix.lower()=='.xlsx' else pd.read_csv(path,dtype='string',keep_default_na=False)).replace('',pd.NA)
        if len(raw)!=info['row_count']:raise ValueError('Kaggle cached row count differs')
        frames.append(clean_kaggle(raw,path.name,info['sheet'],offset));offset+=len(raw)
        schema.append({**info,'duplicate_name_rows':int(raw.Tourist_Spot.duplicated(keep=False).sum()),
                       'duplicate_name_groups':int(raw.loc[raw.Tourist_Spot.duplicated(keep=False),'Tourist_Spot'].nunique())})
    return pd.concat(frames,ignore_index=True),metadata,schema


def prepare_commonplace(frame):
    records=[]
    for row in frame.to_dict('records'):
        row['name_normalized']=normalize_name(row['name'])
        # Missing geography is never inferred from borough or opaque source/address-point IDs.
        row['zipcode_normalized']=normalize_zipcode(row.get('zipcode'))
        row['address_normalized']=normalize_address(row.get('address'))
        records.append(row)
    index={}
    for row in records:
        if row['name_normalized']:index.setdefault(row['name_normalized'],[]).append(row)
    return index


def geographic_evidence(k,c):
    same_zip=present(k.get('zipcode')) and present(c.get('zipcode_normalized')) and k['zipcode']==c['zipcode_normalized']
    same_address=present(k.get('address_normalized')) and present(c.get('address_normalized')) and k['address_normalized']==c['address_normalized']
    distance=None
    values=[k.get('latitude'),k.get('longitude'),c.get('latitude'),c.get('longitude')]
    if all(present(v) for v in values):
        try:
            values=list(map(float,values))
            if all(math.isfinite(v) for v in values) and -90<=values[0]<=90 and -90<=values[2]<=90 and -180<=values[1]<=180 and -180<=values[3]<=180:
                distance=coordinate_distance(dict(latitude=values[0],longitude=values[1]),dict(latitude=values[2],longitude=values[3]))
        except (ValueError,TypeError):pass
    conflict=present(k.get('zipcode')) and present(c.get('zipcode_normalized')) and k['zipcode']!=c['zipcode_normalized']
    if distance is not None and distance>150:conflict=True
    return same_zip,same_address,distance,conflict


def name_candidates(name,index,threshold):
    if name is None:return []
    result=[]
    for other,rows in index.items():
        if other==name:
            result.extend((row,True,1.0) for row in rows);continue
        # Necessary length and character-overlap bounds avoid expensive comparisons.
        if 2*min(len(name),len(other))/(len(name)+len(other))<threshold:continue
        matcher=SequenceMatcher(None,name,other,autojunk=False)
        if matcher.quick_ratio()<threshold:continue
        score=matcher.ratio()
        if score>=threshold:result.extend((row,False,score) for row in rows)
    return result


def report_row(k,c=None,method='no_candidate',confidence=None,status='UNMATCHED',pass_name='primary',reason='',distance=None):
    c={} if c is None else c
    return dict(kaggle_row_id=k['kaggle_row_id'],kaggle_name=k['name'],kaggle_address=k.get('address'),kaggle_zipcode=k.get('zipcode'),
        commonplace_source_id=c.get('source_record_id'),commonplace_name=c.get('name'),commonplace_facility_type=c.get('facility_type'),
        commonplace_facility_type_label=c.get('facility_type_label'),commonplace_domain_code=c.get('facility_domain_code',c.get('facility_domain')),
        commonplace_domain_label=c.get('facility_domain_label'),commonplace_borough=c.get('borough'),
        commonplace_filter_decision=c.get('attraction_filter_decision'),commonplace_address=c.get('address'),
        commonplace_zipcode=c.get('zipcode_normalized'),distance_meters=distance,match_method=method,
        match_confidence=confidence,match_status=status,matching_pass=pass_name,evidence_reason=reason)


def match_pass(k,index,threshold=FUZZY_THRESHOLD,pass_name='primary'):
    name=normalize_name(k.get('name'))
    if not name:
        result=report_row(k,status='REJECTED',pass_name=pass_name,reason='Missing usable attraction name')
        return result,[result.copy()]
    candidates=name_candidates(name,index,threshold);supported=[];weak=[]
    for c,exact,score in candidates:
        zip_match,address_match,distance,conflict=geographic_evidence(k,c)
        method=None
        if not conflict:
            if zip_match:method=('exact' if exact else 'fuzzy')+'_name_zip'
            elif address_match:method=('exact' if exact else 'fuzzy')+'_name_address'
            elif exact and distance is not None and distance<=DISTANCE_THRESHOLD:method='exact_name_coordinates'
        entry=report_row(k,c,method or ('exact_name_only' if exact else 'fuzzy_name_only'),round(score,6),
            'REJECTED',pass_name,'Conflicting geographic evidence' if conflict else 'No corroborating ZIP, address or coordinate evidence',distance)
        if method:
            entry['evidence_reason']='Name and independent location evidence';supported.append(entry)
        else:weak.append(entry)
    if len(supported)==1:
        accepted=supported[0];accepted['match_status']='MATCHED_'+accepted['commonplace_filter_decision']
        return accepted.copy(),supported+weak
    if len(supported)>1:
        for entry in supported:entry.update(match_status='AMBIGUOUS',evidence_reason='Multiple geographically supported CommonPlace candidates')
        result=report_row(k,status='AMBIGUOUS',method='multiple_supported_candidates',pass_name=pass_name,reason='No forced tie resolution')
        return result,supported+weak
    if len(weak)>1:
        for entry in weak:entry.update(match_status='AMBIGUOUS',evidence_reason='Multiple name candidates; missing/conflicting geographic evidence')
        result=report_row(k,status='AMBIGUOUS',method='name_only_ambiguity',pass_name=pass_name,reason='No geographic evidence to resolve name candidates')
        return result,weak
    if weak:return weak[0].copy(),weak
    result=report_row(k,pass_name=pass_name,reason='No name candidate reaches the configured threshold')
    return result,[result.copy()]


def match_rows(kaggle,commonplace,threshold=FUZZY_THRESHOLD,diagnostic_exclude=True):
    main=prepare_commonplace(commonplace.loc[commonplace.attraction_filter_decision.isin(['INCLUDE','REVIEW'])])
    excluded=prepare_commonplace(commonplace.loc[commonplace.attraction_filter_decision.eq('EXCLUDE')])
    summaries=[];details=[];primary_unmatched=[]
    for k in kaggle.to_dict('records'):
        summary,rows=match_pass(k,main,threshold)
        details.extend(rows)
        if summary['match_status'] not in {'MATCHED_INCLUDE','MATCHED_REVIEW'}:primary_unmatched.append(k['kaggle_row_id'])
        # Diagnostic EXCLUDE search only for primary UNMATCHED, never ambiguous/rejected rescue.
        if diagnostic_exclude and summary['match_status']=='UNMATCHED':
            diagnostic,diagnostic_rows=match_pass(k,excluded,threshold,'exclude_diagnostic')
            details.extend(diagnostic_rows)
            if diagnostic['match_status']!='UNMATCHED':summary=diagnostic
        summaries.append(summary)
    summary=pd.DataFrame(summaries,columns=REPORT_COLUMNS);details=pd.DataFrame(details,columns=REPORT_COLUMNS)
    accepted=summary.match_status.isin(STATUSES[:3]);duplicate_ids=summary.loc[accepted,'commonplace_source_id'].duplicated(keep=False)
    collisions=set(summary.loc[accepted].loc[duplicate_ids,'commonplace_source_id'])
    if collisions:
        collision_rows=accepted & summary.commonplace_source_id.isin(collisions)
        summary.loc[collision_rows,['match_status','evidence_reason']]=['AMBIGUOUS','Multiple Kaggle rows compete for one CommonPlace record; manual alias/duplicate review required']
        conflicted_kaggle=set(summary.loc[collision_rows,'kaggle_row_id'])
        details.loc[details.kaggle_row_id.isin(conflicted_kaggle) & details.match_status.isin(STATUSES[:3]),['match_status','evidence_reason']]=['AMBIGUOUS','Multiple curated rows compete for one CommonPlace record']
    if len(summary)!=len(kaggle) or summary.kaggle_row_id.duplicated().any():raise AssertionError('Kaggle row accounting failed')
    primary_unmatched=summary.loc[~summary.match_status.isin(['MATCHED_INCLUDE','MATCHED_REVIEW']),'kaggle_row_id'].tolist()
    return summary,details,primary_unmatched


def support_by_subtype(commonplace,summary):
    review=commonplace.loc[commonplace.attraction_filter_decision.eq('REVIEW')]
    supported=summary.loc[summary.match_status.eq('MATCHED_REVIEW')]
    groups=[]
    for keys,frame in review.groupby(['facility_type','facility_domain_code','facility_domain_label'],dropna=False,sort=True):
        matches=supported.loc[supported.commonplace_source_id.isin(frame.source_record_id)]
        ids=matches.commonplace_source_id.nunique()
        groups.append({'facility_type':keys[0],'facility_domain_code':keys[1],'facility_domain_label':keys[2],
            'review_rows_total':len(frame),'review_rows_matched_by_kaggle':ids,'support_rate':ids/len(frame),
            'sample_supported_places':json.dumps(sorted(matches.commonplace_name.dropna().unique().tolist())[:5],ensure_ascii=False)})
    return pd.DataFrame(groups).sort_values(['review_rows_matched_by_kaggle','support_rate','facility_type','facility_domain_code'],ascending=[False,False,True,True]).reset_index(drop=True)


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fuzzy-threshold',type=float,default=FUZZY_THRESHOLD)
    parser.add_argument('--no-exclude-diagnostic',action='store_true');args=parser.parse_args(argv)
    if not 0<args.fuzzy_threshold<=1:raise ValueError('Fuzzy threshold must be in (0,1]')
    kaggle,metadata,schema=load_kaggle()
    cp_file=ROOT/'data/interim/commonplace_attraction_classified.csv';commonplace=pd.read_csv(cp_file,dtype=CP_DTYPES)
    counts=commonplace.attraction_filter_decision.value_counts().to_dict()
    if counts!={'EXCLUDE':11760,'REVIEW':5790,'INCLUDE':2901}:raise ValueError('Unexpected CommonPlace classification; no decisions will be changed')
    summary,details,primary_unmatched=match_rows(kaggle,commonplace,args.fuzzy_threshold,not args.no_exclude_diagnostic)
    support=support_by_subtype(commonplace,summary)
    accepted=summary.loc[summary.match_status.isin(STATUSES[:3])]
    signals=commonplace.copy();signals['kaggle_tourist_match']=signals.source_record_id.isin(accepted.commonplace_source_id)
    lookup=accepted.set_index('commonplace_source_id')
    signals['kaggle_match_method']=signals.source_record_id.map(lookup.match_method)
    signals['kaggle_match_confidence']=signals.source_record_id.map(lookup.match_confidence)
    status_counts=summary.match_status.value_counts().reindex(STATUSES,fill_value=0)
    primary_gaps=kaggle.loc[kaggle.kaggle_row_id.isin(primary_unmatched)].merge(summary[['kaggle_row_id','match_status','evidence_reason']],on='kaggle_row_id',validate='one_to_one')
    # Name-only candidates remain inspection evidence, never counted as supported matches.
    weak=details.loc[details.match_method.isin(['exact_name_only','fuzzy_name_only'])]
    paths={ROOT/'data/interim/kaggle_tourist_locations_clean.csv':kaggle.to_csv(index=False),
        ROOT/'data/interim/commonplace_kaggle_tourist_signal.csv':signals.to_csv(index=False),
        ROOT/'data/reports/audit/attractions/kaggle_commonplace_matching_summary.csv':summary.to_csv(index=False),
        ROOT/'data/reports/audit/attractions/kaggle_commonplace_matching_report.csv':details.to_csv(index=False),
        ROOT/'data/reports/audit/attractions/kaggle_commonplace_ambiguous_matches.csv':details.loc[details.match_status.eq('AMBIGUOUS')].to_csv(index=False),
        ROOT/'data/reports/audit/attractions/kaggle_commonplace_name_only_candidates.csv':weak.to_csv(index=False),
        ROOT/'data/reports/audit/attractions/commonplace_review_supported_by_kaggle.csv':summary.loc[summary.match_status.eq('MATCHED_REVIEW')].rename(columns={'commonplace_facility_type':'facility_type','commonplace_domain_label':'facility_domain_label','commonplace_borough':'borough'}).to_csv(index=False),
        ROOT/'data/reports/audit/attractions/commonplace_include_supported_by_kaggle.csv':summary.loc[summary.match_status.eq('MATCHED_INCLUDE')].rename(columns={'commonplace_facility_type':'facility_type','commonplace_domain_label':'facility_domain_label','commonplace_borough':'borough'}).to_csv(index=False),
        ROOT/'data/reports/audit/attractions/kaggle_matches_commonplace_exclude.csv':summary.loc[summary.match_status.eq('MATCHED_EXCLUDE')].to_csv(index=False),
        ROOT/'data/reports/audit/attractions/kaggle_tourist_locations_unmatched.csv':primary_gaps.to_csv(index=False),
        ROOT/'data/reports/audit/attractions/commonplace_kaggle_review_subtype_support.csv':support.to_csv(index=False)}
    include_n=int(status_counts['MATCHED_INCLUDE']);review_n=int(status_counts['MATCHED_REVIEW'])
    lines=['# Kaggle tourist-relevance cross-check — audit only','',
        f'Source: [{metadata["dataset_id"]}]({metadata["source_url"]}). Raw files remain ignored; no canonical source replacement.',
        '## Actual source schema','',json.dumps(schema,indent=2),'',
        f'Actual rows: {len(kaggle)}. The dataset title says 348, but the downloaded workbook has 347 data rows.',
        f'Invalid/missing normalized ZIP values: {int(kaggle.zipcode.isna().sum())}.',
        f'Repeated normalized-name rows: {int(kaggle.name_normalized.duplicated(keep=False).sum())}.',
        'Exact duplicates and repeated names are preserved for alias/duplicate review.','',
        '## Geographic-evidence limitation','',
        'CommonPlace has coordinates, but no addresses or ZIP columns. Kaggle has addresses/ZIPs, but no coordinates.',
        'Opaque source/address-point IDs and boroughs are not address/ZIP evidence. No geocoding or ZIP inference was added.',
        'Therefore this snapshot cannot support the requested geographic/address-backed matching hierarchy.',
        'Zero accepted matches means insufficient comparable evidence, not proven absence from CommonPlace.',
        'Name-only candidates are preserved separately for manual inspection and cannot support REVIEW promotion.','',
        '## Row-level status accounting','',markdown_table(status_counts.rename_axis('match_status').reset_index(name='rows')),'',
        f'Current INCLUDE representation confirmed by accepted matches: {include_n}/{len(kaggle)} ({include_n/len(kaggle):.2%}).',
        f'INCLUDE + REVIEW confirmed representation: {include_n+review_n}/{len(kaggle)} ({(include_n+review_n)/len(kaggle):.2%}).',
        'These are confirmed-match lower bounds; overall source overlap/completeness is unknown with the available fields.',
        f'Rows without an accepted primary INCLUDE/REVIEW match: {len(primary_gaps)}; preserved in the unmatched review file, including ambiguous/rejected/diagnostic EXCLUDE statuses.','',
        '## REVIEW subtype support','',markdown_table(support),'',
        'No subtype is promoted by this audit. Unsupported matches cannot establish a subtype support rate beyond confirmed matches.',
        '## Matched REVIEW examples','',markdown_table(summary.loc[summary.match_status.eq('MATCHED_REVIEW')]),'',
        '## Matched INCLUDE subtype counts','',markdown_table(summary.loc[summary.match_status.eq('MATCHED_INCLUDE')].groupby(['commonplace_facility_type','commonplace_domain_label'],dropna=False).size().reset_index(name='matched_rows')),'',
        '## Name-only REVIEW candidates — NOT accepted matches','',markdown_table(weak.loc[weak.commonplace_filter_decision.eq('REVIEW'),['kaggle_name','commonplace_name','commonplace_domain_label','match_method','match_status']].head(30)),'',
        '## Unmatched tourist-location examples','',markdown_table(primary_gaps[['name','address','zipcode','match_status']].head(20)),'',
        '## Matching policy and integrity','',
        f'Fuzzy SequenceMatcher threshold: {args.fuzzy_threshold}; exact-name coordinate threshold: {DISTANCE_THRESHOLD}m.',
        'Shared Unicode/punctuation/address normalization is reused without removing meaningful name words.',
        'Exact/fuzzy names require same ZIP or exact normalized full address; exact names may use <=50m coordinates.',
        'Conflicting ZIP or >150m coordinates blocks acceptance. Multiple plausible records remain AMBIGUOUS.',
        'EXCLUDE is diagnostic only after primary UNMATCHED; it never changes authoritative decisions.',
        'One CommonPlace record claimed by multiple accepted Kaggle rows becomes AMBIGUOUS pending alias review.',
        'Confidence is a name-evidence score, not a calibrated probability. Summary counts each Kaggle row once; full reports expose candidate pairs.',
        'Audit signals are written to a separate interim copy. False means no accepted match, not proven non-tourist status.',
        'CommonPlace source rows, taxonomy rules and INCLUDE/REVIEW/EXCLUDE pools remain unchanged.',
        'No additional canonical rows, final attraction IDs or processed attractions.csv are created.','']
    paths[ROOT/'data/reports/audit/attractions/kaggle_tourist_relevance_report.md']='\n'.join(lines)
    for path,content in paths.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    print(status_counts.to_string());print(f'Rows: {len(kaggle)}; primary unrepresented: {len(primary_gaps)}; name-only candidate pairs: {len(weak)}')
    print('CommonPlace classification remains:',counts)


if __name__=='__main__':main()
