"""Download ONLY complete New York business metadata discovered from the official index."""
from datetime import datetime,timezone
from html.parser import HTMLParser
import gzip
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from urllib.parse import urljoin

ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/'data/raw/reviews/google_local_2021'
SOURCE_URL='https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/'

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.links.extend(v for k,v in attrs if k=='href')


def discover(html):
    parser=Links();parser.feed(html)
    links=[urljoin(SOURCE_URL,link) for link in parser.links if re.search(r'(?:meta|metadata)[-_]New_York\.json\.gz$',link)]
    links=sorted(set(links))
    if len(links)!=1:raise ValueError('Official New York complete metadata link is missing/ambiguous')
    return links[0]


def download(refresh=False,raw_dir=RAW):
    raw_dir=Path(raw_dir);record=raw_dir/'retrieval_metadata.json'
    if record.exists() and not refresh:
        metadata=json.loads(record.read_text());digest=hashlib.sha256()
        with (raw_dir/metadata['filename']).open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=metadata['sha256']:raise ValueError('Cached Google Local metadata checksum mismatch')
        print('Cached metadata:',metadata['filename']);return metadata
    with urllib.request.urlopen(SOURCE_URL,timeout=120) as response:html=response.read().decode()
    url=discover(html);filename=url.rsplit('/',1)[1]
    raw_dir.mkdir(parents=True,exist_ok=True);temporary=raw_dir/(filename+'.part');digest=hashlib.sha256();size=0
    with urllib.request.urlopen(url,timeout=120) as response,temporary.open('wb') as destination:
        length=response.headers.get('Content-Length')
        for chunk in iter(lambda:response.read(1024*1024),b''):
            destination.write(chunk);digest.update(chunk);size+=len(chunk)
    if length and size!=int(length):raise ValueError('Incomplete metadata download')
    with gzip.open(temporary,'rt') as stream:
        first=json.loads(next(stream))
        if not isinstance(first,dict) or 'gmap_id' not in first:raise ValueError('Not business metadata')
    metadata={'source':'google_local_2021','source_url':SOURCE_URL,'download_url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),
        'filename':filename,'file_size_bytes':size,'sha256':digest.hexdigest(),'snapshot_coverage':'through September 2021','role':'fixed offline experimental subjective-constraint review corpus; metadata-only matching stage'}
    temporary.replace(raw_dir/filename);(raw_dir/'source_index.html').write_text(html);record.write_text(json.dumps(metadata,indent=2)+'\n');print(json.dumps(metadata,indent=2));return metadata

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--refresh',action='store_true');download(parser.parse_args().refresh)
