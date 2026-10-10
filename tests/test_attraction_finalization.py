import sys
import unittest
from pathlib import Path
import json
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import finalize_attractions as f

class AttractionFinalizationTests(unittest.TestCase):
    def candidate(self,name='Visitor Museum',origin='UNMATCHED_INDIVIDUAL_LANDMARK'):
        source='nyc_lpc_scenic_landmarks' if origin=='UNMATCHED_SCENIC_LANDMARK' else 'nyc_lpc_individual_landmarks'
        return dict(candidate_name=name,candidate_origin=origin,latitude=40.75,longitude=-74,landmark_supported=origin.startswith('COMMONPLACE'),
            landmark_evidence=json.dumps([dict(source=source,source_id='1',name=name)]))
    def decide(self,name='Visitor Museum',origin='UNMATCHED_INDIVIDUAL_LANDMARK',base=None):
        c=self.candidate(name,origin);source=json.loads(c['landmark_evidence'])[0]['source']
        landmarks=pd.DataFrame([dict(source=source,landmark_source_id='1',active_designated=True,geometry_wkt=None)])
        b=pd.DataFrame(base or [],columns=['name','latitude','longitude','source_record_id'])
        return f.curate(pd.DataFrame([c]),b,f.load_rules(),landmarks).iloc[0]
    def test_scenic(self):self.assertEqual(self.decide('Scenic Site','UNMATCHED_SCENIC_LANDMARK').auto_decision,'ADD')
    def test_landmark_review(self):self.assertEqual(self.decide('Community Chapel','COMMONPLACE_REVIEW_LANDMARK_SUPPORTED').auto_decision,'ADD')
    def test_review_infrastructure(self):self.assertEqual(self.decide('Historic Comfort Station','COMMONPLACE_REVIEW_LANDMARK_SUPPORTED').auto_decision,'DO_NOT_ADD')
    def test_museum(self):self.assertEqual(self.decide().auto_decision,'ADD')
    def test_residential(self):self.assertEqual(self.decide('Historic Apartments').auto_decision,'DO_NOT_ADD')
    def test_conflict(self):self.assertEqual(self.decide('Museum Office Building').auto_decision,'DO_NOT_ADD')
    def test_exclude_needs_positive(self):
        self.assertEqual(self.decide('Business Headquarters','COMMONPLACE_EXCLUDE_LANDMARK_SUPPORTED').auto_decision,'DO_NOT_ADD')
        self.assertEqual(self.decide('Public Library','COMMONPLACE_EXCLUDE_LANDMARK_SUPPORTED').auto_decision,'ADD')
    def test_alias(self):
        row=self.decide(base=[dict(name='Visitor Museum',latitude=40.75,longitude=-74,source_record_id='C1')]);self.assertEqual(row.auto_decision,'ALIAS_OF_EXISTING');self.assertEqual(row.alias_target,'C1')
    def test_far_name_not_alias(self):self.assertEqual(self.decide(base=[dict(name='Visitor Museum',latitude=40.85,longitude=-74,source_record_id='C1')]).auto_decision,'ADD')
    def test_constituent_is_not_whole_alias(self):self.assertEqual(self.decide('Prospect Park','UNMATCHED_SCENIC_LANDMARK',base=[dict(name='Prospect Park Zoo',latitude=40.75,longitude=-74,source_record_id='C1')]).auto_decision,'ADD')
    def test_ambiguous_alias_excluded(self):
        rows=[dict(name='Visitor Museum',latitude=40.75,longitude=-74,source_record_id=i) for i in ['C1','C2']]
        self.assertEqual(self.decide(base=rows).auto_decision,'DO_NOT_ADD')
    def test_stable_registry_and_append(self):
        empty=pd.DataFrame(columns=['canonical_key','attraction_id']);a,r=f.assign_ids(['b','a'],empty);b,r2=f.assign_ids(['c','a','b'],r)
        self.assertEqual(a['a'],b['a']);self.assertEqual(a['b'],b['b']);self.assertEqual(b['c'],'ATTR_0003')
        _,r3=f.assign_ids(['c','b','a'],r2);self.assertEqual(r2.to_csv(index=False),r3.to_csv(index=False))
    def test_no_kaggle_only_add(self):self.assertEqual(self.decide('Ordinary Institution').auto_decision,'DO_NOT_ADD')
    def test_determinism(self):
        c=self.candidate();landmarks=pd.DataFrame([dict(source='nyc_lpc_individual_landmarks',landmark_source_id='1',active_designated=True,geometry_wkt=None)])
        base=pd.DataFrame(columns=['name','latitude','longitude','source_record_id'])
        a=f.curate(pd.DataFrame([c]),base,f.load_rules(),landmarks);b=f.curate(pd.DataFrame([c]),base,f.load_rules(),landmarks)
        self.assertEqual(a.to_csv(index=False),b.to_csv(index=False))

    def test_alias_does_not_append_final_row(self):
        base=pd.DataFrame([dict(name='Visitor Museum',latitude=40.75,longitude=-74,source_record_id='C1',
            facility_type='3',facility_domain_code='4',facility_domain_label='Museum',borough='Manhattan')])
        row=self.candidate();row.update(curation_candidate_id='CUR_0001',auto_decision='ALIAS_OF_EXISTING',alias_target='C1',auto_reason='Strong name/location agreement')
        matched=pd.DataFrame(columns=['commonplace_source_id','match_status','landmark_source','landmark_source_id','landmark_name'])
        categories=pd.DataFrame([dict(facility_type='3',facility_domain_code='4',category='museum')])
        union,resolutions=f.build_union(base,pd.DataFrame([row]),matched,categories)
        self.assertEqual(len(union),1);self.assertEqual(resolutions.resolution.tolist(),['ALIAS_OF_EXISTING'])
        self.assertTrue(union.is_landmark.iloc[0])

    def test_retired_registry_ids_stay_reserved(self):
        registry=pd.DataFrame([dict(canonical_key='old',attraction_id='ATTR_0009')])
        mapping,updated=f.assign_ids(['new'],registry)
        self.assertEqual(mapping['old'],'ATTR_0009');self.assertEqual(mapping['new'],'ATTR_0010');self.assertEqual(len(updated),2)

if __name__=='__main__':unittest.main()
