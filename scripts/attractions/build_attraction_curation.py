"""Build temporary, evidence-only manual-curation records; never assign final decisions."""
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import pandas as pd
from shapely import wkt
from shapely.geometry import Point
from scripts.shared.restaurant_matching import normalize_name, coordinate_distance
from scripts.attractions.match_attractions_kaggle import CP_DTYPES
from scripts.attractions.explore_attractions import markdown_table

ROOT=Path(__file__).resolve().parents[2]
REPORTS=ROOT/'data/reports/audit/attractions'
CURATION_DIR=ROOT/'data/interim'
MAX_INDIVIDUAL=200
ORIGINS=['COMMONPLACE_REVIEW_LANDMARK_SUPPORTED','COMMONPLACE_EXCLUDE_LANDMARK_SUPPORTED','UNMATCHED_SCENIC_LANDMARK','UNMATCHED_INDIVIDUAL_LANDMARK']
MANUAL_FIELDS=['manual_decision','manual_reason','manual_notes']
KEYWORD_WEIGHTS={**dict.fromkeys(['museum','theater','theatre','concert','cathedral','monument','memorial','library','market','terminal','bridge','park','garden','plaza','square','fort','castle'],8),
 **dict.fromkeys(['church','synagogue','temple'],5),**dict.fromkeys(['station','hall','tower','historic'],4),**dict.fromkeys(['mansion','house'],2)}
INSTITUTIONAL={'museum','theater','theatre','concert','cathedral','church','synagogue','temple','monument','memorial','library','market','terminal','bridge','park','garden','plaza','square','fort','castle'}
INFRASTRUCTURE=re.compile(r'\b(?:lampposts?|lamp\s*posts?|street\s*lights?|hydrants?|sewers?|ventilation|vent\s+structures?|maintenance|storage\s+tanks?|substations?)\b',re.I)
PRIVATE=re.compile(r'\b(?:apartments?|residences?|residential|dwellings?|row\s+houses?)\b|^\s*\d+[\w-]*\s+.*\b(?:house|houses)\b',re.I)
BOROUGHS={'MN':'Manhattan','BK':'Brooklyn','BX':'Bronx','QN':'Queens','SI':'Staten Island'}
GENERIC={'the','of','and','a','an','new','york','city','building','house','church','park','library','station','hall','street','avenue'}
MANUAL_COLUMNS=['curation_candidate_id','candidate_name','candidate_origin','facility_type','facility_domain_label','landmark_type',
 'designation_address','borough','review_priority','possible_existing_include_name','possible_existing_include_distance_m',
 'kaggle_name_support','evidence_summary',*MANUAL_FIELDS]
OUTPUT_COLUMNS=['curation_candidate_id','candidate_name','candidate_origin','commonplace_source_id','commonplace_filter_decision',
 'facility_type','facility_domain_code','facility_domain_label','landmark_source','landmark_source_id','landmark_type','lp_number',
 'designation_address','borough','latitude','longitude','coordinate_method','landmark_supported','landmark_designated',
 'kaggle_name_support','kaggle_candidate_name','review_keywords','institutional_name_signal','clear_address_signal','private_residence_signal',
 'selection_score','review_priority','possible_existing_include_match','possible_existing_include_name','possible_existing_include_source_id',
 'possible_existing_include_distance_m','possible_existing_include_name_similarity','possible_existing_include_method',
 'possible_existing_include_candidate_count','evidence_summary','landmark_evidence',*MANUAL_FIELDS]


def present(value):return value is not None and not pd.isna(value) and str(value).strip()!=''


def review_signals(row):
    name=str(row.get('landmark_name') or '')
    normalized=normalize_name(name) or ''
    keywords=sorted(k for k in KEYWORD_WEIGHTS if re.search(r'\b'+k+r'\b',normalized))
    institutional=bool(set(keywords)&INSTITUTIONAL)
    private=bool(PRIVATE.search(name))
    infrastructure=bool(INFRASTRUCTURE.search(name))
    address=present(row.get('designation_address'))
    eligible=bool(keywords) and not infrastructure and not(private and not institutional)
    score=max((KEYWORD_WEIGHTS[k] for k in keywords),default=0)*10+min(len(keywords),4)*2+int(institutional)*5+int(address)*3-int(private)*10
    return dict(eligible=eligible,keywords=keywords,institutional=institutional,private=private,infrastructure=infrastructure,address=address,score=score)


