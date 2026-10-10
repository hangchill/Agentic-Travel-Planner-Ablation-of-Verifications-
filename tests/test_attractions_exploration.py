import sys
from pathlib import Path
import unittest
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import explore_attractions as explore


class AttractionsExplorationTests(unittest.TestCase):
    def fixture(self):
        raw=pd.DataFrame({column:pd.Series(['',''],dtype='string') for column in explore.FIELDS.values()}).replace('',pd.NA)
        raw['FEATURE NAME']=['SAME NAME','SAME NAME']
        raw['OBJECTID']=['001','002'];raw['PLACEID']=['11','12']
        raw['FACILITY TYPE']=['4','13'];raw['FACILITY DOMAINS']=['1','5']
        raw['BOROUGH CODE']=['1','8'];raw['the_geom']=['POINT (-73.99 40.75)',pd.NA]
        taxonomy=pd.DataFrame({'facility_type':['4','13'],'facility_domain':['1','1'],
            'facility_type_label':['Recreational Facility','Miscellaneous'],
            'facility_domain_label':['Park','Official Landmark'],'source_url':['source','source']})
        return raw,taxonomy

    def test_row_ids_geometry_and_raw_values_preserved(self):
        raw,taxonomy=self.fixture();clean=explore.clean_exploration(raw,taxonomy)
        self.assertEqual(len(clean),2);self.assertEqual(clean.source_record_id.tolist(),['001','002'])
        self.assertEqual(clean.longitude.iloc[0],-73.99);self.assertEqual(clean.latitude.iloc[0],40.75)
        self.assertTrue(pd.isna(clean.latitude.iloc[1]))
        self.assertEqual(clean.borough.iloc[0],'Manhattan');self.assertTrue(pd.isna(clean.borough.iloc[1]))
        self.assertTrue(pd.isna(clean.facility_domain_label.iloc[1]))
        self.assertEqual(clean.facility_type_label.iloc[1],'Miscellaneous')
        for column in raw:pd.testing.assert_series_equal(clean['raw_'+column],raw[column],check_names=False)
        self.assertNotIn('attraction_id',clean)

    def test_samples_stable_and_keywords_only_categories(self):
        raw,taxonomy=self.fixture();raw.loc[1,'FEATURE NAME']='MUSEUM GARDEN TOURIST ATTRACTION'
        clean=explore.clean_exploration(raw,taxonomy)
        candidate,_=explore.category_masks(clean)
        self.assertEqual(candidate.tolist(),[True,False])
        a=explore.deterministic_samples(clean,'facility_domain')
        b=explore.deterministic_samples(clean.iloc[::-1],'facility_domain')
        pd.testing.assert_frame_equal(a,b)

    def test_missing_source_field_fails_without_guessing(self):
        raw,taxonomy=self.fixture()
        with self.assertRaises(ValueError):explore.clean_exploration(raw.drop(columns='FACILITY TYPE'),taxonomy)

    def test_dictionary_parses_last_pipe_delimited_code(self):
        types='<br>'.join(f'{i} = Type {i}' for i in range(1,14))
        text=f'| FACILITY_T | Categories<br>{types} | integer |\n| FACI_DOM | Values<br>Type 13<br>1 = Landmark<br>4 = Other | text |'
        taxonomy=explore.taxonomy_from_dictionary(text)
        self.assertEqual(taxonomy.facility_domain.tolist(),['1','4'])
        self.assertEqual(taxonomy.facility_domain_label.tolist(),['Landmark','Other'])


if __name__=='__main__':unittest.main()
