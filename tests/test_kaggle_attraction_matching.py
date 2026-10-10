import sys
import unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import match_attractions_kaggle as m

class KaggleMatchingTests(unittest.TestCase):
    def kg(self, name='Chelsea Market', zipcode='10011', address='75 Ninth Avenue'):
        return m.clean_kaggle(pd.DataFrame({'Tourist_Spot':[name], 'Address':[address], 'Zipcode':[zipcode]}))

    def cp(self, decision='REVIEW', **changes):
        row=dict(name='Chelsea Market', zipcode='10011', address='75 Ninth Avenue', source_record_id='001', attraction_filter_decision=decision)
        row.update(changes)
        return pd.DataFrame([row])

    def status(self, kg, cp, **kwargs):
        return m.match_rows(kg, cp, **kwargs)[0].match_status.iloc[0]

    def test_exact_zip_and_classifications(self):
        for decision in ['INCLUDE', 'REVIEW']:
            self.assertEqual(self.status(self.kg(), self.cp(decision)), 'MATCHED_'+decision)

    def test_exact_address(self):
        summary, _, _ = m.match_rows(self.kg(zipcode=None), self.cp(zipcode=None))
        self.assertEqual(summary.match_method.iloc[0], 'exact_name_address')

    def test_fuzzy_threshold(self):
        kg=self.kg(name='Chelsea Markett')
        self.assertEqual(self.status(kg,self.cp(),threshold=.94),'MATCHED_REVIEW')
        self.assertEqual(self.status(kg,self.cp(),threshold=.99),'UNMATCHED')

    def test_name_only_ambiguity(self):
        cp=pd.concat([self.cp(zipcode=None,address=None),self.cp(zipcode=None,address=None,source_record_id='002')],ignore_index=True)
        self.assertEqual(self.status(self.kg(),cp),'AMBIGUOUS')
        self.assertEqual(self.status(self.kg(),cp.iloc[:1]),'REJECTED')

    def test_exclude_diagnostic_only(self):
        cp=self.cp('EXCLUDE')
        self.assertEqual(self.status(self.kg(),cp,diagnostic_exclude=False),'UNMATCHED')
        self.assertEqual(self.status(self.kg(),cp),'MATCHED_EXCLUDE')
        cp=pd.concat([self.cp('INCLUDE'),cp],ignore_index=True)
        self.assertEqual(self.status(self.kg(),cp),'MATCHED_INCLUDE')

    def test_unmatched(self):
        self.assertEqual(self.status(self.kg(name='Completely unrelated location'),self.cp()),'UNMATCHED')

    def test_determinism(self):
        a=m.match_rows(self.kg(),self.cp());b=m.match_rows(self.kg(),self.cp())
        self.assertEqual([x.to_csv(index=False) for x in a[:2]],[x.to_csv(index=False) for x in b[:2]])

    def test_competing_aliases_remain_unrepresented(self):
        kg=pd.concat([self.kg(),self.kg()],ignore_index=True);kg.loc[1,'kaggle_row_id']='KAGGLE_ROW_0002'
        summary,_,gaps=m.match_rows(kg,self.cp())
        self.assertEqual(summary.match_status.tolist(),['AMBIGUOUS','AMBIGUOUS'])
        self.assertEqual(len(gaps),2)

    def test_conflicting_zip_blocks_address_match(self):
        self.assertEqual(self.status(self.kg(),self.cp(zipcode='10012')),'REJECTED')

    def test_coordinate_match_and_conflict(self):
        kg=self.kg(zipcode=None,address=None);kg['latitude']=40.75;kg['longitude']=-73.99
        cp=self.cp(zipcode=None,address=None,latitude=40.75,longitude=-73.99)
        self.assertEqual(self.status(kg,cp),'MATCHED_REVIEW')
        cp['latitude']=40.8
        self.assertEqual(self.status(kg,cp),'REJECTED')

    def test_raw_preservation_and_explicit_zip(self):
        kg=self.kg(name='  Chelsea & Market  ',zipcode=None,address='75 Ninth Avenue, New York, NY 10011')
        self.assertEqual(kg.name_raw.iloc[0],'  Chelsea & Market  ')
        self.assertEqual(kg.zipcode.iloc[0],'10011')
        self.assertEqual(kg.name_normalized.iloc[0],'chelsea and market')

if __name__=='__main__':unittest.main()