def evidence(row,match=None):
    return dict(source=row['source'],source_id=str(row['landmark_source_id']),lp_number=row.get('lp_number'),
        name=row['landmark_name'],designation_address=row.get('designation_address'),borough=row.get('borough'),
        latitude=row.get('latitude'),longitude=row.get('longitude'),coordinate_method=row.get('coordinate_method'),
        geometry_wkt=row.get('geometry_wkt'),match_method=match.get('match_method') if match else None,
        match_confidence=match.get('match_confidence') if match else None)


def candidate(row,origin,cp=None,match=None):
    signals=review_signals(row)
    cp={} if cp is None else cp
    return dict(candidate_name=cp.get('name',row['landmark_name']),candidate_origin=origin,
        commonplace_source_id=cp.get('source_record_id'),commonplace_filter_decision=cp.get('attraction_filter_decision'),
        facility_type=cp.get('facility_type'),facility_domain_code=cp.get('facility_domain_code'),facility_domain_label=cp.get('facility_domain_label'),
        landmark_source=row['source'],landmark_source_id=str(row['landmark_source_id']),landmark_type='SCENIC' if 'scenic' in row['source'] else 'INDIVIDUAL',
        lp_number=row.get('lp_number'),designation_address=row.get('designation_address'),borough=BOROUGHS.get(cp.get('borough',row.get('borough')),cp.get('borough',row.get('borough'))),
        latitude=cp.get('latitude',row.get('latitude')),longitude=cp.get('longitude',row.get('longitude')),
        coordinate_method='commonplace_source_coordinate' if cp else row.get('coordinate_method'),
        landmark_supported=bool(cp),landmark_designated=True,review_keywords=';'.join(signals['keywords']),
        institutional_name_signal=signals['institutional'],clear_address_signal=signals['address'],private_residence_signal=signals['private'],
        selection_score=signals['score'],_evidence=[evidence(row,match)],**dict.fromkeys(MANUAL_FIELDS,''))


def same_candidate(left,right):
    """Preserve distinct CommonPlace identities and branches; avoid fuzzy identity merging."""
    lcp,rcp=left.get('commonplace_source_id'),right.get('commonplace_source_id')
    if present(lcp) and present(rcp):return str(lcp)==str(rcp)
    refs=lambda item:{(e['source'],e['source_id']) for e in item['_evidence']}
    if refs(left)&refs(right):return True
    for l in left['_evidence'][:1]:
        for r in right['_evidence'][:1]:
            if normalize_name(l['name'])!=normalize_name(r['name']):continue
            if not all(present(v) for v in [l['latitude'],l['longitude'],r['latitude'],r['longitude']]):continue
            distance=coordinate_distance(l,r)
            same_lp=present(l.get('lp_number')) and l.get('lp_number')==r.get('lp_number')
            if (same_lp and distance<=50) or distance<=10:return True
    return False


def deduplicate(candidates):
    ordered=sorted(candidates,key=lambda c:(ORIGINS.index(c['candidate_origin']),normalize_name(c['candidate_name']) or '',c['landmark_source'],c['landmark_source_id']))
    groups=[]
    for incoming in ordered:
        existing=next((g for g in groups if same_candidate(g,incoming)),None)
        if existing is None:groups.append(incoming.copy());continue
        # Preserve every contributing source reference; the earliest origin wins.
        existing['_evidence']=list({(e['source'],e['source_id']):e for e in existing['_evidence']+incoming['_evidence']}.values())
        existing['landmark_supported'] |= incoming['landmark_supported']
        existing['selection_score']=max(existing['selection_score'],incoming['selection_score'])
        existing['review_keywords']=';'.join(sorted((set(existing['review_keywords'].split(';'))|set(incoming['review_keywords'].split(';')))-{''}))
    return groups


