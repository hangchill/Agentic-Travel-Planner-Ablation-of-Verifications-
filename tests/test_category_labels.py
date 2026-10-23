"""Category equivalence at DSL comparisons; no database or model required."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from chinatravel.symbol_verification.category_labels import normalize_category_label
from chinatravel.symbol_verification.dsl import execute_dsl_code
from chinatravel.symbol_verification.hard_constraint import evaluate_constraints_py
from chinatravel.agent.nesy_verifier.shared_verifier import check_personal_constraints


class CategoryLabelsTests(unittest.TestCase):
    def evaluate(self, code, observed):
        variables = {'restaurant_type': lambda *args: observed, 'plan': {},
                     'attraction_type': lambda *args: observed,
                     'accommodation_type': lambda *args: observed,
                     'activity_position': lambda *args: observed}
        diagnostics = []
        execute_dsl_code(code, variables, category_diagnostics=diagnostics)
        return variables['result'], diagnostics

    def test_known_equivalence_and_formatting(self):
        for label in ['川菜', 'Sichuan cuisine', 'Sichuan food', '  SICHUAN   CUISINE  ', 'Sichuan-cuisine']:
            self.assertEqual(normalize_category_label(label), 'Sichuan cuisine')
        self.assertNotEqual(normalize_category_label('川菜'), normalize_category_label('粤菜'))
        self.assertNotEqual(normalize_category_label('Unknown A'), normalize_category_label('Unknown B'))

    def test_both_directions_chinese_and_english(self):
        for literal in ['川菜', 'Sichuan cuisine', 'Sichuan food']:
            for observed in ['川菜', 'Sichuan cuisine', 'Sichuan food']:
                result, diagnostics = self.evaluate(f'result=restaurant_type(plan,"Beijing")=={literal!r}', observed)
                self.assertTrue(result)
                self.assertEqual(diagnostics[0]['raw_label'], observed)
                self.assertTrue(all(d['normalized_label'] == 'Sichuan cuisine' for d in diagnostics))

    def test_membership_and_collected_set_subset(self):
        for code in [
            'result=restaurant_type(plan,"B") in ["川菜"]',
            'result="川菜" in {restaurant_type(plan,"B")}',
            'types=set()\ntypes.add(restaurant_type(plan,"B"))\nresult={"川菜"}<=types',
            'types=set()\nfor i in [1,2]:\n  types.add(restaurant_type(plan,"B"))\nresult=types=={"川菜"}',
            't=restaurant_type(plan,"B")\nresult=t!="粤菜"',
            'types={restaurant_type(plan,"B")}\nresult=False\nfor cuisine in types:\n  if cuisine=="川菜": result=True',
        ]:
            self.assertTrue(self.evaluate(code, 'Sichuan cuisine')[0])

    def test_other_backed_categories(self):
        for func, literal, observed in [('attraction_type', '自然风光', 'natural scenery'),
                                        ('accommodation_type', '智能客控', 'Smart Room Control')]:
            self.assertTrue(self.evaluate(f'result={func}(plan,"B")=={literal!r}', observed)[0])

    def test_unknown_distinct_and_entities_untouched(self):
        for code, observed in [('result=restaurant_type(plan,"B")=="粤菜"', 'Sichuan cuisine'),
                               ('result=restaurant_type(plan,"B")=="Unknown B"', 'Unknown A'),
                               ('result=activity_position(plan)=="川菜"', 'Sichuan cuisine'),
                               ('result="cafe"=="coffee shop"', '')]:
            self.assertFalse(self.evaluate(code, observed)[0])

    def test_entity_value_is_not_normalized_against_category(self):
        self.assertTrue(self.evaluate('result=restaurant_type(plan,"B")==activity_position(plan)', '川菜')[0])
        variables = {'restaurant_type': lambda: 'Sichuan cuisine', 'activity_position': lambda: '川菜'}
        execute_dsl_code('result=restaurant_type()==activity_position()', variables)
        self.assertFalse(variables['result'])

    def test_shared_and_benchmark_paths_preserve_sources(self):
        code = 'result=restaurant_type(plan,"Beijing")=="川菜"'
        problem = {'hard_logic_py': [code]}; plan = {}; before = deepcopy(problem)
        diagnostics = []
        with patch.dict('chinatravel.symbol_verification.concept_func.func_dict', {'restaurant_type': lambda *args: 'Sichuan cuisine'}):
            self.assertEqual(check_personal_constraints(problem, plan, diagnostics), ([True], []))
            self.assertEqual(evaluate_constraints_py([code], plan), [True])
        self.assertEqual(problem, before)
        self.assertEqual(diagnostics[0]['constraint_index'], 1)

    def test_reused_entity_variable_is_conservatively_untouched(self):
        code='name=restaurant_type(plan,"B")\nname=activity_position(plan)\nresult=name=="川菜"'
        self.assertFalse(self.evaluate(code, 'Sichuan cuisine')[0])


    def test_comparison_short_circuit_preserved(self):
        calls = []
        variables = {'restaurant_type': lambda: '粤菜',
                     'later': lambda: calls.append(True)}
        execute_dsl_code('result="川菜"==restaurant_type()==later()', variables)
        self.assertFalse(variables['result'])
        self.assertEqual(calls, [])

    def test_transport_formatting_without_invented_translation(self):
        variables = {'innercity_transport_type': lambda: '  TAXI  '}
        execute_dsl_code('result=innercity_transport_type()=="taxi"', variables)
        self.assertTrue(variables['result'])
        self.assertNotEqual(normalize_category_label('出租车', 'transport'), 'taxi')
