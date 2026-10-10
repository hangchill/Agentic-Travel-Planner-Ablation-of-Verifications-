import sys
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from scripts.restaurants import preprocess_restaurants as pipeline
class GoogleMapsTests(unittest.TestCase):
    def raw(self):
        return pd.DataFrame({'URL':['https://example.test/a','https://example.test/b'],
            'Name':['  A  ','B'],'Rating':[4.5,None],'Rating Count':[10,None],
            'Detailed Ratings':['{}','{}'],'Price Category':[1,None],
            'Address':['  NJ address  ','NY address'],'Lat':[40.88,40.75],
            'Lon':[-74.1,-73.99],'ZipCode':['7026','10001']})

    def test_cleaning_preserves_missingness_and_all_geography(self):
        raw=self.raw();clean=pipeline.clean_google_maps(raw)
        with tempfile.TemporaryDirectory() as tmp:
            out,registry=pipeline.assign_restaurant_ids(clean,Path(tmp)/'registry.csv')
        out=pipeline.add_price_ranges(out,pipeline.load_price_mapping())
        pipeline.validate_restaurants(out,raw)
        self.assertEqual(len(out),2);self.assertEqual(out.zipcode.iloc[0],'07026')
        self.assertEqual(out.name.iloc[0],'A');self.assertEqual(out.address.iloc[0],'NJ address')
        self.assertTrue(pd.isna(out.rating.iloc[1]));self.assertTrue(pd.isna(out.price_category.iloc[1]))
        self.assertEqual(out.columns.tolist(),pipeline.COLUMNS)
        self.assertIn('price_min',out);self.assertNotIn('estimated_meal_cost',out);self.assertNotIn('opening_hours',out)

    def test_exact_full_source_duplicates_only(self):
        raw=pd.concat([self.raw(),self.raw().iloc[:1]],ignore_index=True)
        clean=pipeline.clean_google_maps(raw);self.assertEqual(len(clean),2)
        raw.loc[2,'Detailed Ratings']='different raw value'
        self.assertEqual(len(pipeline.clean_google_maps(raw)),3)

    def test_registry_reuse_and_order_independence(self):
        clean=pipeline.clean_google_maps(self.raw())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'registry.csv'
            first,registry=pipeline.assign_restaurant_ids(clean,path);registry.to_csv(path,index=False)
            second,again=pipeline.assign_restaurant_ids(clean.iloc[::-1],path)
            self.assertEqual(dict(zip(first.url,first.restaurant_id)),dict(zip(second.url,second.restaurant_id)))
            pd.testing.assert_frame_equal(registry,again)

    def test_sampling_and_manual_observations_not_overwritten(self):
        fixture=pd.DataFrame({'price_category':[1]*8+[2]*3+[None],
            'restaurant_id':[f'REST_{i:04d}' for i in range(12)],'name':[str(i) for i in range(12)],
            'rating':[4]*12,'rating_count':[10]*12,'address':['Address']*12,'url':['https://example.test']*12})
        samples=pipeline.sample_price_categories(fixture)
        self.assertEqual(samples.groupby('price_category').size().to_dict(),{1.0:5,2.0:3})
        pd.testing.assert_frame_equal(samples,pipeline.sample_price_categories(fixture.iloc[::-1]))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'manual.csv';template=pipeline.manual_price_template(samples)
            pipeline.save_manual_template(template,path)
            template.loc[0,'notes']='User observation';template.to_csv(path,index=False)
            before=path.read_bytes();pipeline.save_manual_template(pipeline.manual_price_template(samples),path)
            self.assertEqual(before,path.read_bytes())

    def test_invalid_values_and_price_mutation_fail(self):
        raw=self.raw();clean=pipeline.clean_google_maps(raw)
        with tempfile.TemporaryDirectory() as tmp:out,_=pipeline.assign_restaurant_ids(clean,Path(tmp)/'registry.csv')
        out=pipeline.add_price_ranges(out,pipeline.load_price_mapping())
        for column,value in [('rating',6),('latitude',91),('longitude',181),('name',pd.NA)]:
            broken=out.copy();broken.loc[0,column]=value
            with self.assertRaises(ValueError):pipeline.validate_restaurants(broken)
        changed=out.copy();changed.loc[0,'price_category']=4
        with self.assertRaises(AssertionError):pipeline.validate_restaurants(changed,raw)

    def test_validated_mapping_and_missing_category(self):
        mapping=pipeline.load_price_mapping()
        fixture=pd.DataFrame({column:[None]*5 for column in pipeline.BASE_COLUMNS})
        fixture['price_category']=[1,2,3,4,None]
        result=pipeline.add_price_ranges(fixture,mapping)
        self.assertEqual(result.price_min.iloc[:4].tolist(),[10,20,40,100])
        self.assertEqual(result.price_max.iloc[:3].tolist(),[20,40,100])
        self.assertTrue(pd.isna(result.price_max.iloc[3]))
        self.assertEqual(result.price_open_ended.iloc[:4].tolist(),[False,False,False,True])
        self.assertEqual(result.price_range_label.iloc[:4].tolist(),['$10–20','$20–40','$40–100','$100+'])
        self.assertTrue(result.loc[4,pipeline.PRICE_FIELDS].isna().all())
        pd.testing.assert_series_equal(fixture.price_category,result.price_category)
        self.assertNotIn('estimated_meal_cost',result)

    def test_unknown_category_and_invalid_derived_prices(self):
        mapping=pipeline.load_price_mapping()
        fixture=pd.DataFrame({column:[None] for column in pipeline.BASE_COLUMNS})
        fixture['price_category']=5
        with self.assertRaises(ValueError):pipeline.add_price_ranges(fixture,mapping)
        raw=self.raw()
        with tempfile.TemporaryDirectory() as tmp:
            base,_=pipeline.assign_restaurant_ids(pipeline.clean_google_maps(raw),Path(tmp)/'registry.csv')
        out=pipeline.add_price_ranges(base,mapping)
        for field,value in [('price_max',100),('price_open_ended',True),('price_range_label','$999')]:
            broken=out.copy();broken.loc[0,field]=value
            with self.assertRaises(AssertionError):pipeline.validate_restaurants(broken,raw,mapping)
        broken=out.copy();broken.loc[1,'price_min']=10
        with self.assertRaises(AssertionError):pipeline.validate_restaurants(broken,raw,mapping)


if __name__=='__main__':unittest.main()