def possible_alias(candidate,include):
    name=normalize_name(candidate['candidate_name']) or ''
    geometries=[wkt.loads(e['geometry_wkt']) for e in candidate['_evidence'] if present(e.get('geometry_wkt'))]
    important=set(name.split())-GENERIC
    options=[]
    for row in include.to_dict('records'):
        if not all(present(v) for v in [row.get('latitude'),row.get('longitude'),candidate.get('latitude'),candidate.get('longitude')]):continue
        distance=coordinate_distance(candidate,row)
        contained=any(g.covers(Point(float(row['longitude']),float(row['latitude']))) for g in geometries)
        if distance>150 and not contained:continue
        other=normalize_name(row['name']) or ''
        similarity=SequenceMatcher(None,name,other,autojunk=False).ratio()
        if similarity<0.65 or (not(important&(set(other.split())-GENERIC)) and similarity<0.90):continue
        options.append(dict(name=row['name'],source_id=str(row['source_record_id']),distance=distance,similarity=similarity,
            method='name_similarity_polygon_contains' if contained else 'name_similarity_within_150m'))
    options.sort(key=lambda e:(-e['similarity'],e['distance'],e['source_id']))
    top=options[0] if options else {}
    return dict(possible_existing_include_match=bool(options),possible_existing_include_name=top.get('name'),
        possible_existing_include_source_id=top.get('source_id'),possible_existing_include_distance_m=top.get('distance'),
        possible_existing_include_name_similarity=top.get('similarity'),possible_existing_include_method=top.get('method'),
        possible_existing_include_candidate_count=len(options))


def kaggle_support(candidate,weak):
    names={normalize_name(candidate['candidate_name'])}
    names.update(normalize_name(e['name']) for e in candidate['_evidence'])
    supported=[]
    for row in weak.to_dict('records'):
        identity=present(candidate.get('commonplace_source_id')) and str(row.get('commonplace_source_id'))==str(candidate['commonplace_source_id'])
        name_evidence=normalize_name(row.get('kaggle_name')) in names or normalize_name(row.get('commonplace_name')) in names
        if identity or name_evidence:supported.append(str(row['kaggle_name']))
    return sorted(set(supported))


