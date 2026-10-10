"""Stream accepted Google reviews into an identity-free SQLite cache and freeze text corpora."""
from pathlib import Path
import csv,gzip,json,sqlite3,hashlib,re,unicodedata
from datetime import datetime,timezone
from collections import Counter
import pandas as pd
from download_review_corpus import download
from download_reviews import ROOT,RAW
MAX_TEXT_REVIEWS_PER_ENTITY=100
RANDOM_STATE=42
DB=ROOT/'data/interim/google_local_matched_reviews.sqlite'
REPORT=ROOT/'data/reports'

def clean_text(value):
    if value is None:return ''
    if not isinstance(value,str):raise ValueError('Review text must be string/null')
    return re.sub(r'\s+',' ',unicodedata.normalize('NFC',value)).strip()

def convert_time(value):
    if value is None:return None,None
    try:
        dt=datetime.fromtimestamp(float(value)/1000,timezone.utc)
        return dt.isoformat(),dt.date().isoformat()
    except (ValueError,TypeError,OverflowError,OSError):return None,None

def review_row(row):
    text=clean_text(row.get('text'));timestamp=row.get('time');rating=row.get('rating')
    if rating is not None and (not isinstance(rating,(int,float)) or isinstance(rating,bool) or rating not in [1,2,3,4,5]):raise ValueError('Unexpected rating')
    identity=json.dumps([row['gmap_id'],text,rating,timestamp],ensure_ascii=False,separators=(',',':'))
    key=hashlib.sha256(identity.encode()).hexdigest();dt,date=convert_time(timestamp)
    rank=hashlib.sha256((str(RANDOM_STATE)+':'+key).encode()).hexdigest()
    return (key,row['gmap_id'],rating,text,timestamp,dt,date,bool(text),rank)

def extract(path,registry,database,provenance):
    accepted=set(registry.gmap_id);database=Path(database);database.parent.mkdir(parents=True,exist_ok=True)
    part=database.with_suffix('.partial.sqlite');part.unlink(missing_ok=True)
    conn=sqlite3.connect(part);conn.execute('PRAGMA journal_mode=OFF');conn.execute('PRAGMA synchronous=OFF')
    conn.execute('CREATE TABLE reviews (source_review_key TEXT PRIMARY KEY,gmap_id TEXT,rating REAL,review_text TEXT,review_timestamp REAL,review_datetime TEXT,review_date TEXT,has_review_text INTEGER,sample_rank TEXT)')
    counters={g:dict(total_reviews=0,text_reviews=0,ratings_only_reviews=0,exact_duplicates_removed=0,invalid_timestamps=0) for g in accepted}
    keys=Counter();types={};missing=Counter();raw=matched=0
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for raw,line in enumerate(f,1):
            row=json.loads(line)
            for k,v in row.items():
                keys[k]+=1;types.setdefault(k,Counter())[type(v).__name__]+=1
                if v is None:missing[k]+=1
            gid=row.get('gmap_id')
            if gid in accepted:
                values=review_row(row);c=counters[gid];matched+=1;c['total_reviews']+=1;c['text_reviews' if values[7] else 'ratings_only_reviews']+=1
                if values[4] is not None and values[5] is None:c['invalid_timestamps']+=1
                inserted=conn.execute('INSERT OR IGNORE INTO reviews VALUES (?,?,?,?,?,?,?,?,?)',values).rowcount
                c['exact_duplicates_removed']+=int(not inserted)
            if raw%1000000==0:conn.commit();print('Scanned reviews:',raw,'matched:',matched,flush=True)
    conn.commit();conn.execute('CREATE INDEX entity_reviews ON reviews(gmap_id,has_review_text,review_timestamp DESC,source_review_key)');conn.execute('CREATE INDEX diversity ON reviews(gmap_id,has_review_text,rating,sample_rank)')
    stats=dict(provenance=provenance,raw_source_reviews=raw,raw_matched_reviews=matched,keys=dict(keys),types={k:dict(v) for k,v in types.items()},nulls=dict(missing),missing_fields={k:raw-n for k,n in keys.items()},entities=counters,timestamp_unit='epoch milliseconds; UTC')
    conn.execute('CREATE TABLE extraction_metadata (json TEXT)');conn.execute('INSERT INTO extraction_metadata VALUES (?)',(json.dumps(stats),));conn.commit();conn.close();part.replace(database);return stats

