"""Conservative cached Overpass retrieval; successful responses replace cache atomically."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.parse
import urllib.error

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data/raw/restaurants/osm/restaurants.json'
ENDPOINT = 'https://overpass-api.de/api/interpreter'
QUERY_VERSION = 'restaurant-bbox-v1'


def bounding_box(frame, margin=0.005):
    lat = pd.to_numeric(frame.latitude, errors='raise')
    lon = pd.to_numeric(frame.longitude, errors='raise')
    if lat.isna().any() or lon.isna().any() or not lat.between(-90,90).all() or not lon.between(-180,180).all():
        raise ValueError('Invalid canonical coordinates')
    return [float(lat.min()-margin), float(lon.min()-margin), float(lat.max()+margin), float(lon.max()+margin)]


def query_for(box):
    bounds = ','.join(f'{v:.7f}' for v in box)
    return f'[out:json][timeout:90];nwr["amenity"="restaurant"]({bounds});out center tags;'


def validate_response(data):
    if not isinstance(data,dict) or 'remark' in data or not isinstance(data.get('elements'),list):
        raise ValueError('Incomplete or failed Overpass response')
    keys=set()
    for element in data['elements']:
        key=(element.get('type'),element.get('id'))
        if key[0] not in {'node','way','relation'} or not isinstance(key[1],int):
            raise ValueError('Invalid Overpass element')
        keys.add(key)
    return data


def download(canonical, cache=CACHE, endpoint=ENDPOINT, refresh=False):
    core=canonical.read_bytes()
    frame=pd.read_csv(canonical,dtype=str,keep_default_na=False)
    if len(frame)!=670 or frame.restaurant_id.duplicated().any():
        raise ValueError('Expected frozen 670 canonical restaurants')
    box=bounding_box(frame)
    if cache.exists() and not refresh:
        data=validate_response(json.loads(cache.read_text()))
        if data.get('retrieval',{}).get('bounding_box')!=box:
            raise ValueError('Cache bounding box differs; explicitly refresh')
        print(f'Using cached OSM input: {len(data["elements"])} records')
        return data
    query=query_for(box)
    for attempt in range(3):
        try:
            request=urllib.request.Request(endpoint, data=urllib.parse.urlencode({'data':query}).encode(),
                headers={'User-Agent':'RestaurantResearchPipeline/1.0 (conservative cached retrieval)'})
            with urllib.request.urlopen(request,timeout=110) as response:
                data=validate_response(json.load(response))
            unique={(e['type'],e['id']):e for e in data['elements']}
            data['elements']=[unique[key] for key in sorted(unique)]
            data['retrieval']={'retrieved_at':datetime.now(timezone.utc).isoformat(),
                'overpass_endpoint':endpoint,'query_version':QUERY_VERSION,'query':query,
                'bounding_box':box,'canonical_file_sha256':hashlib.sha256(core).hexdigest()}
            cache.parent.mkdir(parents=True,exist_ok=True)
            temporary=cache.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            temporary.replace(cache)
            print(f'Retrieved {len(unique)} OSM restaurants from {endpoint}')
            return data
        except (urllib.error.URLError,TimeoutError,ValueError) as error:
            if isinstance(error,urllib.error.HTTPError) and error.code not in {429,500,502,503,504}:
                raise
            print(f'Overpass attempt {attempt+1} failed: {error}',flush=True)
            if attempt==2:
                raise RuntimeError('OSM retrieval failed / coverage unknown; existing cache and outputs preserved') from error
            time.sleep(5*(attempt+1))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--endpoint',default=ENDPOINT)
    args=parser.parse_args()
    download(ROOT/'data/processed/restaurants.csv',endpoint=args.endpoint,refresh=args.refresh)


if __name__=='__main__':main()
