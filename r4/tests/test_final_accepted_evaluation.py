"""Use authoritative accepted checkpoints for the R3 and R4 benchmark CLI."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from chinatravel.evaluation.repair_comparison import _component, _save
from r4.safety import split_uids
from scripts.evaluate_repair_run import main as evaluate_run


class FinalAcceptedEvaluationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.uid = sorted(split_uids("subset_test"))[0]
        _save(self.root / "run_manifest.json", {
            "run_id": "test-r4", "query_uids": [self.uid], "repair_strategies_requested": ["R4"],
            "language": "en", "split_query_source": "subset_test"})
        self.metadata = {"split": "subset_test", "selected_query_ids": [self.uid],
                         "synthetic_runtime": False}
        _save(self.root / "r4_run_metadata.json", self.metadata)
        query = self.root / "queries" / _component(self.uid)
        _save(query / "reference/query.json", {"uid": self.uid, "hard_logic_py": ["result=True"]})
        self.accepted = {"itinerary": [{"day": 1, "activities": [{"position": "Accepted"}]}]}
        self.rejected = {"itinerary": [{"day": 1, "activities": [{"position": "Rejected"}]}]}
        self.checkpoint = query / "trials" / (_component("R4") + ".json")
        _save(self.checkpoint, {"query_uid": self.uid, "execution_status": "completed",
            "final_verification": {"translated_plan": self.accepted},
            "candidate_plan": self.rejected,
            "repair_history": [{"step": 2, "accepted": False,
                                "verification": {"translated_plan": self.rejected}}]})
        _save(self.root / "r4_selection_and_costs.json", [{"query_uid": self.uid,
            "selected_source": "initial", "selected_step": 0,
            "selected_verification": {"translated_plan": {"itinerary": []}}}])

    def scorer(self, references, plans, directory, **kwargs):
        _save(directory / "benchmark_summary.json", {"query_count": len(plans), "rate_scale": "percent"})
        return {"query_count": len(plans)}

    def test_cli_ignores_selected_initial_and_rejected_last_candidate(self):
        scorer = Mock(side_effect=self.scorer)
        with patch("eval_exp.evaluate_final_plans", scorer), \
             patch("r4.evaluate_selected.evaluate_selected") as selected:
            results = evaluate_run(["--run-dir", str(self.root)])
        selected.assert_not_called()
        references, plans, directory = scorer.call_args.args
        self.assertEqual(set(references), {self.uid})
        self.assertEqual(plans, {self.uid: self.accepted})
        self.assertEqual(directory, self.root / "benchmark_eval" / _component("R4"))
        population = json.loads((directory / "evaluation_population.json").read_text())
        self.assertEqual((population["outcome_policy"], population["partition"]), ("final_accepted", "test"))
        self.assertEqual(population["plan_source"], "final_verification.translated_plan")
        self.assertEqual(results["R4"]["outcome_policy"], "final_accepted")
        self.assertEqual(results["R4"]["split"], "subset_test")
        self.assertFalse((self.root / "benchmark_eval/selected").exists())

    def test_missing_final_verification_never_falls_back_to_other_candidates(self):
        _save(self.checkpoint, {"execution_status": "failed", "candidate_plan": self.rejected})
        scorer = Mock(side_effect=self.scorer)
        with patch("eval_exp.evaluate_final_plans", scorer):
            evaluate_run(["--run-dir", str(self.root)])
        self.assertEqual(scorer.call_args.args[1], {self.uid: {}})

    def test_r4_mock_runtime_is_still_excluded(self):
        _save(self.root / "r4_run_metadata.json", {**self.metadata, "synthetic_runtime": True})
        with patch("eval_exp.evaluate_final_plans") as scorer:
            with self.assertRaisesRegex(ValueError, "Synthetic smoke runs"):
                evaluate_run(["--run-dir", str(self.root)])
        scorer.assert_not_called()
        self.assertFalse((self.root / "benchmark_eval").exists())

    def test_r4_population_must_match_the_saved_evaluation_split(self):
        _save(self.root / "r4_run_metadata.json", {**self.metadata, "split": "subset_train"})
        with patch("eval_exp.evaluate_final_plans") as scorer:
            with self.assertRaisesRegex(ValueError, "named train/test split"):
                evaluate_run(["--run-dir", str(self.root)])
        scorer.assert_not_called()

    def test_optional_trial_exports_also_use_final_accepted_plans(self):
        scorer = Mock(side_effect=self.scorer)
        with patch("eval_exp.evaluate_final_plans", scorer), \
             patch("r4.evaluate_selected.evaluate_selected") as selected:
            evaluate_run(["--run-dir", str(self.root), "--include-trials"])
        selected.assert_not_called()
        self.assertEqual(scorer.call_count, 2)
        self.assertTrue(all(call.args[1] == {self.uid: self.accepted} for call in scorer.call_args_list))


if __name__ == "__main__":
    unittest.main()
