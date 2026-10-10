"""Clean LPC source snapshots and audit geographically corroborated CommonPlace overlap."""
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile
import pandas as pd
from pyproj import CRS, Transformer
import shapefile
from shapely import make_valid, wkt, transform
from shapely.geometry import shape, Point
from scripts.attractions.download_attractions import ROOT, LANDMARK_DATASETS
from scripts.shared.restaurant_matching import normalize_name, coordinate_distance
from scripts.attractions.match_attractions_kaggle import name_candidates, FUZZY_THRESHOLD, CP_DTYPES, STATUSES
from scripts.attractions.explore_attractions import markdown_table

SOURCES={'individual':'nyc_lpc_individual_landmarks','scenic':'nyc_lpc_scenic_landmarks'}
MATCH_COLUMNS=['landmark_source','landmark_source_id','landmark_name','borough','designation_address','lp_number',
 'commonplace_source_id','commonplace_name','commonplace_filter_decision','facility_type','facility_domain_code',
 'facility_domain_label','distance_meters','geometry_contains','match_method','match_confidence','match_status','evidence_reason']


def eligibility(properties, kind):
    """Only exact designated state; unknown current flags are not inferred."""
    status=str(properties.get('lpc_sitest' if kind=='individual' else 'status','')).strip().casefold()
    current=properties.get('current_') if kind=='scenic' else None
    action=str(properties.get('last_actio','')).strip().casefold()
    if kind=='scenic' and str(current).strip().casefold() not in {'true','1','yes'}:
        return False,'inactive / superseded / non-current'
    if status!='designated' or action in {'rescinded','rescind','inactive','calendared'}:
        return False,'other current states'
    return True, 'current + designated' if kind=='scenic' else 'designated; current flag unavailable'


def representative_geometry(geometry, crs='EPSG:4326'):
    if geometry is None:return None,None,None,'missing_geometry'
    geom=shape(geometry)
    if geom.geom_type not in {'Polygon','MultiPolygon'}:raise ValueError('Expected polygon landmark geometry')
    repair=not geom.is_valid
    if repair:geom=make_valid(geom)
    if geom.is_empty:return None,None,None,'empty_geometry'
    projection=Transformer.from_crs(CRS.from_user_input(crs),4326,always_xy=True)
    geom=transform(geom,projection.transform,interleaved=False)
    xmin,ymin,xmax,ymax=geom.bounds
    if not(-180<=xmin<=xmax<=180 and -90<=ymin<=ymax<=90):raise ValueError('Invalid geographic geometry')
    point=geom.representative_point()
    if not geom.covers(point):raise ValueError('Representative point is not covered by geometry')
    return geom,point.y,point.x,'representative_point'+('_repaired' if repair else '')


def clean_features(features,kind,crs='EPSG:4326'):
    rows=[]
    for index,feature in enumerate(features):
        props={str(k).lower():v for k,v in feature['properties'].items()}
        name=props.get('lpc_name' if kind=='individual' else 'scen_lm_na')
        lp=props.get('lpc_lpnumb' if kind=='individual' else 'lp_number')
        source_id=str(props.get('objectid')) if kind=='individual' else f'{lp}:source_row_{index+1:04d}'
        geom,lat,lon,method=representative_geometry(feature.get('geometry'),crs)
        active,group=eligibility(props,kind)
        rows.append(dict(**{'raw_'+key:value for key,value in props.items()},
            landmark_source_id=source_id,landmark_name=name,name_normalized=normalize_name(name),
            designation_address=props.get('address'),borough=props.get('borough'),latitude=lat,longitude=lon,
            coordinate_method=method,lp_number=lp,designation_date=props.get('desdate'),
            site_status=props.get('lpc_sitest' if kind=='individual' else 'status'),most_current=props.get('current_'),
            last_action=props.get('last_actio'),active_designated=active,status_group=group,
            currency_verified=kind=='scenic',source=SOURCES[kind],geometry_wkt=geom.wkt if geom is not None else None))
    result=pd.DataFrame(rows)
    if result.landmark_source_id.duplicated().any():raise ValueError('Nonunique source references')
    return result