def build_curation(commonplace,landmarks,matched,gaps,weak,max_individual=MAX_INDIVIDUAL):
    if max_individual<0:raise ValueError('Invalid individual cap')
    include=commonplace.loc[commonplace.attraction_filter_decision.eq('INCLUDE')]
    cp=commonplace.set_index('source_record_id').to_dict('index')
    landmark_lookup={(r['source'],str(r['landmark_source_id'])):r for r in landmarks.to_dict('records')}
    candidates=[]
    for match in matched.to_dict('records'):
        decision=match['commonplace_filter_decision']
        if match['match_status']!='MATCHED_'+decision or decision not in {'REVIEW','EXCLUDE'}:continue
        source_row=landmark_lookup[(match['landmark_source'],str(match['landmark_source_id']))]
        identity=str(match['commonplace_source_id'])
        if identity not in cp or cp[identity]['attraction_filter_decision']!=decision:raise ValueError('Supported CommonPlace identity/decision mismatch')
        candidates.append(candidate(source_row,'COMMONPLACE_'+decision+'_LANDMARK_SUPPORTED',dict(cp[identity],source_record_id=identity),match))
    individual_raw=0;signal_count=0;excluded_infrastructure=0;excluded_private=0
    for row in gaps.to_dict('records'):
        if row.get('active_designated')!=True or row.get('match_status') in {'MATCHED_INCLUDE','MATCHED_REVIEW','MATCHED_EXCLUDE'}:continue
        if 'scenic' in row['source']:candidates.append(candidate(row,'UNMATCHED_SCENIC_LANDMARK'));continue
        individual_raw+=1;signals=review_signals(row)
        excluded_infrastructure+=int(signals['infrastructure'] and bool(signals['keywords']))
        excluded_private+=int(signals['private'] and not signals['institutional'] and not signals['infrastructure'] and bool(signals['keywords']))
        if signals['eligible']:
            signal_count+=1;candidates.append(candidate(row,'UNMATCHED_INDIVIDUAL_LANDMARK'))
    groups=deduplicate(candidates)
    individual=[r for r in groups if r['candidate_origin']=='UNMATCHED_INDIVIDUAL_LANDMARK']
    individual.sort(key=lambda r:(-r['selection_score'],normalize_name(r['candidate_name']) or '',str(r.get('lp_number')),r['landmark_source_id']))
    retained=[r for r in groups if r['candidate_origin']!='UNMATCHED_INDIVIDUAL_LANDMARK']+individual[:max_individual]
    for row in retained:
        row.update(possible_alias(row,include))
        names=kaggle_support(row,weak);row['kaggle_name_support']=bool(names);row['kaggle_candidate_name']=' | '.join(names)
        very_strong=row['possible_existing_include_match'] and row['possible_existing_include_name_similarity']>=0.90 and (row['possible_existing_include_distance_m']<=50 or row['possible_existing_include_method']=='name_similarity_polygon_contains')
        strong_keywords=set(row['review_keywords'].split(';')) & {k for k,w in KEYWORD_WEIGHTS.items() if w==8}
        row['review_priority']='HIGH' if row['candidate_origin']!='UNMATCHED_INDIVIDUAL_LANDMARK' or very_strong or (strong_keywords and row['institutional_name_signal'] and row['clear_address_signal']) else ('MEDIUM' if row['institutional_name_signal'] or row['selection_score']>=40 else 'LOW')
        if row['landmark_supported']:
            methods=sorted({e['match_method'] for e in row['_evidence'] if e['match_method']})
            summary=f"CommonPlace {row['commonplace_filter_decision']} row; confident LPC designated-landmark match ({', '.join(methods)})"
        else:summary=f"Unmatched {'scenic' if row['landmark_type']=='SCENIC' else 'individual'} designated landmark; review keywords={row['review_keywords'] or 'none'}; no accepted CommonPlace match"
        if row['possible_existing_include_match']:summary+=f"; possible INCLUDE alias/constituent {row['possible_existing_include_distance_m']:.0f} m away (name similarity {row['possible_existing_include_name_similarity']:.2f})"
        if names:summary+='; Kaggle name-only support (unconfirmed)'
        row['evidence_summary']=summary
        # Full source references remain available when multiple LP/site records were merged.
        row['landmark_evidence']=json.dumps([{k:(v if present(v) else None) for k,v in e.items() if k!='geometry_wkt'} for e in sorted(row['_evidence'],key=lambda e:(e['source'],e['source_id']))],sort_keys=True,ensure_ascii=False,default=str,allow_nan=False)
    retained.sort(key=lambda r:({'HIGH':0,'MEDIUM':1,'LOW':2}[r['review_priority']],ORIGINS.index(r['candidate_origin']),-r['selection_score'],normalize_name(r['candidate_name']) or '',r['landmark_source_id']))
    for index,row in enumerate(retained):row['curation_candidate_id']=f'CUR_{index+1:04d}'
    frame=pd.DataFrame(retained,columns=OUTPUT_COLUMNS)
    if frame.curation_candidate_id.duplicated().any() or not frame[MANUAL_FIELDS].eq('').all().all():raise AssertionError('Curation identity/manual decision integrity failed')
    if frame.commonplace_filter_decision.eq('INCLUDE').any():raise AssertionError('Automatic INCLUDE records must not enter curation')
    statistics=dict(individual_gap_rows=individual_raw,individual_signal_rows=signal_count,excluded_keyword_infrastructure=excluded_infrastructure,
        excluded_keyword_private=excluded_private,pre_dedup_candidate_rows=len(candidates),post_dedup_candidate_rows=len(groups),
        dedup_merges=len(candidates)-len(groups),individual_distinct_before_cap=len(individual),individual_retained=min(len(individual),max_individual),
        individual_truncated=max(0,len(individual)-max_individual))
    return frame,statistics


