"""Explicit public-source retrieval; enrichment and tests never call this command."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

import pandas as pd
from scripts.restaurants.download_restaurants_osm import bounding_box, validate_response, ENDPOINT
from scripts.attractions.enrich_admission_costs import RAW, ROOT, TOURISM, LEISURE, normalize_osm, match_records
import csv
import re
from scripts.attractions.download_attractions import retrieve as retrieve_get


def retrieve(url, query=None):
    if query is None:
        return retrieve_get(url)
    headers = {'User-Agent': 'NYCAttractionAdmissionResearch/1.0', 'Accept': 'application/json'}
    request = urllib.request.Request(url, data=urllib.parse.urlencode({'data': query}).encode() if query else None, headers=headers)
    with urllib.request.urlopen(request, timeout=110) as response:
        return response.read()


def store(directory, source, body, url, **extra):
    json.loads(body)  # Never replace a valid cache with an HTML error page.
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{source}.json'
    temporary = path.with_suffix('.json.tmp')
    temporary.write_bytes(body)
    temporary.replace(path)
    metadata_path = directory / 'retrieval_metadata.json'
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {'sources': {}}
    metadata['sources'][source] = {'file': path.name, 'source_url': url,
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'raw_sha256': hashlib.sha256(body).hexdigest(), **extra}
    temporary = metadata_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(metadata, indent=2, sort_keys=True) + '\n')
    temporary.replace(metadata_path)


def download(directory=RAW, canonical=ROOT / 'data/processed/attractions.csv', endpoint=ENDPOINT, refresh=False):
    metadata_path = directory / 'retrieval_metadata.json'
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {'sources': {}}
    box = bounding_box(pd.read_csv(canonical))
    bounds = ','.join(f'{v:.7f}' for v in box)
    selectors = [('tourism', TOURISM), ('leisure', LEISURE)]
    # Whole-attraction selectors; normalization still rejects unrelated mixed tags.
    parts = [f'nwr["{key}"~"^({"|".join(sorted(values))})$"]["{fee}"]({bounds});'
             for key, values in selectors for fee in ('fee', 'charge', 'fee:conditional', 'charge:conditional')]
    query = '[out:json][timeout:90];(' + ''.join(parts) + ');out center tags;'
    if refresh or 'osm' not in metadata['sources']:
        body = retrieve(endpoint, query)
        validate_response(json.loads(body))
        store(directory, 'osm', body, endpoint, query=query, bounding_box=box, query_version='admission-v1')
        metadata = json.loads(metadata_path.read_text())
    elif metadata['sources']['osm'].get('bounding_box') != box:
        raise ValueError('Cached bounding box differs; use --refresh explicitly')
    osm_body = (directory / 'osm.json').read_bytes()
    if hashlib.sha256(osm_body).hexdigest() != metadata['sources']['osm']['raw_sha256']:
        raise ValueError('OSM checksum mismatch')
    osm = normalize_osm(json.loads(osm_body), metadata['sources']['osm']['retrieved_at'].split('T')[0])
    with canonical.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    matched = match_records(rows, osm)
    qids = sorted({m['record']['wikidata_id'] for m in matched if m['match_status'] == 'ACCEPTED' and re.fullmatch(r'Q\d+', m['record'].get('wikidata_id', ''))})
    if refresh or 'wikidata' not in metadata['sources']:
        entities = {}
        urls = []
        for qid in qids:
            url = f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json'
            entities.update(json.loads(retrieve(url)).get('entities', {}))
            urls.append(url)
        store(directory, 'wikidata', json.dumps({'entities': entities}, sort_keys=True).encode(),
              'https://www.wikidata.org/wiki/Special:EntityData/', entity_urls=urls,
              linked_osm_sha256=metadata['sources']['osm']['raw_sha256'])
    print(f'Cached {len(osm)} OSM fee records; inspected {len(qids)} confidently linked Wikidata entities')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=RAW)
    parser.add_argument('--endpoint', default=ENDPOINT)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--official-url', help='Associated-source structured admission records (see admission documentation)')
    args = parser.parse_args()
    if args.official_url:
        store(args.raw, 'official', retrieve(args.official_url), args.official_url)
    download(args.raw, endpoint=args.endpoint, refresh=args.refresh)


if __name__ == '__main__':
    main()