def select_reviews(conn,gid,cap=MAX_TEXT_REVIEWS_PER_ENTITY):
    # Recent first; deterministic content-key ties. Rating round robin adds at most
    # 40 from the remaining history using seeded SHA-256 ranks rather than RNG order.
    conn.row_factory=sqlite3.Row
    count=conn.execute('SELECT COUNT(*) FROM reviews WHERE gmap_id=? AND has_review_text=1',(gid,)).fetchone()[0]
    if count<=cap:return [dict(r) for r in conn.execute('SELECT * FROM reviews WHERE gmap_id=? AND has_review_text=1 ORDER BY review_timestamp DESC,source_review_key',(gid,))]
    chosen=[dict(r) for r in conn.execute('SELECT * FROM reviews WHERE gmap_id=? AND has_review_text=1 ORDER BY review_timestamp DESC,source_review_key LIMIT ?',(gid, min(60,cap)))]
    seen={r['source_review_key'] for r in chosen}
    groups=[]
    for rating in [1,2,3,4,5,None]:
        groups.append(iter(conn.execute('SELECT * FROM reviews WHERE gmap_id=? AND has_review_text=1 AND rating IS ? ORDER BY sample_rank,source_review_key',(gid,rating))))
    while len(chosen)<cap:
        progress=False
        for group in groups:
            for row in group:
                if row['source_review_key'] in seen:continue
                chosen.append(dict(row));seen.add(row['source_review_key']);progress=True;break
            if len(chosen)==cap:break
        if not progress:raise AssertionError('Sampling exhausted unexpectedly')
    return sorted(chosen,key=lambda r: (-(r['review_timestamp'] if r['review_timestamp'] is not None else float('-inf')),r['source_review_key']))

def assign_ids(keys,path,prefix):
    columns=['source_review_key','review_id'];old=pd.read_csv(path,dtype=str) if path.exists() else pd.DataFrame(columns=columns)
    if old.source_review_key.duplicated().any() or old.review_id.duplicated().any():raise ValueError('Review ID registry collision')
    mapping=dict(zip(old.source_review_key,old.review_id));next_id=max([int(v.split('_')[1]) for v in mapping.values()]+[0])+1
    for key in sorted(set(keys)-mapping.keys()):mapping[key]=f'{prefix}_{next_id:06d}';next_id+=1
    frame=pd.DataFrame(sorted(mapping.items(),key=lambda p:p[1]),columns=columns);path.parent.mkdir(parents=True,exist_ok=True);frame.to_csv(path,index=False);return mapping

def validate_output(frame,kind,canonical,registry):
    expected=[kind+'_review_id',kind+'_id','gmap_id','rating','review_text','review_date','source','source_review_key']
    assert list(frame.columns)==expected
    assert frame[kind+'_id'].isin(canonical[kind+'_id']).all()
    pairs=set(zip(registry.entity_id,registry.gmap_id));assert set(zip(frame[kind+'_id'],frame.gmap_id)).issubset(pairs)
    assert frame.review_text.map(lambda t:isinstance(t,str) and bool(t.strip())).all()
    assert not frame[kind+'_review_id'].duplicated().any() and not frame.source_review_key.duplicated().any()
    assert frame.groupby(kind+'_id').size().le(MAX_TEXT_REVIEWS_PER_ENTITY).all()

def table(frame):return frame.to_csv(index=False).strip()

