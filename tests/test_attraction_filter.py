import hashlib
from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import filter_attractions as filtering


class AttractionFilterTests(unittest.TestCase):
    def rows(self,pairs):
        return pd.DataFrame({'facility_type':pd.Series([t for t,d in pairs],dtype='string'),
            'facility_domain':pd.Series([d for t,d in pairs],dtype='string'),
            'facility_domain_label':[None]*len(pairs),'name':[f'Feature {i}' for i in range(len(pairs))],
            'source_record_id':[f'{i:04d}' for i in range(len(pairs))],
            'latitude':[40.75]*len(pairs),'longitude':[-73.99]*len(pairs)})

    def test_include_exclude_review_and_unmapped(self):
        pairs=[('3','4'),('4','1'),('4','6'),('1','1'),('2','1'),('8','1'),('9','1'),('13','5'),('99','99')]
        result=filtering.classify_rows(self.rows(pairs),filtering.load_rules())
        self.assertEqual(result.attraction_filter_decision.tolist(),
            ['INCLUDE','INCLUDE','INCLUDE','EXCLUDE','EXCLUDE','EXCLUDE','REVIEW','REVIEW','UNMAPPED'])
        self.assertEqual(result.facility_domain_label.iloc[7],'UNKNOWN_UNDOCUMENTED')
        self.assertTrue(pd.isna(result.facility_domain_label_raw.iloc[7]))
        self.assertTrue(result.attraction_filter_reason.notna().all())

    def test_name_flags_do_not_change_taxonomy_decisions(self):
        rows=self.rows([('3','4'),('1','1')]);rows['name']=['SCHOOL ADMIN OFFICE','MUSEUM TOURIST ATTRACTION']
        result=filtering.classify_rows(rows,filtering.load_rules())
        self.assertEqual(result.attraction_filter_decision.tolist(),['INCLUDE','EXCLUDE'])
        flagged=filtering.candidate_name_flags(result.loc[result.attraction_filter_decision.eq('INCLUDE')])
        self.assertEqual(len(flagged),1)
        self.assertIn('school_like',flagged.name_review_flags.iloc[0])
        self.assertIn('office_like',flagged.name_review_flags.iloc[0])

    def test_duplicate_rules_cannot_multiply_rows(self):
        rules=filtering.load_rules();rules=pd.concat([rules,rules.iloc[:1]],ignore_index=True)
        with self.assertRaises(ValueError):filtering.classify_rows(self.rows([('1','1')]),rules)

    def test_snapshot_partition_and_raw_field_preservation(self):
        clean=pd.read_csv(filtering.CLEAN_FILE,dtype=filtering.SOURCE_DTYPES)
        classified,pools,audits,flags=filtering.build_artifacts(clean,filtering.load_rules())
        self.assertEqual(len(classified),20451)
        self.assertEqual(sum(len(pool) for pool in pools.values()),20451)
        self.assertEqual(classified.source_record_id.tolist(),clean.source_record_id.tolist())
        for column in clean.columns:
            if column=='facility_domain_label':continue
            pd.testing.assert_series_equal(clean[column],classified[column],check_names=False)
        self.assertEqual(len(pools['REVIEW'].loc[pools['REVIEW'].facility_domain_label.eq('UNKNOWN_UNDOCUMENTED')]),220)
        for decision,pool in pools.items():self.assertTrue(pool.attraction_filter_decision.eq(decision).all())
        self.assertNotIn('attraction_id',classified)

    def test_repeat_outputs_and_reordered_sampling_are_deterministic(self):
        clean=pd.read_csv(filtering.CLEAN_FILE,dtype=filtering.SOURCE_DTYPES);rules=filtering.load_rules()
        _,a,aa,_=filtering.build_artifacts(clean,rules)
        _,b,ba,_=filtering.build_artifacts(clean,rules)
        for decision in filtering.DECISIONS:
            self.assertEqual(a[decision].to_csv(index=False),b[decision].to_csv(index=False))
        for decision in filtering.DECISIONS[:-1]:
            reordered=filtering.subtype_audit(filtering.classify_rows(clean.iloc[::-1],rules),rules,decision)
            self.assertEqual(aa[decision].to_csv(index=False),ba[decision].to_csv(index=False))
            self.assertEqual(aa[decision].to_csv(index=False),reordered.to_csv(index=False))


if __name__=='__main__':unittest.main()