def load_source(kind):
    directory=ROOT/'data/raw/attractions/landmarks'/kind
    metadata=json.loads((directory/'retrieval_metadata.json').read_text())
    for filename,checksum in metadata['checksums'].items():
        if hashlib.sha256((directory/filename).read_bytes()).hexdigest()!=checksum:raise ValueError('Landmark source changed')
    # Keep the export projection label for audit; resolved LPC CRS evidence governs transformation.
    with zipfile.ZipFile(directory/'landmarks.zip') as archive:
        def component(suffix):
            paths=[p for p in archive.namelist() if p.lower().endswith(suffix)]
            if len(paths)!=1:raise ValueError('Ambiguous export component')
            return io.BytesIO(archive.read(paths[0]))
        reader=shapefile.Reader(shp=component('.shp'),shx=component('.shx'),dbf=component('.dbf'),encoding='utf-8')
        features=[{'properties':record.record.as_dict(),'geometry':record.shape.__geo_interface__} for record in reader.iterShapeRecords()]
    if len(features)!=metadata['row_count']:raise ValueError('Shapefile/API snapshot row-count mismatch')
    raw=pd.DataFrame([f['properties'] for f in features])
    api=json.loads((directory/'landmarks.geojson').read_text())
    api_frame=pd.DataFrame([f['properties'] for f in api['features']])
    clean=clean_features(features,kind,f"EPSG:{metadata['geometry_epsg']}")
    if kind=='individual':
        # Corroborate the resolved CRS against source geographic point attributes.
        offsets=[]
        for row in clean.itertuples():
            if pd.notna(row.raw_latitude) and pd.notna(row.raw_longitude) and row.geometry_wkt:
                offsets.append(wkt.loads(row.geometry_wkt).distance(Point(float(row.raw_longitude),float(row.raw_latitude))))
        if not offsets or sum(d<=0.002 for d in offsets)/len(offsets)<0.95:raise ValueError('Resolved CRS lacks source-coordinate corroboration')
        coordinate_check={'rows_checked':len(offsets),'outside_polygon_by_over_0_002_degrees':sum(d>0.002 for d in offsets),'maximum_offset_degrees':max(offsets)}
    # Export correspondence is checked by source attributes rather than trusting row order.
    keys=['objectid'] if kind=='individual' else ['lp_number','scen_lm_na','status','current_']
    def signature(frame):
        frame=frame.rename(columns={c:c.lower() for c in frame})
        return sorted(tuple(str(row[k]).strip() for k in keys) for row in frame.to_dict('records'))
    if signature(raw)!=signature(api_frame):raise ValueError('Shapefile/API source identities disagree')
    schema={'source_coordinate_validation':coordinate_check if kind=='individual' else 'Scenic extents verified against LPC EPSG:2263 geometry during download','metadata':metadata,'api_columns':api_frame.columns.tolist(),'export_columns':raw.columns.tolist(),
        'api_dtypes':api_frame.dtypes.astype(str).to_dict(),'api_missingness':api_frame.isna().sum().to_dict(),
        'exact_duplicate_attribute_rows':int(api_frame.duplicated().sum()),
        'unique_landmark_names':int(clean.landmark_name.nunique()),'status_counts':clean.status_group.value_counts().to_dict(),
        'status_values':clean.site_status.value_counts(dropna=False).to_dict(),'current_values':clean.most_current.value_counts(dropna=False).astype(int).to_dict()}
    return clean,schema


def match_landmarks(landmarks,commonplace,threshold=FUZZY_THRESHOLD):
    index={}
    for row in commonplace.to_dict('records'):
        name=normalize_name(row['name'])
        if name:index.setdefault(name,[]).append(row)
    summaries=[];details=[]
    for landmark in landmarks.loc[landmarks.active_designated].to_dict('records'):
        geometry=wkt.loads(landmark['geometry_wkt']) if landmark.get('geometry_wkt') else None
        base=dict(landmark_source=landmark['source'],landmark_source_id=landmark['landmark_source_id'],
            landmark_name=landmark['landmark_name'],borough=landmark.get('borough'),
            designation_address=landmark.get('designation_address'),lp_number=landmark.get('lp_number'))
        supported=[];weak=[]
        for candidate,exact,score in name_candidates(landmark['name_normalized'],index,threshold):
            lat,lon=candidate.get('latitude'),candidate.get('longitude')
            distance=None;contains=False
            if pd.notna(lat) and pd.notna(lon) and geometry is not None:
                distance=coordinate_distance(landmark,candidate)
                contains=bool(geometry.covers(Point(float(lon),float(lat))))
            method='name_only_or_far'
            if contains:method=('exact' if exact else 'fuzzy')+'_name_polygon_contains'
            elif distance is not None and distance<=50:method=('exact' if exact else 'fuzzy')+'_name_within_50m'
            elif exact and distance is not None and distance<=150:method='exact_name_within_150m'
            accepted=method!='name_only_or_far'
            entry=dict(base,commonplace_source_id=candidate['source_record_id'],commonplace_name=candidate['name'],
                commonplace_filter_decision=candidate['attraction_filter_decision'],facility_type=candidate.get('facility_type'),
                facility_domain_code=candidate.get('facility_domain_code'),facility_domain_label=candidate.get('facility_domain_label'),
                distance_meters=distance,geometry_contains=contains,match_method=method,match_confidence=round(score,6),
                match_status='MATCHED_'+candidate['attraction_filter_decision'] if accepted else 'REJECTED',
                evidence_reason='Name and geometry/location corroborate identity' if accepted else 'No sufficiently close geographic corroboration')
            (supported if accepted else weak).append(entry)
        if len(supported)==1:summary=supported[0].copy()
        elif len(supported)>1:
            for entry in supported:entry.update(match_status='AMBIGUOUS',evidence_reason='Multiple geographically supported CommonPlace records')
            summary=dict(base,match_status='AMBIGUOUS',evidence_reason='No forced resolution of multiple plausible records')
        elif weak:summary=dict(base,match_status='REJECTED',evidence_reason='Name candidates lack geographic corroboration')
        else:summary=dict(base,match_status='UNMATCHED',evidence_reason='No name candidate reaches threshold')
        summaries.append(summary);details.extend(supported+weak or [summary.copy()])
    return pd.DataFrame(summaries,columns=MATCH_COLUMNS),pd.DataFrame(details,columns=MATCH_COLUMNS)


