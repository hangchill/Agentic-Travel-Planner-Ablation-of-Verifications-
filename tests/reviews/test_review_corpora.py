import unittest,tempfile,gzip,json,sqlite3,sys
from pathlib import Path
import pandas as pd
from scripts.reviews import build_review_corpora as b
from scripts.reviews.download_review_corpus import discover_review

class ReviewCorpusTests(unittest.TestCase):
    def fixture(self,rows):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);root=Path(folder.name);source=root/'reviews.gz';db=root/'reviews.sqlite'
        with gzip.open(source,'wt') as f:
            for r in rows:f.write(json.dumps(r)+'\n')
        registry=pd.DataFrame([dict(gmap_id='G1')]);stats=b.extract(source,registry,db,{})
        return db,stats,root
    def row(self,i,text='Great food!',gid='G1',rating=5):return dict(gmap_id=gid,time=1600000000000+i*1000,rating=rating,text=text,name='Private reviewer',user_id='private')
    def test_stream_filter_and_schema(self):
        db,stats,_=self.fixture([self.row(0),self.row(1,gid='G2')]);self.assertEqual(stats['raw_source_reviews'],2);self.assertEqual(stats['raw_matched_reviews'],1)
        with sqlite3.connect(db) as c:
            self.assertEqual(c.execute('select count(*) from reviews').fetchone()[0],1)
            fields=[r[1] for r in c.execute('pragma table_info(reviews)')];self.assertNotIn('name',fields);self.assertNotIn('user_id',fields)
    def test_empty_text(self):
        db,stats,_=self.fixture([self.row(i,text=t) for i,t in enumerate([None,'',' \n\t','Good'])])
        with sqlite3.connect(db) as c:self.assertEqual(len(b.select_reviews(c,'G1')),1)
        self.assertEqual(stats['entities']['G1']['ratings_only_reviews'],3)
    def test_clean_wording(self):self.assertEqual(b.clean_text('  Great\r\nfood!\tNot quiet.  '),'Great food! Not quiet.')
    def test_utc_timestamp(self):self.assertEqual(b.convert_time(1600000000000),('2020-09-13T12:26:40+00:00','2020-09-13'));self.assertEqual(b.convert_time('invalid'),(None,None))
    def test_exact_duplicates(self):
        row=self.row(0);db,stats,_=self.fixture([row,row,self.row(1)])
        self.assertEqual(stats['entities']['G1']['exact_duplicates_removed'],1)
        with sqlite3.connect(db) as c:self.assertEqual(len(b.select_reviews(c,'G1')),2)
    def test_below_and_at_cap(self):
        for n in [0,1,99,100]:
            db,_,_=self.fixture([self.row(i,text=str(i)) for i in range(n)])
            with sqlite3.connect(db) as c:self.assertEqual(len(b.select_reviews(c,'G1')),n)
    def test_cap_diversity_recency_determinism(self):
        rows=[self.row(i,text=str(i),rating=1+i%5 if i<150 else 5) for i in range(300)];db,_,_=self.fixture(rows)
        with sqlite3.connect(db) as c:
            a=b.select_reviews(c,'G1');again=b.select_reviews(c,'G1')
        self.assertEqual(a,again);self.assertEqual(len(a),100);self.assertEqual({r['rating'] for r in a},{1,2,3,4,5})
        self.assertTrue({b.review_row(r)[0] for r in rows[-60:]}.issubset({r['source_review_key'] for r in a}))
        db2,_,_=self.fixture(list(reversed(rows)))
        with sqlite3.connect(db2) as c:self.assertEqual(a,b.select_reviews(c,'G1'))
    def test_stable_append_ids(self):
        with tempfile.TemporaryDirectory() as d:
            for prefix in ['RR','AR']:
                path=Path(d)/(prefix+'.csv');a=b.assign_ids(['z','m'],path,prefix);first=path.read_bytes();self.assertEqual(a,b.assign_ids(['m','z'],path,prefix));self.assertEqual(first,path.read_bytes());new=b.assign_ids(['a','z'],path,prefix);self.assertEqual(a['z'],new['z']);self.assertEqual(a['m'],new['m']);self.assertEqual(new['a'],prefix+'_000003')
    def test_integrity_and_privacy(self):
        columns=['restaurant_review_id','restaurant_id','gmap_id','rating','review_text','review_date','source','source_review_key']
        frame=pd.DataFrame([['RR_000001','REST_1','G1',5,'Good','2020-01-01','google_local_2021','key']],columns=columns)
        canonical=pd.DataFrame([dict(restaurant_id='REST_1')]);registry=pd.DataFrame([dict(entity_id='REST_1',gmap_id='G1')]);b.validate_output(frame,'restaurant',canonical,registry)
        for field,value in [('restaurant_id','ORPHAN'),('gmap_id','G2'),('review_text','')]:
            bad=frame.copy();bad.loc[0,field]=value
            with self.assertRaises(AssertionError):b.validate_output(bad,'restaurant',canonical,registry)
        with self.assertRaises(AssertionError):b.validate_output(frame.assign(reviewer_name='private'),'restaurant',canonical,registry)
    def test_official_complete_link(self):
        html='<a href="review-New_York.json.gz">full</a><a href="ratings-New_York.csv">ratings</a>'
        self.assertTrue(discover_review(html).endswith('/review-New_York.json.gz'))
        with self.assertRaises(ValueError):discover_review('<a href="New_York_10.json.gz">core</a>')
if __name__=='__main__':unittest.main()