def build(database,registry,stats):
    REPORT.mkdir(parents=True,exist_ok=True);conn=sqlite3.connect(database);coverage=[];summaries=[]
    for kind,plural,prefix in [('restaurant','restaurants','RR'),('attraction','attractions','AR')]:
        canonical=pd.read_csv(ROOT/f'data/processed/{plural}.csv');names=canonical.set_index(kind+'_id')['name'].to_dict();selected=[];entity_rows=[]
        for e in registry.loc[registry.entity_type.eq(kind)].sort_values('entity_id').itertuples():
            c=dict(stats['entities'][e.gmap_id]);bounds=conn.execute('SELECT MIN(review_date),MAX(review_date),SUM(has_review_text),COUNT(*) FROM reviews WHERE gmap_id=?',(e.gmap_id,)).fetchone()
            samples=select_reviews(conn,e.gmap_id)
            record=dict(entity_type=kind,entity_id=e.entity_id,gmap_id=e.gmap_id,entity_name=names[e.entity_id],**c,earliest_review_date=bounds[0],latest_review_date=bounds[1],unique_text_reviews=bounds[2] or 0,unique_reviews=bounds[3],processed_reviews=len(samples))
            coverage.append(record);entity_rows.append(record)
            for r in samples:selected.append(dict(entity_id=e.entity_id,**r))
        idmap=assign_ids([r['source_review_key'] for r in selected],ROOT/f'data/metadata/{kind}_review_id_registry.csv',prefix)
        columns=[kind+'_review_id',kind+'_id','gmap_id','rating','review_text','review_date','source','source_review_key']
        output=pd.DataFrame([{columns[0]:idmap[r['source_review_key']],columns[1]:r['entity_id'],**{k:r[k] for k in ['gmap_id','rating','review_text','review_date','source_review_key']},'source':'google_local_2021'} for r in selected],columns=columns)
        validate_output(output,kind,canonical,registry.loc[registry.entity_type.eq(kind)])
        output.to_csv(ROOT/f'data/processed/{kind}_reviews.csv',index=False)
        cov=pd.DataFrame(entity_rows);quantiles=[]
        for field in ['total_reviews','text_reviews','unique_text_reviews']:
            s=cov[field];quantiles.append(dict(measure=field,minimum=int(s.min()),p25=s.quantile(.25),median=s.median(),p75=s.quantile(.75),p90=s.quantile(.9),p95=s.quantile(.95),maximum=int(s.max()),mean=s.mean()))
        bins=pd.cut(cov.text_reviews,[-1,0,4,9,24,49,99,float('inf')],labels=['0','1–4','5–9','10–24','25–49','50–99','100+']).value_counts(sort=False)
        summary=dict(entity_type=kind,canonical_entities=len(canonical),matched_entities=len(cov),entities_with_source_reviews=int(cov.total_reviews.gt(0).sum()),entities_with_text_reviews=int(cov.text_reviews.gt(0).sum()),text_coverage_percent=100*cov.text_reviews.gt(0).sum()/len(canonical),raw_matched_reviews=int(cov.total_reviews.sum()),text_reviews=int(cov.text_reviews.sum()),ratings_only_reviews=int(cov.ratings_only_reviews.sum()),exact_duplicates_found=int(cov.exact_duplicates_removed.sum()),duplicates_removed=int(cov.exact_duplicates_removed.sum()),entities_requiring_cap=int(cov.unique_text_reviews.gt(100).sum()),entities_at_100=int(cov.processed_reviews.eq(100).sum()),entities_below_cap=int(cov.processed_reviews.lt(100).sum()),processed_reviews=len(output),date_min=output.review_date.dropna().min() if output.review_date.notna().any() else None,date_max=output.review_date.dropna().max() if output.review_date.notna().any() else None)
        summaries.append(summary)
        lines=[f'# {kind.title()} review corpus','',json.dumps(summary,indent=2),'','## Source review-count distribution (includes zero-review matched entities)','','```csv',table(pd.DataFrame(quantiles)),'```','','## Text-review count bins','','```csv',bins.to_csv(),'```','','## Processed rating distribution','','```csv',output.rating.value_counts().sort_index().to_csv(),'```','','## Processed date distribution (UTC year)','','```csv',output.review_date.str[:4].value_counts().sort_index().to_csv(),'```']
        gids=registry.loc[registry.entity_type.eq(kind),'gmap_id'].tolist()
        placeholders=','.join('?' for _ in gids)
        source_ratings=pd.read_sql_query(f'SELECT rating,COUNT(*) AS unique_reviews FROM reviews WHERE gmap_id IN ({placeholders}) GROUP BY rating ORDER BY rating',conn,params=gids)
        source_dates=pd.read_sql_query(f'SELECT SUBSTR(review_date,1,4) AS utc_year,COUNT(*) AS unique_reviews FROM reviews WHERE gmap_id IN ({placeholders}) GROUP BY utc_year ORDER BY utc_year',conn,params=gids)
        lines+=['','## Unique source rating distribution (before cap; text and ratings-only)','','```csv',table(source_ratings),'```','','## Unique source date distribution (before cap; UTC year)','','```csv',table(source_dates),'```']
        if kind=='attraction':
            groups=canonical.merge(cov,left_on='attraction_id',right_on='entity_id',how='left').groupby('category').agg(canonical=('attraction_id','size'),matched=('gmap_id','count'),with_text=('text_reviews',lambda s:s.fillna(0).gt(0).sum()),processed_reviews=('processed_reviews','sum'))
            lines+=['','## Category coverage','','```csv',groups.to_csv(),'```']
        (REPORT/f'{kind}_review_report.md').write_text('\n'.join(lines)+'\n')
    pd.DataFrame(coverage).to_csv(REPORT/'google_local_review_coverage.csv',index=False)
    (REPORT/'google_local_review_extraction.json').write_text(json.dumps({k:v for k,v in stats.items() if k!='entities'},indent=2)+'\n')
    policy='Historical snapshot through September 2021; fixed offline evidence, recent observations within that snapshot, rating diversity, and bounded LLM retrieval cost. The sample is not statistically representative of all Google reviews. Missing mapping or zero text reviews means UNKNOWN / review evidence unavailable, never negative subjective evidence. No subjective labels or reviewer profiles are created.'
    (REPORT/'review_dataset_summary.md').write_text('# Offline review corpus summary\n\n'+json.dumps({k:v for k,v in stats.items() if k not in ['entities','keys','types','nulls','missing_fields']},indent=2)+'\n\n'+table(pd.DataFrame(summaries))+'\n\n'+policy+'\n\nCap 100: all unique text reviews retained up to the cap; otherwise 60 most recent plus 40 historical selections round-robin across available 1–5 ratings (null ratings last), each stratum ordered by SHA-256 of seed 42 and source review key. Timestamp ties use content key. Exact duplicates use gmap_id, normalized text, rating, and original timestamp; source_review_key is their SHA-256, with no user identity. Coverage source counts are before deduplication; unique counts and processed counts are separate. UTC epoch milliseconds conversion; invalid dates remain null and sort last. SQLite interim stores all unique accepted observations including ratings-only, without source names, user IDs, photos, or responses. IDs persist in append-only key registries, including formerly selected keys.\n')
    conn.close();print(json.dumps(summaries,indent=2),flush=True)

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--reextract',action='store_true');args=p.parse_args()
    registry_path=ROOT/'data/metadata/google_local_entity_registry.csv';registry=pd.read_csv(registry_path)
    assert len(registry)==887 and registry.match_confidence.eq('HIGH').all() and not registry.gmap_id.duplicated().any()
    meta=download();provenance=dict(review_sha256=meta['sha256'],registry_sha256=hashlib.sha256(registry_path.read_bytes()).hexdigest(),download=meta,policy_version=1)
    if DB.exists() and not args.reextract:
        with sqlite3.connect(DB) as conn:stats=json.loads(conn.execute('SELECT json FROM extraction_metadata').fetchone()[0])
        if stats['provenance']!=provenance:raise ValueError('Interim provenance changed: explicitly reextract')
        print('Using completed single-pass extraction cache',flush=True)
    else:stats=extract(RAW/meta['filename'],registry,DB,provenance)
    build(DB,registry,stats)
if __name__=='__main__':main()
