"""Named-place constraints: Chinese names are translated to English for evaluation."""
import json
from pathlib import Path
import tempfile
import unittest

from chinatravel.evaluation import named_place_translation as npt

HAVE_DATABASES = (npt.ZH_DB / "attractions" / "suzhou").is_dir() and (npt.EN_DB / "attractions" / "suzhou").is_dir()

ATTRACTION_CODE = (
    "attraction_name_set=set()\nfor activity in allactivities(plan):\n"
    "    if activity_type(activity)=='attraction':\n"
    "        attraction_name_set.add(activity_position(activity))\n"
    "result=({'寒山寺'}<=attraction_name_set)"
)
BUDGET_CODE = (
    "total_cost=0 \nfor activity in allactivities(plan):\n"
    "    total_cost+=activity_cost(activity)\nresult=(total_cost<=6100)"
)


def fake_resolve(zh_name):
    return {"寒山寺": "Hanshan Temple"}.get(zh_name)


class ConstraintRewriteTests(unittest.TestCase):
    def test_named_place_literal_is_replaced(self):
        code, pairs, unresolved = npt.translate_named_place_constraint(ATTRACTION_CODE, fake_resolve)
        self.assertIn("result=({'Hanshan Temple'}<=attraction_name_set)", code)
        self.assertEqual(code.replace("'Hanshan Temple'", "'寒山寺'"), ATTRACTION_CODE)
        self.assertEqual(pairs, [("寒山寺", "Hanshan Temple")])
        self.assertEqual(unresolved, [])

    def test_other_constraints_stay_identical(self):
        type_code = "result=({'博物馆'}<=attraction_type_set)"
        for code in (BUDGET_CODE, type_code, "result=(day_count(plan)==2)"):
            self.assertEqual(npt.translate_named_place_constraint(code, fake_resolve), (code, [], []))

    def test_unknown_name_is_unchanged_and_reported(self):
        code = ATTRACTION_CODE.replace("寒山寺", "不存在的地方")
        new_code, pairs, unresolved = npt.translate_named_place_constraint(code, fake_resolve)
        self.assertEqual(new_code, code)
        self.assertEqual(pairs, [])
        self.assertEqual(unresolved, ["不存在的地方"])

    def test_chinese_run_is_not_touched(self):
        refs = {"q": {"uid": "q", "target_city": "Suzhou", "hard_logic_py": [ATTRACTION_CODE]}}
        self.assertEqual(npt.translate_references(refs, "zh"), (refs, []))

    def test_query_without_named_place_is_not_copied(self):
        refs = {"q": {"uid": "q", "hard_logic_py": [BUDGET_CODE]}}
        translated, log = npt.translate_references(refs, "en")
        self.assertIs(translated["q"], refs["q"])
        self.assertEqual(log, [])


@unittest.skipUnless(HAVE_DATABASES, "sandbox databases not installed")
class DatabaseMappingTests(unittest.TestCase):
    def test_city_maps(self):
        self.assertEqual(npt.build_name_map("suzhou")["寒山寺"], "Hanshan Temple")
        self.assertEqual(npt.build_name_map("wuhan")["黄鹤楼"], "Yellow Crane Tower")
        self.assertEqual(npt.build_name_map("chongqing")["蓝苑人家渝菜坊(北滨路店)"],
                         "Blue Garden Family Sichuan Cuisine Restaurant (North Riverside Road Branch)")
        self.assertEqual(npt.build_name_map("nanjing")["花筑·僖堂民宿(南京夫子庙老门东店)"],
                         "Floral Hotel Xitang B&B (Nanjing Confucius Temple Laomendong Branch)")

    def test_translate_references_keeps_original(self):
        original = [BUDGET_CODE, ATTRACTION_CODE]
        refs = {"q": {"uid": "q", "target_city": "Suzhou", "hard_logic_py": list(original)}}
        translated, log = npt.translate_references(refs, "en")
        self.assertEqual(refs["q"]["hard_logic_py"], original)  # input not changed
        self.assertEqual(translated["q"]["hard_logic_py_original"], original)
        self.assertEqual(translated["q"]["hard_logic_py"][0], BUDGET_CODE)
        self.assertIn("'Hanshan Temple'", translated["q"]["hard_logic_py"][1])
        self.assertEqual(log, [dict(uid="q", constraint_index=1, zh="寒山寺", en="Hanshan Temple", resolved=True)])

    def test_benchmark_checker_passes_translated_constraint(self):
        from chinatravel.symbol_verification.concept_func import set_concept_func_lang
        from chinatravel.symbol_verification.hard_constraint import evaluate_constraints_py
        set_concept_func_lang("en")
        plan = {"people_number": 1, "start_city": "Shanghai", "target_city": "Suzhou", "itinerary": [
            {"day": 1, "activities": [{"type": "attraction", "position": "Hanshan Temple",
                                       "start_time": "09:00", "end_time": "10:00", "price": 0,
                                       "cost": 0, "tickets": 1, "transports": []}]}]}
        refs = {"q": {"uid": "q", "target_city": "Suzhou", "hard_logic_py": [ATTRACTION_CODE]}}
        translated, _ = npt.translate_references(refs, "en")
        self.assertEqual(evaluate_constraints_py(translated["q"]["hard_logic_py"], plan), [True])
        self.assertEqual(evaluate_constraints_py([ATTRACTION_CODE], plan), [False])

    def test_evaluate_repair_run_scores_translated_references(self):
        from chinatravel.evaluation.export_final_plans import evaluate_repair_run
        from chinatravel.evaluation.repair_comparison import _component, _save
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _save(root / "run_manifest.json", dict(run_id="r", query_uids=["q"],
                  repair_strategies_requested=["R0"], language="en"))
            problem = dict(uid="q", target_city="Suzhou", hard_logic_py=[ATTRACTION_CODE])
            query = root / "queries" / _component("q")
            _save(query / "initial_state.json", {"state": {"problem": problem}})
            _save(query / (_component("R0") + ".json"), dict(
                execution_status="completed", final_verification={"translated_plan": {"itinerary": []}}))
            seen = []
            evaluate_repair_run(root, evaluator=lambda refs, plans, directory, **kw: seen.append(refs) or {})
            self.assertIn("'Hanshan Temple'", seen[0]["q"]["hard_logic_py"][0])
            output = root / "benchmark_eval" / _component("R0")
            population = json.loads((output / "evaluation_population.json").read_text(encoding="utf-8"))
            self.assertEqual(population["queries"]["q"]["hard_logic_py_original"], [ATTRACTION_CODE])
            log = json.loads((output / "named_place_translations.json").read_text(encoding="utf-8"))
            self.assertEqual([e["en"] for e in log], ["Hanshan Temple"])


if __name__ == "__main__":
    unittest.main()