def subtype_support(cp,summary):
    weak=pd.read_csv(ROOT/'data/interim/kaggle_commonplace_name_only_candidates.csv',dtype={'commonplace_source_id':'string'})
    accepted=summary.loc[summary.match_status.isin(STATUSES[:3])]
    rows=[]
    for key,group in cp.loc[cp.attraction_filter_decision.eq('REVIEW')].groupby(['facility_type','facility_domain_code','facility_domain_label'],dropna=False,sort=True):
        supported=accepted.loc[accepted.commonplace_source_id.isin(group.source_record_id)]
        count=supported.commonplace_source_id.nunique()
        rows.append(dict(facility_type=key[0],facility_domain_code=key[1],facility_domain_label=key[2],total_rows=len(group),
            landmark_supported_rows=count,support_rate=count/len(group),kaggle_name_only_evidence_count=int(weak.commonplace_source_id.isin(group.source_record_id).sum()),
            representative_supported_attractions=json.dumps(sorted(supported.commonplace_name.dropna().unique())[:8]),
            recommendation='SELECTIVE_PROMOTION_NEEDED' if count else 'KEEP_REVIEW'))
    from scripts.attractions.filter_attractions import load_rules
    covered={(r['facility_type'],r['facility_domain_code']) for r in rows}
    for rule in load_rules().loc[lambda f:f.decision.eq('REVIEW')].itertuples():
        if (rule.facility_type,rule.facility_domain_code) not in covered:
            rows.append(dict(facility_type=rule.facility_type,facility_domain_code=rule.facility_domain_code,
                facility_domain_label=rule.facility_domain_label,total_rows=0,landmark_supported_rows=0,support_rate=None,
                kaggle_name_only_evidence_count=0,representative_supported_attractions='[]',recommendation='KEEP_REVIEW'))
    return pd.DataFrame(rows).sort_values(['landmark_supported_rows','facility_type','facility_domain_code'],ascending=[False,True,True])


