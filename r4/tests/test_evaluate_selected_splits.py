"""Keep evaluation on its named split while matrix evidence remains train-only."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from r4.evaluate_selected import evaluate_selected
from r4.safety import split_uids, train_uids


class SelectedEvaluationSplitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def save(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def prepare(self, split, *, selected=None, outcomes=None):
        selected = sorted(split_uids(split))[:2] if selected is None else selected
        self.save("r4_run_metadata.json", {
            "split": split, "language": "en", "selected_query_ids": selected,
            "evaluation_split_partition": "test" if split.endswith("_test") else "train"})
        for uid in selected:
            self.save(f"queries/{uid}/reference/query.json", {"uid": uid})
        self.save("r4_selection_and_costs.json", outcomes if outcomes is not None else [{
            "query_uid": uid, "selected_verification": {
                "translated_plan": {"itinerary": [{"day": 1, "activities": []}]}}
        } for uid in selected])
        return selected

    def test_explicit_selected_diagnostic_records_test_partition(self):
        selected = self.prepare("subset_test")
        scorer = Mock(return_value={"query_count": 2})
        evaluate_selected(self.root, scorer)
        references, plans, destination = scorer.call_args.args
        self.assertEqual(set(references), set(selected))
        self.assertEqual(set(plans), set(selected))
        population = json.loads((destination / "evaluation_population.json").read_text())
        self.assertEqual((population["split"], population["partition"]), ("subset_test", "test"))

    def test_training_evaluation_remains_supported(self):
        self.prepare("subset_train")
        scorer = Mock(return_value={"ok": True})
        self.assertEqual(evaluate_selected(self.root, scorer), {"ok": True})
        population = json.loads((self.root / "benchmark_eval/selected/evaluation_population.json").read_text())
        self.assertEqual(population["partition"], "train")
        with self.assertRaisesRegex(ValueError, "Matrix evidence must come from a training split"):
            train_uids("subset_test")

    def test_test_evaluation_rejects_training_query_ids(self):
        self.prepare("subset_test", selected=[sorted(train_uids())[0]])
        scorer = Mock()
        with self.assertRaisesRegex(ValueError, "unique query IDs from subset_test"):
            evaluate_selected(self.root, scorer)
        scorer.assert_not_called()
        self.assertFalse((self.root / "benchmark_eval").exists())

    def test_missing_plan_keeps_query_in_denominator_and_ignores_extra_references(self):
        selected = self.prepare("subset_test", outcomes=[])
        self.save("queries/extra/reference/query.json", {"uid": "unselected"})
        scorer = Mock()
        evaluate_selected(self.root, scorer)
        references, plans, _ = scorer.call_args.args
        self.assertEqual(set(references), set(selected))
        self.assertEqual(plans, dict.fromkeys(selected, {}))

    def test_missing_reference_is_rejected_before_writing_exports(self):
        selected = self.prepare("subset_test")
        (self.root / f"queries/{selected[0]}/reference/query.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing saved reference"):
            evaluate_selected(self.root, Mock())
        self.assertFalse((self.root / "benchmark_eval").exists())


if __name__ == "__main__":
    unittest.main()
