import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from scripts.restaurants import osm_enrichment as osm
from scripts.restaurants import download_restaurants_osm as downloader
class OsmTests(unittest.TestCase):
    def elements(self,names=('Cafe One',),coordinates=None,tags=None):
        return {'elements':[{'type':'node','id':i+1,'lat':40.75 if coordinates is None else coordinates[i][0],
            'lon':-73.99 if coordinates is None else coordinates[i][1],
            'tags':{'amenity':'restaurant','name':name,**(tags or {})}} for i,name in enumerate(names)]}

    def canonical(self,names=('Cafe One',)):
        frame=pd.DataFrame({k:['']*len(names) for k in osm.CORE})
        frame['name']=list(names);frame['restaurant_id']=[f'REST_{i:04d}' for i in range(len(names))]
        frame['latitude']='40.75';frame['longitude']='-73.99';frame['zipcode']='10001';frame['address']='10 Main Street'
        return frame

    def test_node_way_relation_and_raw_values(self):
        data=self.elements(tags={'opening_hours':' unsupported text ','opening_hours:kitchen':'Mo 12:00-20:00',
            'cuisine':'italian;pizza','diet:vegan':'limited'})
        for kind in ['way','relation']:
            data['elements'].append({'type':kind,'id':2,'center':{'lat':40.75,'lon':-73.99},'tags':{'amenity':'restaurant','name':'Other'}})
        clean=osm.extract_elements(data)
        self.assertEqual(set(clean.osm_type),{'node','way','relation'})
        self.assertEqual(clean.iloc[0].opening_hours_raw,' unsupported text ')
        self.assertEqual(clean.iloc[0].diet_vegan_raw,'limited')
        self.assertTrue(clean.iloc[1][osm.RAW].isna().all())
        self.assertEqual(len(osm.extract_elements({'elements':data['elements']*2})),3)

    def test_normalization_distance_and_exact_close(self):
        self.assertEqual(osm.normalize_name('Café & Joe’s'),'cafe and joes')
        self.assertAlmostEqual(osm.coordinate_distance({'latitude':0,'longitude':0},{'latitude':0,'longitude':1}),111194.9266,places=3)
        report=osm.match_records(self.canonical(),osm.extract_elements(self.elements()))
        self.assertEqual(report.match_status.tolist(),['MATCHED'])
        self.assertEqual(report.match_method.iloc[0],'exact_name_close_coordinates')

    def test_postcode_unique_and_distance_limit(self):
        data=self.elements(coordinates=[(40.7508,-73.99)],tags={'addr:postcode':'10001'})
        report=osm.match_records(self.canonical(),osm.extract_elements(data))
        self.assertEqual(report.match_method.iloc[0],'exact_name_postcode')
        data['elements'][0]['lat']=40.752
        self.assertNotIn('MATCHED',osm.match_records(self.canonical(),osm.extract_elements(data)).match_status.tolist())

    def test_chain_and_osm_duplicates_ambiguous(self):
        report=osm.match_records(self.canonical(('Cafe One','Cafe One')),osm.extract_elements(self.elements()))
        self.assertEqual(report.match_status.tolist(),['AMBIGUOUS','AMBIGUOUS'])
        report=osm.match_records(self.canonical(),osm.extract_elements(self.elements(('Cafe One','Cafe One'))))
        self.assertEqual(report.match_status.tolist(),['AMBIGUOUS','AMBIGUOUS'])
        # Name/postcode alone cannot resolve distant branches.
        report=osm.match_records(self.canonical(),osm.extract_elements(self.elements(coordinates=[(41,-73.99)],tags={'addr:postcode':'10001'})))
        self.assertNotIn('MATCHED',report.match_status.tolist())

    def test_conflicting_name_and_house_number(self):
        report=osm.match_records(self.canonical(),osm.extract_elements(self.elements(('Entirely Different',))))
        self.assertNotIn('MATCHED',report.match_status.tolist())
        report=osm.match_records(self.canonical(),osm.extract_elements(self.elements(tags={'addr:housenumber':'99','addr:street':'Main Street'})))
        self.assertNotIn('MATCHED',report.match_status.tolist())

    def test_fuzzy_name_close(self):
        c=self.canonical(('The Riverside Restaurant',))
        report=osm.match_records(c,osm.extract_elements(self.elements(('The Riverside Restaurants',))))
        self.assertEqual(report.match_status.tolist(),['MATCHED'])
        self.assertEqual(report.match_method.iloc[0],'fuzzy_name_close_coordinates')

    def test_cuisine_and_diet_semantics(self):
        self.assertEqual(osm.cuisine_values('italian;pizza;italian'),['italian','pizza'])
        for value in ['yes','no','only','limited','custom value']:
            clean=osm.extract_elements(self.elements(tags={'diet:vegan':value}))
            self.assertEqual(clean.diet_vegan_raw.iloc[0],value)

    def test_missing_fields_and_invalid_coordinates(self):
        clean=osm.extract_elements(self.elements())
        self.assertTrue(clean[osm.RAW].isna().all().all())
        unnamed=self.elements();del unnamed['elements'][0]['tags']['name']
        self.assertEqual(osm.match_records(self.canonical(),osm.extract_elements(unnamed)).match_status.tolist(),['UNMATCHED'])
        data=self.elements();del data['elements'][0]['lat']
        report=osm.match_records(self.canonical(),osm.extract_elements(data))
        self.assertEqual(report.match_status.tolist(),['REJECTED'])

    def test_frozen_core_and_failures(self):
        path=osm.ROOT/'data/processed/restaurants.csv';before=path.read_text()
        frame=pd.read_csv(io.StringIO(before),dtype=str,keep_default_na=False)
        self.assertEqual(len(frame),670)
        osm.assert_frozen(before,before)
        for changed in [frame.iloc[::-1],frame.iloc[:-1],frame.assign(name='changed'),frame.assign(restaurant_id='changed')]:
            with self.assertRaises(AssertionError):osm.assert_frozen(before,changed.to_csv(index=False))
        self.assertEqual(osm.frozen_projection(before),osm.frozen_projection(frame.to_csv(index=False)))

    def test_merge_only_matched_and_determinism(self):
        before=(osm.ROOT/'data/processed/restaurants.csv').read_text()
        canonical=pd.read_csv(io.StringIO(before),dtype=str,keep_default_na=False)
        first=canonical.iloc[0]
        data=self.elements((first['name'],),[(float(first.latitude),float(first.longitude))],
            {'opening_hours':'Mo-Fr 10:00-20:00','diet:vegan':'only','cuisine':'italian;pizza'})
        clean=osm.extract_elements(data);report=osm.match_records(canonical,clean)
        enriched=report.merge(clean[['osm_key','osm_type','osm_id',*osm.RAW]],on='osm_key')[osm.ENRICHMENT]
        output=osm.merge_csv(before,enriched)
        self.assertEqual(output,osm.merge_csv(output,enriched))
        osm.assert_frozen(before,output)
        result=pd.read_csv(io.StringIO(output),dtype=str,keep_default_na=False)
        self.assertEqual(result.iloc[0].diet_vegan,'only')
        self.assertEqual(result.iloc[0].opening_hours_kitchen_raw,'')
        self.assertEqual(result.iloc[0].opening_hours_kitchen_source,'')
        enriched['match_status']='AMBIGUOUS'
        self.assertTrue(pd.read_csv(io.StringIO(osm.merge_csv(before,enriched)),dtype=str,keep_default_na=False).opening_hours_raw.eq('').all())

    def test_failed_input_preserves_outputs_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical=Path(tmp)/'restaurants.csv';canonical.write_bytes((osm.ROOT/'data/processed/restaurants.csv').read_bytes())
            cache=Path(tmp)/'raw.json';cache.write_text('{"elements":[],"remark":"runtime error"}')
            original=canonical.read_bytes()
            with self.assertRaises(ValueError):osm.enrich_osm(canonical,cache)
            self.assertEqual(canonical.read_bytes(),original)
            with patch('urllib.request.urlopen',side_effect=TimeoutError('temporary failure')),patch('time.sleep'):
                with self.assertRaises(RuntimeError):downloader.download(canonical,cache,refresh=True)
            self.assertEqual(cache.read_text(),'{"elements":[],"remark":"runtime error"}')

    def test_cached_download_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical=osm.ROOT/'data/processed/restaurants.csv'
            box=downloader.bounding_box(pd.read_csv(canonical,dtype=str,keep_default_na=False))
            cache=Path(tmp)/'cache.json';cache.write_text(json.dumps({'elements':[],'retrieval':{'bounding_box':box}}))
            with patch('urllib.request.urlopen',side_effect=AssertionError('network called')):
                self.assertEqual(downloader.download(canonical,cache)['elements'],[])


if __name__=='__main__':unittest.main()
