import csv
from datetime import date
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import restaurant_hours as hours
import osm_enrichment as osm


class HoursTests(unittest.TestCase):
    def test_default_daily_and_provenance(self):
        for raw in [None,'',float('nan')]:
            fields=hours.hours_fields(raw)
            self.assertEqual(fields['opening_hours_source'],'experimental_default')
            self.assertTrue(fields['opening_hours_is_assumed'])
            schedule=json.loads(fields['opening_hours_effective'])
            self.assertEqual(schedule['format'],'weekly')
            self.assertEqual(set(schedule['schedule']),set(hours.DAYS))
            self.assertTrue(all(v==[['11:00','22:00']] for v in schedule['schedule'].values()))
            self.assertEqual(fields['holiday_rule_status'],'ASSUMED')
            self.assertEqual(fields['holiday_rule_source'],'experimental_default')
            self.assertFalse(fields['has_explicit_holiday_rule'])

    def test_observed_verbatim_and_kitchen_unchanged(self):
        row={'opening_hours_raw':' Mo-Fr 11:00-22:00; Sa-Su 12:00-23:00 ',
             'opening_hours_kitchen_raw':'Mo 12:00-18:00','other':'preserved'}
        result=hours.add_hours_rows([row])[0]
        self.assertEqual(result['opening_hours_raw'],row['opening_hours_raw'])
        self.assertEqual(result['opening_hours_kitchen_raw'],row['opening_hours_kitchen_raw'])
        self.assertEqual(result['opening_hours_source'],'openstreetmap')
        self.assertFalse(result['opening_hours_is_assumed'])
        self.assertEqual(json.loads(result['opening_hours_effective'])['raw'],row['opening_hours_raw'])
        self.assertEqual(result['holiday_rule_status'],'UNKNOWN')
        self.assertIsNone(result['holiday_rule_source'])
        result=hours.add_hours_rows([{'opening_hours_raw':None,'opening_hours_kitchen_raw':None}])[0]
        self.assertIsNone(result['opening_hours_kitchen_raw'])
        self.assertNotIn('opening_hours_kitchen',result)

    def test_ph_classification(self):
        for rule,status in [('PH off','EXPLICIT_CLOSED'),('PH closed','EXPLICIT_CLOSED'),
            ('PH open','EXPLICIT_OPEN'),('PH 24/7','EXPLICIT_OPEN'),
            ('PH 12:00-18:00','EXPLICIT_SPECIAL_HOURS'),('PH 12:00-14:00,16:00-20:00','EXPLICIT_SPECIAL_HOURS')]:
            raw='Mo-Fr 10:00-20:00; '+rule
            result=hours.holiday_rule(raw)
            self.assertTrue(result['has_explicit_holiday_rule'])
            self.assertEqual(result['holiday_rule_status'],status)
            self.assertEqual(result['holiday_rule_raw'],raw)
            self.assertEqual(result['holiday_rule_source'],'openstreetmap')

    def test_complex_ph_preserved_unknown(self):
        for raw in ['Mo-Fr,PH 12:00-18:00','PH off; PH 12:00-18:00','PH +1 day off',
            'PH 12:00-18:00 || 24/7','PH 25:00-26:00','PH 22:00-02:00','PH 12:00-12:00',
            'PH off "except special events"','PH off "unclosed']:
            result=hours.holiday_rule(raw)
            self.assertTrue(result['has_explicit_holiday_rule'],raw)
            self.assertEqual(result['holiday_rule_status'],'UNKNOWN',raw)
            self.assertEqual(result['holiday_rule_raw'],raw)

    def test_no_ph_or_comment_only(self):
        for raw in ['Mo-Su 10:00-22:00','Mo-Su 10:00-22:00 "PH off"','Mo-Su 10:00-22:00 "comment; PH off"','PHONY']:
            result=hours.holiday_rule(raw)
            self.assertFalse(result['has_explicit_holiday_rule'])
            self.assertEqual(result['holiday_rule_status'],'UNKNOWN')
            self.assertIsNone(result['holiday_rule_source'])
            self.assertIsNone(result['holiday_rule_raw'])

    def test_known_calendar_and_scope(self):
        calendar=hours.load_holiday_calendar()
        for day,name in [('2026-01-01',"New Year's Day"),('2026-11-26','Thanksgiving Day'),
                         ('2026-07-04','Independence Day')]:
            self.assertEqual(hours.holiday_for_date(day,calendar)['holiday_name'],name)
        self.assertEqual(hours.holiday_for_date('2026-07-03',calendar)['holiday_type'],'federal_observed')
        self.assertIsNone(hours.holiday_for_date(date(2026,7,2),calendar))
        with self.assertRaises(ValueError):hours.holiday_for_date('2027-01-01',calendar)
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'calendar.csv';file.write_text('date,holiday_name,holiday_type,source\n')
            with self.assertRaises(ValueError):hours.load_holiday_calendar(file)

    def test_resolver_hierarchy(self):
        row={'opening_hours_raw':'Mo-Fr 10:00-20:00; PH off'}
        result=hours.resolve_hours(row,'2026-11-26')
        self.assertTrue(result['is_public_holiday'])
        self.assertEqual(result['hours_evidence'],'explicit_osm_ph')
        self.assertEqual(result['opening_hours_effective'],{'format':'holiday','intervals':[]})
        result=hours.resolve_hours(row,'2026-11-25')
        self.assertEqual(result['hours_evidence'],'ordinary_osm')
        self.assertEqual(result['opening_hours_effective']['raw'],row['opening_hours_raw'])
        special=hours.resolve_hours({'opening_hours_raw':'Mo-Fr 10:00-20:00; PH 12:00-18:00'},'2026-11-26')
        self.assertEqual(special['opening_hours_effective']['intervals'],[['12:00','18:00']])
        observed=hours.resolve_hours({'opening_hours_raw':'Mo-Su 10:00-22:00'},'2026-11-26')
        self.assertEqual(observed['hours_evidence'],'ordinary_osm_holiday_unknown')
        self.assertEqual(observed['holiday_rule_status'],'UNKNOWN')
        default=hours.resolve_hours({'opening_hours_raw':None},'2026-11-26')
        self.assertEqual(default['hours_evidence'],'experimental_default')
        self.assertEqual(default['holiday_rule_status'],'ASSUMED')
        complex_raw='Mo-Fr,PH 12:00-18:00'
        self.assertEqual(hours.resolve_hours({'opening_hours_raw':complex_raw},'2026-11-26')['opening_hours_effective']['raw'],complex_raw)

    def test_frozen_rows_and_determinism(self):
        content=(osm.ROOT/'data/processed/restaurants.csv').read_text()
        rows=list(csv.DictReader(io.StringIO(content)))
        result=hours.add_hours_rows(rows)
        self.assertEqual(result,hours.add_hours_rows(result))
        self.assertEqual(len(result),670)
        for before,after in zip(rows,result):
            self.assertEqual([before[k] for k in osm.CORE],[after[k] for k in osm.CORE])
            self.assertEqual(before.get('opening_hours_raw'),after.get('opening_hours_raw'))
            self.assertEqual(before.get('opening_hours_kitchen_raw'),after.get('opening_hours_kitchen_raw'))
        buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=list(result[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(result)
        osm.assert_frozen(content,buffer.getvalue())


if __name__=='__main__':unittest.main()
