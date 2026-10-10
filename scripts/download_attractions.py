"""Cache the CommonPlace CSV and source schema directly from NYC Open Data."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import subprocess
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = 't95h-5fsr'
SOURCE_URL = f'https://data.cityofnewyork.us/City-Government/CommonPlace/{DATASET_ID}'
CSV_URL = f'https://data.cityofnewyork.us/api/views/{DATASET_ID}/rows.csv?accessType=DOWNLOAD'
SCHEMA_URL = f'https://data.cityofnewyork.us/api/views/{DATASET_ID}.json'
TAXONOMY_URL = 'https://raw.githubusercontent.com/CityOfNewYork/nyc-geo-metadata/main/Metadata/Metadata_PointsOfInterest.md'
RAW_DIR = ROOT/'data/raw/attractions/commonplace'


def retrieve(url):
    request=urllib.request.Request(url,headers={'User-Agent':'TravelPlannerDataExploration/1.0'})
    with urllib.request.urlopen(request,timeout=120) as response:return response.read()


def download(refresh=False,raw_dir=RAW_DIR):
    csv_path=raw_dir/'commonplace.csv';metadata_path=raw_dir/'retrieval_metadata.json';schema_path=raw_dir/'source_schema.json'
    dictionary_path=raw_dir/'source_dictionary.md'
    if not refresh and all(p.exists() for p in [csv_path,metadata_path,schema_path]):
        metadata=json.loads(metadata_path.read_text())
        if hashlib.sha256(csv_path.read_bytes()).hexdigest()!=metadata['raw_sha256']:raise ValueError('Cached CommonPlace checksum mismatch')
        if not dictionary_path.exists():
            dictionary_path.write_bytes(retrieve(TAXONOMY_URL))
            metadata['taxonomy_url']=TAXONOMY_URL
            metadata['dictionary_retrieved_at']=datetime.now(timezone.utc).isoformat()
            metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
        print(f'Using cached CommonPlace: {metadata["row_count"]} rows');return metadata
    # Obtain and validate complete responses before replacing any existing cache.
    schema_bytes=retrieve(SCHEMA_URL);schema=json.loads(schema_bytes)
    dictionary=retrieve(TAXONOMY_URL)
    content=retrieve(CSV_URL)
    reader=csv.reader(io.StringIO(content.decode('utf-8-sig')))
    columns=next(reader);rows=list(reader)
    expected=[c['name'] for c in schema['columns'] if not c['fieldName'].startswith(':')]
    if columns!=expected or not rows or any(len(r)!=len(columns) for r in rows):
        raise ValueError(f'Unexpected or incomplete source CSV schema: {columns}')
    metadata={'dataset_name':schema['name'],'dataset_id':DATASET_ID,'source_url':SOURCE_URL,
        'taxonomy_url':TAXONOMY_URL,'download_url':CSV_URL,'schema_url':SCHEMA_URL,'retrieved_at':datetime.now(timezone.utc).isoformat(),
        'row_count':len(rows),'columns':columns,'raw_sha256':hashlib.sha256(content).hexdigest()}
    raw_dir.mkdir(parents=True,exist_ok=True)
    for path,data in [(csv_path,content),(schema_path,schema_bytes),(dictionary_path,dictionary),
        (metadata_path,(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n').encode())]:
        temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_bytes(data);temporary.replace(path)
    print(json.dumps(metadata,indent=2));return metadata


KAGGLE_DATASET = 'anirudhmunnangi/348-new-york-tourist-locations'
KAGGLE_RAW_DIR = ROOT/'data/raw/attractions/kaggle_tourist_locations'


def download_kaggle(refresh=False,raw_dir=KAGGLE_RAW_DIR):
    metadata_file=raw_dir/'retrieval_metadata.json'
    if metadata_file.exists() and not refresh:
        metadata=json.loads(metadata_file.read_text())
        for file in metadata['files']:
            if hashlib.sha256((raw_dir/file['filename']).read_bytes()).hexdigest()!=file['sha256']:
                raise ValueError('Kaggle cache checksum mismatch')
        print(f'Using cached Kaggle tourist source: {sum(f["row_count"] for f in metadata["files"])} rows')
        return metadata
    existing=list(raw_dir.glob('*.xlsx'))+list(raw_dir.glob('*.csv')) if raw_dir.exists() else []
    with tempfile.TemporaryDirectory() as temporary:
        staging=Path(temporary)
        if existing and not refresh:
            for path in existing:shutil.copy2(path,staging/path.name)
        else:
            subprocess.run(['kaggle','datasets','download',KAGGLE_DATASET,'-p',str(staging),'--unzip'],check=True)
        import pandas as pd
        files=[]
        for path in sorted(staging.iterdir()):
            if path.suffix.lower()=='.xlsx':
                sheets=pd.read_excel(path,sheet_name=None)
            elif path.suffix.lower()=='.csv':sheets={'csv':pd.read_csv(path)}
            else:continue
            for sheet,frame in sheets.items():
                files.append({'filename':path.name,'sheet':sheet,'row_count':len(frame),'columns':frame.columns.tolist(),
                    'dtypes':{column:str(dtype) for column,dtype in frame.dtypes.items()},
                    'missingness':{column:int(n) for column,n in frame.isna().sum().items()},
                    'exact_duplicate_rows':int(frame.duplicated().sum()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        if not files:raise ValueError('No supported Kaggle tables downloaded')
        metadata={'dataset_id':KAGGLE_DATASET,'source_url':f'https://www.kaggle.com/datasets/{KAGGLE_DATASET}',
            'retrieved_at':datetime.now(timezone.utc).isoformat(),'files':files}
        raw_dir.mkdir(parents=True,exist_ok=True)
        for path in staging.iterdir():
            if path.is_file():shutil.copy2(path,raw_dir/path.name)
        metadata_file.write_text(json.dumps(metadata,indent=2)+'\n')
        print(json.dumps(metadata,indent=2));return metadata


LANDMARK_DATASETS={'individual':'buis-pvji','scenic':'qexa-qpj6'}


def download_landmark(kind,refresh=False,raw_dir=None):
    dataset_id=LANDMARK_DATASETS[kind]
    crs_url='https://services5.arcgis.com/Oos4pNA2538iVFA1/ArcGIS/rest/services/'+('Ind_Landmark_Lots_POLY' if kind=='individual' else 'Scenic')+'/FeatureServer?f=pjson'
    raw_dir=Path(raw_dir) if raw_dir else ROOT/'data/raw/attractions/landmarks'/kind
    metadata_file=raw_dir/'retrieval_metadata.json'
    if metadata_file.exists() and not refresh:
        metadata=json.loads(metadata_file.read_text())
        for filename,checksum in metadata['checksums'].items():
            if hashlib.sha256((raw_dir/filename).read_bytes()).hexdigest()!=checksum:raise ValueError('Landmark cache checksum mismatch')
        if 'geometry_epsg' not in metadata:
            crs_bytes=retrieve(crs_url);crs_metadata=json.loads(crs_bytes);reference=crs_metadata.get('spatialReference',crs_metadata.get('fullExtent',{}).get('spatialReference',{}))
            epsg=reference.get('latestWkid',reference.get('wkid'))
            if kind=='scenic':
                # The current LPC service uses Web Mercator; request explicit 2263 and
                # verify every cached source polygon extent rather than guessing units.
                crs_url='https://services5.arcgis.com/Oos4pNA2538iVFA1/ArcGIS/rest/services/Scenic/FeatureServer/0/query?where=1%3D1&outFields=LP_NUMBER&returnGeometry=true&outSR=2263&f=json'
                crs_bytes=retrieve(crs_url);crs_metadata=json.loads(crs_bytes)
                epsg=crs_metadata['spatialReference'].get('latestWkid',crs_metadata['spatialReference'].get('wkid'))
                def bounds(points):return (min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points))
                expected={f['attributes']['LP_NUMBER']:bounds([p for ring in f['geometry']['rings'] for p in ring]) for f in crs_metadata['features']}
                def pairs(coords):
                    if isinstance(coords[0],(float,int)):yield coords
                    else:
                        for child in coords:yield from pairs(child)
                source=json.loads((raw_dir/'landmarks.geojson').read_text())
                for feature in source['features']:
                    actual=bounds(list(pairs(feature['geometry']['coordinates'])))
                    if any(abs(a-b)>5 for a,b in zip(actual,expected[feature['properties']['lp_number']])):raise ValueError('Scenic CRS evidence does not agree with source polygon extents')
            if epsg!=2263:raise ValueError('Unexpected LPC native reference; inspect before processing')
            (raw_dir/'lpc_crs_metadata.json').write_bytes(crs_bytes)
            metadata.update(geometry_epsg=epsg,crs_evidence_url=crs_url,geometry_note='Socrata geometry is native EPSG:2263; exported .prj incorrectly labels projected coordinates WGS84. LPC service metadata resolves the conflict.')
            metadata['checksums']['lpc_crs_metadata.json']=hashlib.sha256(crs_bytes).hexdigest()
            metadata_file.write_text(json.dumps(metadata,indent=2)+'\n')
        print(f'Using cached {kind} landmarks: {metadata["row_count"]} rows');return metadata
    schema_url=f'https://data.cityofnewyork.us/api/views/{dataset_id}.json'
    url=f'https://data.cityofnewyork.us/api/geospatial/{dataset_id}?method=export&format=GeoJSON'
    schema_bytes=retrieve(schema_url);schema=json.loads(schema_bytes)
    content=retrieve(url);collection=json.loads(content)
    if collection.get('type')!='FeatureCollection' or not collection.get('features'):raise ValueError('Incomplete landmark export')
    # Socrata preserves native projected coordinates even in its GeoJSON export.
    # Preserve the Shapefile projection label; resolve conflicting labels against LPC metadata.
    import zipfile
    shape_url=f'https://data.cityofnewyork.us/api/geospatial/{dataset_id}?method=export&format=Shapefile'
    archive=retrieve(shape_url)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        projections=[name for name in bundle.namelist() if name.lower().endswith('.prj')]
        if len(projections)!=1:raise ValueError('Missing or ambiguous source CRS')
        projection=bundle.read(projections[0])
    expected_count=int(json.loads(retrieve(f'https://data.cityofnewyork.us/resource/{dataset_id}.json?$select=count(*)'))[0]['count'])
    if len(collection['features'])!=expected_count:raise ValueError('Landmark export/count mismatch; retry snapshot')
    metadata={'dataset_name':schema['name'],'dataset_id':dataset_id,'retrieved_at':datetime.now(timezone.utc).isoformat(),
        'row_count':len(collection['features']),'source_url':f'https://data.cityofnewyork.us/d/{dataset_id}',
        'download_url':url,'schema_url':schema_url,'geometry_crs':projection.decode().strip(),'geometry_note':'CRS applies to Shapefile export; GeoJSON API retains native projected coordinates and is preserved only for source inspection','projection_download_url':shape_url,
        'checksums':{'landmarks.zip':hashlib.sha256(archive).hexdigest(),'source_projection.prj':hashlib.sha256(projection).hexdigest(),'landmarks.geojson':hashlib.sha256(content).hexdigest(),'source_schema.json':hashlib.sha256(schema_bytes).hexdigest()}}
    raw_dir.mkdir(parents=True,exist_ok=True)
    for filename,data in [('landmarks.zip',archive),('source_projection.prj',projection),('landmarks.geojson',content),('source_schema.json',schema_bytes),('retrieval_metadata.json',(json.dumps(metadata,indent=2)+'\n').encode())]:
        tmp=raw_dir/(filename+'.tmp');tmp.write_bytes(data);tmp.replace(raw_dir/filename)
    download_landmark(kind,False,raw_dir)
    print(json.dumps(metadata,indent=2));return json.loads(metadata_file.read_text())

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--source',choices=['commonplace','kaggle','individual','scenic','landmarks'],default='commonplace')
    args=parser.parse_args()
    if args.source in ['individual','scenic']:download_landmark(args.source,args.refresh)
    elif args.source=='landmarks':
        for kind in LANDMARK_DATASETS:download_landmark(kind,args.refresh)
    else:(download_kaggle if args.source=='kaggle' else download)(args.refresh)


if __name__=='__main__':main()