def main():
    individual,individual_schema=load_source('individual');scenic,scenic_schema=load_source('scenic')
    cp=pd.read_csv(ROOT/'data/interim/commonplace_attraction_classified.csv',dtype=CP_DTYPES)
    if len(cp)!=20451:raise ValueError('CommonPlace full-row accounting changed')
    landmarks=pd.concat([individual,scenic],ignore_index=True)
    summary,details=match_landmarks(landmarks,cp)
    accepted=summary.match_status.isin(STATUSES[:3])
    gaps=landmarks.loc[landmarks.active_designated].merge(summary[['landmark_source','landmark_source_id','match_status','evidence_reason']],
        left_on=['source','landmark_source_id'],right_on=['landmark_source','landmark_source_id'],validate='one_to_one')
    gaps=gaps.loc[~gaps.match_status.isin(STATUSES[:3])].copy()
    patterns=['museum','theater','church','cathedral','monument','memorial','market','station','bridge','library','park','house','mansion']
    gaps['inspection_keywords']=gaps.landmark_name.fillna('').map(lambda name:';'.join(p for p in patterns if re.search(r'\b'+p+r'\b',name,re.I)))
    support=subtype_support(cp,summary)
    artifacts={ROOT/'data/interim/individual_landmarks_clean.csv':individual.to_csv(index=False),
        ROOT/'data/interim/scenic_landmarks_clean.csv':scenic.to_csv(index=False),
        ROOT/'data/reports/audit/attractions/landmark_commonplace_matching_report.csv':details.to_csv(index=False),
        ROOT/'data/interim/landmark_commonplace_matching_summary.csv':summary.to_csv(index=False),
        ROOT/'data/interim/landmarks_unmatched_commonplace.csv':gaps.to_csv(index=False)}
    for decision in ['INCLUDE','REVIEW','EXCLUDE']:
        artifacts[ROOT/(f'data/interim/commonplace_{decision.lower()}_supported_by_landmarks.csv' if decision in ['REVIEW','EXCLUDE'] else f'data/reports/audit/attractions/commonplace_{decision.lower()}_supported_by_landmarks.csv')]=summary.loc[summary.match_status.eq('MATCHED_'+decision)].to_csv(index=False)
    counts=summary.groupby(['landmark_source','match_status']).size().unstack(fill_value=0).reindex(columns=STATUSES,fill_value=0)
    schemas={'individual':individual_schema,'scenic':scenic_schema}
    # JSON represents unavailable currency flags without inventing current status.
    def safe_json(value):
        if isinstance(value,dict):return {str(k):safe_json(v) for k,v in value.items()}
        if isinstance(value,list):return [safe_json(v) for v in value]
        if hasattr(value,'item'):return value.item()
        return value
    lines=['# NYC LPC landmark audit','',
        'Audit only; no taxonomy changes during matching, final attraction IDs, processed attractions table or source union.',
        '## Source schema, missingness, duplicates and status accounting','',
        '```json',json.dumps(safe_json(schemas),indent=2,default=str),'```','',
        'Individual Sites has lpc_sitest but no MOST_CURRENT/current flag or LAST_ACTION field. Only designated rows are eligible; currency cannot be independently verified and is not imputed.',
        'Scenic Landmarks requires current_=true and status=DESIGNATED; contradictory rescinded/inactive/calendared actions block eligibility.',
        'All raw records and status groups remain in the clean tables; only eligible rows enter matching. Unknown/non-designated states are not accepted.','',
        '## Geometry and matching','',
        'Socrata GeoJSON contains native projected coordinates despite its format name. Geometry is transformed from EPSG:2263 using LPC service metadata: the Socrata Shapefile .prj incorrectly labels its projected coordinates WGS84. This metadata conflict is preserved in retrieval metadata; transformed individual points are validated against source latitude/longitude. Source identities and row counts are checked between exports.',
        'Representative points are guaranteed covered by the polygon; invalid polygons are deterministically repaired and flagged. No external geocoding.',
        f'Names reuse Unicode/punctuation normalization. Fuzzy threshold={FUZZY_THRESHOLD}. Names need <=50m corroboration; exact names allow <=150m. Exact or high-confidence fuzzy names also accept polygon containment, even for large polygons whose representative point is farther away.',
        'Distance is Haversine distance to the representative point; containment is reported separately. Nearby different names and name-only matches are not accepted. Multiple supported records remain AMBIGUOUS. Source features retain distinct references; these are not canonical attraction IDs.',
        '## Match-status accounting (one row per eligible source feature)','',markdown_table(counts.reset_index()),'',
        'Full matching report contains candidate pairs; use matching_summary for source-row counts. Unique CommonPlace support is counted separately by subtype. Repeated LP numbers/features are preserved rather than silently deduplicated.',
        '## Supported REVIEW examples','',markdown_table(summary.loc[summary.match_status.eq('MATCHED_REVIEW')].head(20)),'',
        '## Supported EXCLUDE examples','',markdown_table(summary.loc[summary.match_status.eq('MATCHED_EXCLUDE')].head(20)),'',
        '## Unmatched scenic landmarks','',markdown_table(gaps.loc[gaps.source.eq(SOURCES['scenic']),['landmark_name','borough','match_status','inspection_keywords']]),'',
        '## Unmatched individual examples','',markdown_table(gaps.loc[gaps.source.eq(SOURCES['individual']),['landmark_name','designation_address','borough','match_status','inspection_keywords']].head(30)),'',
        'Keyword flags are inspection aids; individual designation does not establish tourist suitability or public access.',
        '## Borough distribution (all clean rows)','',markdown_table(landmarks.groupby(['source','borough'],dropna=False).size().reset_index(name='rows')),'']
    artifacts[ROOT/'data/reports/audit/attractions/landmark_audit.md']='\n'.join(lines)
    artifacts[ROOT/'data/reports/audit/attractions/commonplace_review_resolution_with_landmarks.md']='\n'.join([
        '# CommonPlace REVIEW resolution with landmark evidence','',markdown_table(support),'',
        'Supported individual records justify SELECTIVE_PROMOTION_NEEDED, not blanket subtype promotion. No selective promotion is applied here. Remaining mixed categories stay REVIEW.',
        'Kaggle counts are name-only candidate pairs, not confirmed identity matches. Landmark support counts unique CommonPlace source records.',
        'Zero supported rows does not establish absence of tourist relevance. Name and location differences can cause coverage gaps.',''])
    for path,content in artifacts.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    print(counts.to_string());print('Raw rows:',len(individual),len(scenic));print('Eligible rows:',int(individual.active_designated.sum()),int(scenic.active_designated.sum()));print('CommonPlace:',cp.attraction_filter_decision.value_counts().to_dict())

if __name__=='__main__':main()
