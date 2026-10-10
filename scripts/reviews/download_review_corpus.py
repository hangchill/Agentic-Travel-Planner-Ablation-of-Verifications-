"""Discover and cache the official complete New York review split, without identities in logs."""
from scripts.reviews.download_reviews import Links,SOURCE_URL,RAW
from urllib.parse import urljoin
import urllib.request,json,hashlib,gzip,re,time
from datetime import datetime,timezone

def discover_review(html):
    parser=Links();parser.feed(html)
    urls=sorted(set(urljoin(SOURCE_URL,p) for p in parser.links if re.search(r'/review-New_York\.json\.gz$',urljoin(SOURCE_URL,p))))
    if len(urls)!=1:raise ValueError('Complete New York review link missing/ambiguous')
    return urls[0]

def download():
    record=RAW/'review_retrieval_metadata.json'
    if record.exists():
        meta=json.loads(record.read_text());digest=hashlib.sha256()
        with (RAW/meta['filename']).open('rb') as f:
            for chunk in iter(lambda:f.read(4*1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=meta['sha256']:raise ValueError('Review cache checksum mismatch')
        print('Verified cached review split',flush=True);return meta
    with urllib.request.urlopen(SOURCE_URL,timeout=120) as f:html=f.read().decode()
    url=discover_review(html);filename=url.rsplit('/',1)[1];RAW.mkdir(parents=True,exist_ok=True)
    part=RAW/(filename+'.part');digest=hashlib.sha256();size=0;last=time.monotonic()
    with urllib.request.urlopen(url,timeout=120) as response,part.open('wb') as out:
        length=response.headers.get('Content-Length')
        for chunk in iter(lambda:response.read(4*1024*1024),b''):
            out.write(chunk);digest.update(chunk);size+=len(chunk)
            if time.monotonic()-last>30:print('Downloaded bytes:',size,flush=True);last=time.monotonic()
    if length and size!=int(length):raise ValueError('Incomplete review download')
    with gzip.open(part,'rt') as f:
        row=json.loads(next(f))
        if not {'gmap_id','rating','time'}.issubset(row):raise ValueError('Unexpected review schema')
    meta=dict(source='google_local_2021',download_url=url,retrieved_at=datetime.now(timezone.utc).isoformat(),filename=filename,file_size_bytes=size,sha256=digest.hexdigest(),snapshot_coverage='through September 2021')
    part.replace(RAW/filename);record.write_text(json.dumps(meta,indent=2)+'\n');print(json.dumps(meta),flush=True);return meta
if __name__=='__main__':download()
