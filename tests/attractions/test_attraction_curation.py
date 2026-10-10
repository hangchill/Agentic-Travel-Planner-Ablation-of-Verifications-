import sys
import unittest
from pathlib import Path
import pandas as pd
from shapely.geometry import Polygon
from scripts.attractions import build_attraction_curation as c
class AttractionCurationTests(unittest.TestCase):
    def landmark(self,name='Town Library',identity='L1',source='nyc_lpc_individual_landmarks',latitude=40.75,longitude=-74,lp='LP1'):
        return dict(landmark_name=name,landmark_source_id=identity,source=source,latitude=latitude,longitude=longitude,
            borough='MN',designation_address='1 Main Street',lp_number=lp,active_designated=True,coordinate_method='representative_point',geometry_wkt=None)
    def cp(self,name='Town Library',identity='C1',decision='REVIEW',latitude=40.75,longitude=-74):
        return dict(name=name,source_record_id=identity,attraction_filter_decision=decision,latitude=latitude,longitude=longitude,
            borough='Manhattan',facility_type='3',facility_domain_code='2',facility_domain_label='Library')
    def run_build(self,landmarks=None,cp=None,matches=None,gaps=None,weak=None,cap=200):
        cp=pd.DataFrame(cp or [self.cp()]);landmarks=pd.DataFrame(landmarks or [self.landmark()])
        matches=pd.DataFrame(matches or [],columns=['landmark_source','landmark_source_id','commonplace_source_id','commonplace_filter_decision','match_status','match_method','match_confidence'])
        gaps=pd.DataFrame(gaps or [],columns=list(self.landmark())+['match_status'])
        weak=pd.DataFrame(weak or [],columns=['commonplace_source_id','commonplace_name','kaggle_name'])
        return c.build_curation(cp,landmarks,matches,gaps,weak,cap)
    def supported(self,decision='REVIEW'):
        return dict(landmark_source='nyc_lpc_individual_landmarks',landmark_source_id='L1',commonplace_source_id='C1',
            commonplace_filter_decision=decision,match_status='MATCHED_'+decision,match_method='exact_name_within_50m',match_confidence=1)
    def test_landmark_supported_review(self):
        frame,_=self.run_build(matches=[self.supported()]);self.assertEqual(frame.candidate_origin.tolist(),[c.ORIGINS[0]])
    def test_landmark_supported_exclude(self):
        frame,_=self.run_build(cp=[self.cp(decision='EXCLUDE')],matches=[self.supported('EXCLUDE')]);self.assertEqual(frame.candidate_origin.tolist(),[c.ORIGINS[1]])
    def test_unmatched_scenic(self):
        scenic=self.landmark(name='Scenic Site',source='nyc_lpc_scenic_landmarks');frame,_=self.run_build(gaps=[dict(scenic,match_status='UNMATCHED')]);self.assertEqual(frame.candidate_origin.tolist(),[c.ORIGINS[2]])
    def test_ordinary_individual_requires_signal(self):
        rows=[dict(self.landmark(name='123 Main Street',identity='L1'),match_status='UNMATCHED'),dict(self.landmark(name='Historic Street Lamppost',identity='L2'),match_status='UNMATCHED'),dict(self.landmark(name='Residential Tower',identity='L3'),match_status='UNMATCHED')]
        frame,_=self.run_build(gaps=rows);self.assertTrue(frame.empty)
    def test_visitor_keyword_individual(self):
        frame,_=self.run_build(gaps=[dict(self.landmark(),match_status='REJECTED')]);self.assertEqual(len(frame),1)
    def test_alias_search(self):
        frame,_=self.run_build(cp=[self.cp(name='Town Library Center',decision='INCLUDE')],gaps=[dict(self.landmark(),match_status='UNMATCHED')]);self.assertTrue(frame.possible_existing_include_match.iloc[0]);self.assertEqual(frame.possible_existing_include_source_id.iloc[0],'C1')
    def test_far_name_not_alias(self):
        frame,_=self.run_build(cp=[self.cp(decision='INCLUDE',latitude=41)],gaps=[dict(self.landmark(),match_status='UNMATCHED')]);self.assertFalse(frame.possible_existing_include_match.iloc[0])
    def test_polygon_constituent_alias(self):
        landmark=self.landmark(name='Prospect Park');landmark['geometry_wkt']=Polygon([(-74.1,40.6),(-73.9,40.6),(-73.9,40.9),(-74.1,40.9)]).wkt
        frame,_=self.run_build(cp=[self.cp(name='Prospect Park Carousel',decision='INCLUDE',latitude=40.88)],gaps=[dict(landmark,match_status='UNMATCHED')]);self.assertTrue(frame.possible_existing_include_match.iloc[0]);self.assertGreater(frame.possible_existing_include_distance_m.iloc[0],150)
    def test_manual_fields_and_temporary_ids(self):
        frame,_=self.run_build(matches=[self.supported()]);self.assertTrue(frame[c.MANUAL_FIELDS].eq('').all().all());self.assertEqual(frame.curation_candidate_id.iloc[0],'CUR_0001')
    def test_determinism_and_cap(self):
        rows=[dict(self.landmark(name='Town '+str(i)+' Library',identity='L'+str(i),lp='LP'+str(i),latitude=40.75+i*.01),match_status='UNMATCHED') for i in range(5)]
        first,stats=self.run_build(gaps=rows,cap=2);second,_=self.run_build(gaps=list(reversed(rows)),cap=2)
        self.assertEqual(first.to_csv(index=False),second.to_csv(index=False));self.assertEqual(stats['individual_truncated'],3)
    def test_dedup_source_refs(self):
        frame,_=self.run_build(matches=[self.supported(),self.supported()]);self.assertEqual(len(frame),1)
    def test_distant_branches_preserved(self):
        rows=[dict(self.landmark(identity='L1'),match_status='UNMATCHED'),dict(self.landmark(identity='L2',latitude=40.85),match_status='UNMATCHED')]
        frame,_=self.run_build(gaps=rows);self.assertEqual(len(frame),2)
    def test_kaggle_only_never_originates_candidate(self):
        weak=[dict(commonplace_source_id='C1',commonplace_name='Town Library',kaggle_name='Town Library')]
        frame,_=self.run_build(weak=weak);self.assertTrue(frame.empty)
        frame,_=self.run_build(weak=weak,matches=[self.supported()]);self.assertTrue(frame.kaggle_name_support.iloc[0])

    def test_proximity_chain_does_not_merge_branches(self):
        rows=[dict(self.landmark(identity='L'+str(i),latitude=40.75+i*.00036),match_status='UNMATCHED') for i in range(3)]
        frame,_=self.run_build(gaps=rows)
        self.assertEqual(len(frame),2)

    def test_existing_manual_edits_are_protected(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            path=Path(directory)/'final_attraction_curation_manual.csv'
            content='manual_decision,manual_reason,manual_notes\nADD,user reason,\n'
            path.write_text(content)
            with patch.object(c,'REPORTS',Path(directory)):
                with self.assertRaisesRegex(ValueError,'refusing to overwrite'):c.main()
            self.assertEqual(path.read_text(),content)

if __name__=='__main__':unittest.main()
