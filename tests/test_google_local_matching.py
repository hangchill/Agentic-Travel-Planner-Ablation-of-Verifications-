import sys
import unittest
from pathlib import Path
import json,gzip,tempfile
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import google_local_matching as g
from download_reviews import discover

class GoogleLocalMatchingTests(unittest.TestCase):
    def entity(self,name='Example Restaurant',kind='restaurant',latitude=40.75,longitude=-74,address='123 Main Street, New York, NY 10001',identity='REST_1',category='museum'):
        return dict(entity_type=kind,entity_id=identity,entity_name=name,name_normalized=g.normalize_name(name),alias_normalized=g.alias_name(name),latitude=latitude,longitude=longitude,
            address_normalized=g.clean_address(address,name),address=address,zipcode=g.zipcode(address),category=category)
    def google(self,name='Example Restaurant',latitude=40.75,longitude=-74,address='123 Main St, New York, NY 10001',identity='G1',categories='Restaurant'):
        return dict(gmap_id=identity,name=name,name_normalized=g.normalize_name(name),alias_normalized=g.alias_name(name),latitude=latitude,longitude=longitude,
            address=address,address_normalized=g.clean_address(address,name),zipcode=g.zipcode(address),categories_raw=json.dumps([categories]))
    def test_registry_integrity(self):
        entities=pd.DataFrame([self.entity()])
        registry=pd.DataFrame([dict(entity_type='restaurant',entity_id='REST_1',gmap_id='G1',match_confidence='HIGH')])
        g.validate_registry(registry,entities)
        for field,value in [('entity_id','UNKNOWN'),('match_confidence','MEDIUM'),('gmap_id',None)]:
            bad=registry.copy();bad.loc[0,field]=value
            with self.assertRaises(AssertionError):g.validate_registry(bad,entities)
        with self.assertRaises(AssertionError):g.validate_registry(pd.concat([registry,registry]),entities)
    def test_exact_name_coord(self):self.assertEqual(g.evaluate(self.entity(),self.google())['match_status'],'MATCHED')
    def test_exact_name_address_missing_coordinates(self):self.assertEqual(g.evaluate(self.entity(latitude=None,longitude=None),self.google(latitude=None,longitude=None))['match_status'],'MATCHED')
    def test_fuzzy_requires_threshold_and_address(self):
        self.assertEqual(g.evaluate(self.entity(),self.google(name='Example Restaurantt'))['match_status'],'MATCHED')
        self.assertNotEqual(g.evaluate(self.entity(),self.google(name='Unrelated Restaurant'))['match_status'],'MATCHED')
        self.assertNotEqual(g.evaluate(self.entity(),self.google(name='Example Restaurantt',address=None))['match_status'],'MATCHED')
    def test_same_name_far(self):self.assertEqual(g.evaluate(self.entity(),self.google(latitude=41))['match_status'],'REJECTED')
    def test_ambiguous_businesses(self):
        summary,_,_=g.match_entities(pd.DataFrame([self.entity()]),[self.google(),self.google(identity='G2')]);self.assertEqual(summary.match_status.iloc[0],'AMBIGUOUS')
    def test_attraction_exact(self):self.assertEqual(g.evaluate(self.entity(name='Example Museum',kind='attraction'),self.google(name='Example Museum',categories='Museum'))['match_status'],'MATCHED')
    def test_deterministic_alias(self):self.assertEqual(g.evaluate(self.entity(name='Fort Example Park',kind='attraction',category='park'),self.google(name='Ft Example Park',categories='Park'))['match_status'],'MATCHED')
    def test_constituent_separate(self):self.assertNotEqual(g.evaluate(self.entity(name='Example Park',kind='attraction',category='park'),self.google(name='Example Park Zoo',categories='Zoo'))['match_status'],'MATCHED')
    def test_generic_far(self):self.assertNotEqual(g.evaluate(self.entity(name='Park',kind='attraction',category='park'),self.google(name='Park',latitude=41,categories='Park'))['match_status'],'MATCHED')
    def test_gmap_collision_quarantined(self):
        a=self.entity(identity='REST_1');b=self.entity(identity='REST_2')
        summary,_,collisions=g.match_entities(pd.DataFrame([a,b]),[self.google()]);self.assertEqual(summary.match_status.tolist(),['AMBIGUOUS','AMBIGUOUS']);self.assertEqual(len(collisions),2)
    def test_conflicting_raw_id_not_accepted(self):
        summary,_,_=g.match_entities(pd.DataFrame([self.entity()]),[self.google()],{'G1'});self.assertEqual(summary.match_status.iloc[0],'REJECTED')
    def test_determinism(self):
        entities=pd.DataFrame([self.entity()]);a=g.match_entities(entities,[self.google()]);b=g.match_entities(entities,[self.google()])
        self.assertEqual([f.to_csv(index=False) for f in a],[f.to_csv(index=False) for f in b])
    def test_metadata_stream_and_quality_accounting(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'meta.json.gz';rows=[dict(name='Example Restaurant',gmap_id='G1',address='Example Restaurant, 123 Main Street, New York, NY 10001',latitude=40.75,longitude=-74,category=['Restaurant']),dict(name='Example Restaurant',gmap_id='G1',latitude=42,longitude=-74)]
            with gzip.open(p,'wt') as stream:
                for row in rows:stream.write(json.dumps(row)+'\n')
            out=Path(directory)/'clean.csv';stats=g.clean_metadata(p,pd.DataFrame([self.entity()]),out)
            self.assertEqual(stats['raw_rows'],2);self.assertEqual(stats['retained_nyc_rows'],1);self.assertEqual(stats['duplicate_gmap_id_values'],1);self.assertEqual(stats['conflicting_duplicate_gmap_ids'],['G1'])
            clean=pd.read_csv(out);self.assertEqual(clean.address_normalized.iloc[0],'123 main st new york ny 10001')
    def test_download_discovery(self):
        self.assertTrue(discover('<a href="meta-New_York.json.gz">metadata</a>').endswith('meta-New_York.json.gz'))
        with self.assertRaises(ValueError):discover('<a href="review-New_York.json.gz">reviews</a>')

if __name__=='__main__':unittest.main()
