import sys
import unittest
from pathlib import Path
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon, mapping, Point
from shapely import wkt
from scripts.attractions import audit_landmarks as a
class LandmarkAuditTests(unittest.TestCase):
    def geometry(self):return Polygon([(-74.001,40.749),(-73.999,40.749),(-73.999,40.751),(-74.001,40.751)])
    def landmarks(self,name='Central Park',geometry=None,kind='individual',**properties):
        props=dict(objectid='123',lpc_name=name,lpc_lpnumb='LP-001',lpc_sitest='Designated',borough='MN',address='Example address')
        if kind=='scenic':props=dict(scen_lm_na=name,lp_number='LP-001',status='DESIGNATED',current_='true',last_actio='DESIGNATED',borough='MN')
        props.update(properties)
        return a.clean_features([{'properties':props,'geometry':mapping(geometry if geometry is not None else self.geometry())}],kind)
    def cp(self,name='Central Park',latitude=40.75,longitude=-74,**kwargs):
        row=dict(name=name,latitude=latitude,longitude=longitude,source_record_id='001',attraction_filter_decision='REVIEW',facility_type='4',facility_domain_code='1',facility_domain_label='Park')
        row.update(kwargs);return pd.DataFrame([row])
    def status(self,l,c):return a.match_landmarks(l,c)[0].match_status.iloc[0]
    def test_geometry_and_representative_point(self):
        result=self.landmarks();g=wkt.loads(result.geometry_wkt.iloc[0]);self.assertTrue(g.covers(Point(result.longitude.iloc[0],result.latitude.iloc[0])))
        self.assertEqual(result.coordinate_method.iloc[0],'representative_point')
        self.assertEqual(result.landmark_source_id.iloc[0],'123')
    def test_multipolygon(self):
        result=self.landmarks(geometry=MultiPolygon([self.geometry()]));self.assertTrue(result.latitude.notna().all())
    def test_status_filtering(self):
        for props in [dict(status='CALENDARED'),dict(status='RESCINDED'),dict(current_='false'),dict(last_actio='RESCINDED'),dict(current_=None)]:
            self.assertFalse(self.landmarks(kind='scenic',**props).active_designated.iloc[0])
        self.assertTrue(self.landmarks(kind='scenic').active_designated.iloc[0])
        self.assertFalse(self.landmarks(lpc_sitest='Calendared').active_designated.iloc[0])
        self.assertFalse(self.landmarks().currency_verified.iloc[0])
    def test_name_and_borough(self):
        result=self.landmarks(name='  Museum & Park  ',borough='QN');self.assertEqual(result.name_normalized.iloc[0],'museum and park');self.assertEqual(result.borough.iloc[0],'QN')
    def test_exact_close(self):self.assertEqual(self.status(self.landmarks(),self.cp()),'MATCHED_REVIEW')
    def test_fuzzy_close(self):self.assertEqual(self.status(self.landmarks(name='Central Parkk'),self.cp()),'MATCHED_REVIEW')
    def test_same_name_far(self):self.assertEqual(self.status(self.landmarks(),self.cp(latitude=40.8)),'REJECTED')
    def test_large_polygon_containment(self):
        geometry=Polygon([(-74.1,40.6),(-73.9,40.6),(-73.9,40.9),(-74.1,40.9)])
        summary,_=a.match_landmarks(self.landmarks(geometry=geometry),self.cp(latitude=40.88))
        self.assertEqual(summary.match_status.iloc[0],'MATCHED_REVIEW');self.assertGreater(summary.distance_meters.iloc[0],150);self.assertTrue(summary.geometry_contains.iloc[0])
    def test_ambiguous(self):
        cp=pd.concat([self.cp(),self.cp(source_record_id='002')],ignore_index=True)
        self.assertEqual(self.status(self.landmarks(),cp),'AMBIGUOUS')
    def test_unmatched(self):self.assertEqual(self.status(self.landmarks(),self.cp(name='Unrelated destination')),'UNMATCHED')
    def test_decisions_not_promoted(self):
        for decision in ['INCLUDE','REVIEW','EXCLUDE']:self.assertEqual(self.status(self.landmarks(),self.cp(attraction_filter_decision=decision)),'MATCHED_'+decision)
    def test_determinism(self):
        for x,y in zip(a.match_landmarks(self.landmarks(),self.cp()),a.match_landmarks(self.landmarks(),self.cp())):self.assertEqual(x.to_csv(index=False),y.to_csv(index=False))
    def test_inactive_never_matched(self):self.assertTrue(a.match_landmarks(self.landmarks(lpc_sitest='Rescinded'),self.cp())[0].empty)
    def test_projected_geometry(self):
        from pyproj import Transformer
        from shapely import transform
        transformer=Transformer.from_crs(4326,2263,always_xy=True)
        projected=transform(self.geometry(),transformer.transform,interleaved=False)
        _,lat,lon,_=a.representative_geometry(mapping(projected),'EPSG:2263')
        self.assertAlmostEqual(lat,40.75,places=3);self.assertAlmostEqual(lon,-74,places=3)

if __name__=='__main__':unittest.main()