def main():
    for filename in ['final_attraction_curation.csv','final_attraction_curation_manual.csv']:
        path=CURATION_DIR/filename
        if path.exists():
            old=pd.read_csv(path,dtype='string',keep_default_na=False)
            if old[MANUAL_FIELDS].apply(lambda col:col.str.strip().ne('')).any().any():raise ValueError('Manual edits exist; refusing to overwrite populated curation decisions')
    def read(path):return pd.read_csv(ROOT/path,dtype={**CP_DTYPES,'landmark_source_id':'string','commonplace_source_id':'string','lp_number':'string'})
    commonplace=read('data/interim/commonplace_attraction_classified.csv')
    if commonplace.attraction_filter_decision.value_counts().to_dict()!={'EXCLUDE':11760,'REVIEW':5790,'INCLUDE':2901}:raise ValueError('Unexpected CommonPlace snapshot')
    include=read('data/interim/commonplace_attraction_candidates.csv')
    expected=commonplace.loc[commonplace.attraction_filter_decision.eq('INCLUDE'),'source_record_id']
    if len(commonplace)!=20451 or len(include)!=2901 or set(include.source_record_id)!=set(expected):raise ValueError('Automatic base integrity failed')
    landmarks=pd.concat([read('data/interim/individual_landmarks_clean.csv'),read('data/interim/scenic_landmarks_clean.csv')],ignore_index=True)
    matched=pd.concat([read('data/interim/commonplace_review_supported_by_landmarks.csv'),read('data/interim/commonplace_exclude_supported_by_landmarks.csv')],ignore_index=True)
    frame,statistics=build_curation(commonplace,landmarks,matched,read('data/interim/landmarks_unmatched_commonplace.csv'),read('data/interim/kaggle_commonplace_name_only_candidates.csv'))
    def frequencies(field):
        if field=='review_priority':return frame[field].value_counts().reindex(['HIGH','MEDIUM','LOW'],fill_value=0).rename_axis(field).reset_index(name='candidates')
        return frame.groupby(field,dropna=False,sort=True).size().reset_index(name='candidates')
    lines=['# Final attraction manual-curation candidates','',
        'Evidence-only review table. The automatic 2,901 CommonPlace INCLUDE rows are untouched and excluded from this table. No final attraction IDs, processed attractions.csv, decisions, promotions or source union are created.',
        f'Total candidates: {len(frame)}. Temporary CUR_ IDs track this fixed snapshot; they are not canonical IDs and may shift if snapshots change.','',
        '## Priority','',markdown_table(frequencies('review_priority')),'','## Origin','',markdown_table(frequencies('candidate_origin')),'',
        '## Selection and truncation','',json.dumps(statistics,indent=2),'',
        'All confident landmark-supported REVIEW/EXCLUDE identities and all active unmatched scenic records are retained. Only eligible unmatched/rejected individual records enter keyword screening.',
        f'Individual cap: {MAX_INDIVIDUAL}, applied AFTER conservative deduplication. Sort by descending selection_score, normalized name, LP number, then landmark source ID. No LLM classification.',
        f'Keyword weights: {json.dumps(KEYWORD_WEIGHTS,sort_keys=True)}.',
        'Score = 10 × strongest keyword weight + 2 × keyword count (capped at 4) + 5 for institutional-name signal + 3 for nonempty designation address − 10 for explicit private-residence wording.',
        'Institutional-name signal is the presence of documented institution/public-space keywords, not independently verified public access. A clear-address signal means a nonempty source designation address, not geocoding or verified visiting instructions.',
        f'Institutional keywords: {", ".join(sorted(INSTITUTIONAL))}.',
        f'Explicit infrastructure exclusion regex: `{INFRASTRUCTURE.pattern}`.',
        f'Explicit private-residence regex: `{PRIVATE.pattern}`. Exclude these only without an institutional-name signal. House/mansion alone are weaker review signals, not proof of public access.',
        'HIGH: all mandatory origins; very strong possible INCLUDE alias (similarity >=0.90 and <=50m or containment); or weight-8 keyword plus institutional-name and address signals. MEDIUM: other institutional-name signal or score >=40. LOW: remaining weaker retained records. Priorities do not decide inclusion.',
        '## Conservative deduplication','',
        'Same CommonPlace source ID or same landmark source reference merges. Otherwise exact normalized landmark name plus same LP within 50m, or exact normalized name within 10m. Distinct CommonPlace identities and distant physical branches remain separate. Location comparisons use a fixed first-record anchor to prevent transitive proximity chains. All source evidence is combined in landmark_evidence JSON. The earliest mandatory origin wins over optional individual evidence.',
        '## Possible INCLUDE aliases','',
        'Every retained candidate is searched against the 2,901 frozen INCLUDE rows. Potential evidence requires similarity >=0.65 plus a shared distinctive token (or similarity >=0.90), and distance <=150m or containment in a contributing landmark polygon.',
        'Only the best candidate is displayed: highest name similarity, then shortest distance, then source ID. Candidate count records alternative suggestions. Names of constituent facilities inside a park may surface: these are possible alias/constituent evidence, not confirmed same-place identity.',
        f'Candidates with possible aliases: {int(frame.possible_existing_include_match.sum())}. Candidates with weak Kaggle name support: {int(frame.kaggle_name_support.sum())}.',
        'Kaggle support uses only existing name-only audit pairs, joined by CommonPlace source ID or exact normalized candidate/landmark name correspondence. It cannot originate a new candidate or confirm identity.',
        'landmark_supported means a confident landmark-to-CommonPlace match; unmatched designated landmarks retain landmark_designated=true but landmark_supported=false.',
        'Individual designation currency remains unverified because the source lacks a current flag. Source geometry/landmark-matching audits are preserved.','',
        '## Manual workflow','',
        'Edit final_attraction_curation_manual.csv as the primary review file. manual_decision, manual_reason and manual_notes start blank. The builder refuses to overwrite files with populated manual fields.',
        'Allowed manual_decision vocabulary: ADD (add a new attraction later); DO_NOT_ADD (omit); ALIAS_OF_EXISTING (same place as an automatic INCLUDE row); NEEDS_REVIEW (undecided). Blank also remains undecided. No automatic decisions or final union are produced.',
        'Join the compact and full tables using curation_candidate_id. Record alias source identity in manual_notes when useful.','',
        '## REVIEW subtype breakdown','',markdown_table(frame.loc[frame.commonplace_filter_decision.eq('REVIEW')].groupby(['facility_type','facility_domain_code','facility_domain_label']).size().reset_index(name='candidates')),'',
        '## EXCLUDE subtype breakdown','',markdown_table(frame.loc[frame.commonplace_filter_decision.eq('EXCLUDE')].groupby(['facility_type','facility_domain_code','facility_domain_label']).size().reset_index(name='candidates')),'',
        '## Landmark source','',markdown_table(frequencies('landmark_source')),'',
        '## Borough (known source codes normalized; original values preserved in landmark evidence)','',markdown_table(frequencies('borough')),'',
        '## HIGH-priority examples','',markdown_table(frame.loc[frame.review_priority.eq('HIGH'),['curation_candidate_id','candidate_name','candidate_origin','evidence_summary']].head(20)),'',
        '## Unmatched scenic candidates and possible aliases','',markdown_table(frame.loc[frame.candidate_origin.eq('UNMATCHED_SCENIC_LANDMARK'),['candidate_name','possible_existing_include_name','possible_existing_include_distance_m','possible_existing_include_name_similarity']]),'',
        '## Integrity','',
        'CommonPlace remains INCLUDE 2901, REVIEW 5790, EXCLUDE 11760, UNMAPPED 0, total 20451. Restaurants, rule metadata, automatic candidate base, Kaggle audit and landmark matching inputs are read-only.',
        'All manual fields are blank. No final ATTR_ IDs, processed attractions.csv, automatic additions, commit or push.','']
    CURATION_DIR.mkdir(parents=True,exist_ok=True)
    REPORTS.mkdir(parents=True,exist_ok=True)
    (CURATION_DIR/'final_attraction_curation.csv').write_text(frame.to_csv(index=False))
    (CURATION_DIR/'final_attraction_curation_manual.csv').write_text(frame[MANUAL_COLUMNS].to_csv(index=False))
    (REPORTS/'final_attraction_curation_report.md').write_text('\n'.join(lines))
    print('Curation candidates:',len(frame));print(frequencies('candidate_origin').to_string(index=False));print(frequencies('review_priority').to_string(index=False));print(json.dumps(statistics,indent=2));print('Possible INCLUDE aliases:',int(frame.possible_existing_include_match.sum()),'; Kaggle name support:',int(frame.kaggle_name_support.sum()))

if __name__=='__main__':main()
