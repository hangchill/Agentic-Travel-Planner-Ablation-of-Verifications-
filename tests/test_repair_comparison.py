"""Paired runner tests using synthetic runtimes, with no DB or live models."""

import ast
from copy import deepcopy
import csv
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from chinatravel.agent.nesy_verifier.initial_state import InitialRepairState
from chinatravel.agent.nesy_verifier.repair_strategies import STRATEGY_FACTORIES, create_repair_strategy
from chinatravel.agent.nesy_verifier.repair_strategies.base import BaseRepairStrategy, RepairResult
from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
from chinatravel.evaluation import repair_comparison as comparison
from scripts.build_regression_matrix import load_input
from chinatravel.evaluation.regression_matrix import build_regression_matrix


def query(uid="q1"):
    return {"uid": uid, "people_number": 1, "start_city": "A", "target_city": "B",
            "nature_language": "query " + uid, "hard_logic_py": ["result=day_count(plan)==2"]}


def state(problem):
    plan = [{"day": 1, "activities": [{"position": problem["uid"]}]}]
    verification = {"personal_constraints": [False], "passed": False,
                    "translated_plan": {"itinerary": deepcopy(plan)}, "error_info": ["failure"]}
    return InitialRepairState(problem["uid"], deepcopy(problem), plan,
                              {"nested": {"value": [1]}}, verification,
                              {"lang": "zh"}, {"input_tokens": 10})


class Repair(BaseRepairStrategy):
    def __init__(self, name, observed, fail=False):
        self.name, self.observed, self.fail = name, observed, fail

    def repair(self, problem, raw_plan, verification_results, context, llm):
        self.observed.append((self.name, deepcopy(raw_plan), deepcopy(context), deepcopy(problem)))
        context["nested"]["value"].append(99)
        problem["nature_language"] = "mutated"
        raw_plan[0]["activities"][0]["position"] = self.name
        if self.fail:
            raise RuntimeError("synthetic failure")
        return RepairResult(raw_plan, {"strategy": self.name, "target_constraint_indices": [1]})


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.observed = []
        self.prepare = Mock(side_effect=state)
        self.runtime = Mock(side_effect=lambda snapshot, name: (SimpleNamespace(input_token_count=0, output_token_count=0), None))
        self.factories = {name: (lambda name=name: Repair(name, self.observed)) for name in ("R0", "R1")}
        self.config = {"repair_strategies": ["R0", "R1"], "max_steps": 1,
                       "model_identifier": "mock", "sampling_settings": {}, "seed": None,
                       "oracle_translation": True, "language": "zh", "split_query_source": "synthetic"}

    def run_comparison(self, **kwargs):
        options = dict(queries={"q1": query()}, run_id="run-a", output_root=self.output,
                       config=self.config, prepare_initial_state=self.prepare,
                       runtime_factory=self.runtime, strategy_factories=self.factories)
        options.update(kwargs)
        with patch.object(loop, "verify_plan", side_effect=lambda problem, plan, **kw: {
            "personal_constraints": [True], "passed": True,
            "translated_plan": deepcopy(plan), "error_info": [],
        }):
            return comparison.run_comparison(**options)

    def pairs(self, root):
        return [json.loads(path.read_text()) for path in (root / "queries").glob("*/*.json")
                if path.name not in ("initial_state.json", "initial_failure.json")]

    def test_generate_once_identical_plans_context_and_hashes(self):
        root = self.run_comparison()
        self.assertEqual(self.prepare.call_count, 1)
        self.assertEqual(self.runtime.call_count, 2)
        self.assertEqual(self.observed[0][1:], self.observed[1][1:])
        pairs = self.pairs(root)
        self.assertEqual(len({pair["initial_plan_hash"] for pair in pairs}), 1)
        self.assertTrue(all(pair["execution_status"] == "completed" for pair in pairs))
        self.assertTrue(all(pair["final_verification"]["passed"] for pair in pairs))
        self.assertTrue(all(pair["stop_reason"] == "verification_passed" for pair in pairs))
        manifest = json.loads((root / "run_manifest.json").read_text())
        self.assertEqual(manifest["repair_strategies_available"], ["R0", "R1"])
        self.assertIn("timestamp", manifest)

    def test_different_queries_and_run_ids_do_not_collide(self):
        root = self.run_comparison(queries={"q1": query(), "q2": query("q2")})
        self.assertEqual(self.prepare.call_count, 2)
        pairs = self.pairs(root)
        self.assertEqual(len({pair["initial_plan_hash"] for pair in pairs}), 2)
        other = self.run_comparison(run_id="run-b")
        self.assertNotEqual(root, other)
        self.assertTrue(root.exists() and other.exists())

    def test_unavailable_fails_or_is_explicitly_skipped(self):
        self.config["repair_strategies"] = ["R0", "R3"]
        with self.assertRaisesRegex(ValueError, "Unavailable"):
            self.run_comparison()
        self.prepare.assert_not_called()
        root = self.run_comparison(skip_unavailable=True)
        skipped = next(pair for pair in self.pairs(root) if pair["repair_strategy"] == "R3")
        self.assertEqual(skipped["execution_status"], "skipped")
        self.assertEqual(len(self.observed), 1)

    def test_strategy_failure_does_not_erase_or_stop_other_pairs(self):
        self.factories["R0"] = lambda: Repair("R0", self.observed, fail=True)
        root = self.run_comparison()
        pairs = {pair["repair_strategy"]: pair for pair in self.pairs(root)}
        self.assertEqual(pairs["R0"]["execution_status"], "failed")
        self.assertIn("synthetic failure", pairs["R0"]["exception"])
        self.assertEqual(pairs["R1"]["execution_status"], "completed")
        self.assertEqual(pairs["R0"]["initial_plan_hash"], pairs["R1"]["initial_plan_hash"])

    def test_flat_attempt_stream_is_directly_matrix_consumable(self):
        root = self.run_comparison()
        rows = [json.loads(line) for line in (root / "attempts.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["repair_strategy"] for row in rows}, {"R0", "R1"})
        self.assertTrue(all(row["run_id"] == "run-a" and row["query_uid"] == "q1" for row in rows))
        analysis = build_regression_matrix(load_input(root / "attempts.jsonl"))
        self.assertEqual(analysis["coverage"]["total_repair_attempts"], 2)

    def test_summary_calls_central_metrics_even_with_zero_attempts(self):
        self.config["max_steps"] = 0
        with patch.object(comparison, "summarize_repair_history", wraps=comparison.summarize_repair_history) as summarize:
            root = self.run_comparison()
        self.assertGreaterEqual(summarize.call_count, 2)
        with (root / "summaries.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["attempts"] == "0" and row["execution_status"] == "completed" for row in rows))

    def test_resume_reuses_initial_and_does_not_duplicate_attempts(self):
        root = self.run_comparison()
        initial_stream = (root / "attempts.jsonl").read_text()
        self.run_comparison(resume=True)
        self.assertEqual(self.prepare.call_count, 1)
        self.assertEqual(len(self.observed), 2)
        self.assertEqual((root / "attempts.jsonl").read_text(), initial_stream)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_comparison()

    def test_resume_rejects_changed_model_query_and_sampling(self):
        self.run_comparison()
        for update in ({"model_identifier": "other"}, {"sampling_settings": {"temperature": 0.5}}):
            with self.subTest(update=update), self.assertRaisesRegex(ValueError, "mismatch"):
                self.run_comparison(resume=True, config={**self.config, **update})
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.run_comparison(resume=True, queries={"q1": {**query(), "nature_language": "changed"}})

    def test_retry_failed_replaces_pair_instead_of_appending(self):
        self.factories["R0"] = lambda: Repair("R0", self.observed, fail=True)
        root = self.run_comparison()
        self.factories["R0"] = lambda: Repair("R0", self.observed)
        self.run_comparison(resume=True, retry_failed=True)
        self.assertEqual(len((root / "attempts.jsonl").read_text().splitlines()), 2)
        self.assertTrue(all(pair["execution_status"] == "completed" for pair in self.pairs(root)))

    def test_interrupted_pair_restarts_and_rebuilds_stale_indexes(self):
        root = self.run_comparison()
        pair_path = next(path for path in (root / "queries").glob("*/*.json")
                         if path.name != "initial_state.json")
        payload = json.loads(pair_path.read_text())
        payload["execution_status"] = "running"
        pair_path.write_text(json.dumps(payload))
        (root / "attempts.jsonl").write_text("stale index")
        self.run_comparison(resume=True)
        self.assertEqual(self.prepare.call_count, 1)
        self.assertEqual(len(self.observed), 3)
        rows = [json.loads(line) for line in (root / "attempts.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({(row["matrix_run_id"], row["query_uid"], row["step"]) for row in rows}), 2)

    def test_resume_rebuilds_old_attempts_in_canonical_format(self):
        root = self.run_comparison()
        path = next(path for path in (root / "queries").glob("*/*.json") if path.name != "initial_state.json")
        old = json.loads(path.read_text())
        attempt = old["repair_attempts"][0]
        attempt.pop("editable_scope")
        attempt.pop("target_provenance")
        attempt["repair_metadata"]["scope"] = "whole_plan"
        attempt["repair_metadata"]["target_provenance"] = "legacy"
        path.write_text(json.dumps(old))
        self.run_comparison(resume=True)
        rows = [json.loads(line) for line in (root / "attempts.jsonl").read_text().splitlines()]
        migrated = next(row for row in rows if row["repair_strategy"] == old["repair_strategy"])
        self.assertEqual(migrated["editable_scope"], "plan")
        self.assertEqual(migrated["target_provenance"], "legacy")
        self.assertNotIn("scope", migrated["repair_metadata"])
        self.assertNotIn("target_provenance", migrated["repair_metadata"])
        self.assertEqual(self.prepare.call_count, 1)

    def test_initial_snapshot_tampering_is_detected(self):
        root = self.run_comparison()
        path = next((root / "queries").glob("*/initial_state.json"))
        payload = json.loads(path.read_text())
        payload["state"]["repair_context"]["extra"] = "tampered"
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "modified"):
            self.run_comparison(resume=True)

    def test_missing_initial_state_cannot_be_regenerated_over_saved_pairs(self):
        root = self.run_comparison()
        next((root / "queries").glob("*/initial_state.json")).unlink()
        with self.assertRaisesRegex(ValueError, "Cannot regenerate"):
            self.run_comparison(resume=True)
        self.assertEqual(self.prepare.call_count, 1)

    def test_completed_attempts_survive_later_exception(self):
        calls = []

        class TwoStep(Repair):
            def repair(self, **kwargs):
                calls.append(1)
                if len(calls) == 2:
                    raise RuntimeError("second proposal failed")
                return super().repair(**kwargs)

        self.factories = {"R0": lambda: TwoStep("R0", self.observed)}
        self.config.update(repair_strategies=["R0"], max_steps=2)
        with patch.object(loop, "verify_plan", return_value={"personal_constraints": [False], "passed": False}):
            root = comparison.run_comparison(
                {"q1": query()}, run_id="run-a", output_root=self.output, config=self.config,
                prepare_initial_state=self.prepare, runtime_factory=self.runtime, strategy_factories=self.factories)
        pair = self.pairs(root)[0]
        self.assertEqual(pair["execution_status"], "failed")
        self.assertEqual(len(pair["repair_attempts"]), 1)
        self.assertEqual(pair["summary_metrics"]["attempts"], 1)
        self.assertEqual(len((root / "attempts.jsonl").read_text().splitlines()), 1)


class ExtractionCompatibilityTests(unittest.TestCase):
    """Execute the actual extracted methods with injected offline collaborators."""

    def methods(self, **namespace):
        path = Path(__file__).resolve().parents[1] / "chinatravel/agent/nesy_verifier/llm_modulo.py"
        tree = ast.parse(path.read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "LLMModuloAgent")
        methods = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                   and node.name in ("solve", "prepare_initial_repair_state")]
        module = ast.Module(body=methods, type_ignores=[])
        scope = dict(deepcopy=deepcopy, json=json, os=os, time=time, create_repair_strategy=create_repair_strategy,
                     **namespace)
        exec(compile(ast.fix_missing_locations(module), str(path), "exec"), scope)
        return scope

    def test_prepare_calls_generation_and_verification_once(self):
        scope = self.methods()
        snapshot = state(query())
        agent = SimpleNamespace(_generate_initial_plan=Mock(return_value=snapshot), translate_innercity_transport=Mock())
        with patch.object(loop, "verify_plan", return_value=snapshot.initial_verification) as verify:
            result = scope["prepare_initial_repair_state"](agent, query())
        agent._generate_initial_plan.assert_called_once()
        verify.assert_called_once()
        self.assertEqual(result.raw_initial_plan, snapshot.raw_initial_plan)

    def test_normal_r0_solve_preserves_outputs_and_verification_path(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = state(query())
            snapshot.generation_metadata["raw_response"] = "[]"
            snapshot.repair_context = {key: "same-context" for key in (
                "go_train_info", "go_flight_info", "back_train_info", "back_flight_info",
                "attraction_info", "restaurant_info", "accommodation_info", "innercity_transport_info")}
            verification = {"translated_plan": {"itinerary": []}, "personal_constraints": [True], "error_info": [], "passed": True}
            loop_call = Mock(return_value={"verification": verification, "history": []})
            scope = self.methods(run_repair_loop=loop_call)
            agent = SimpleNamespace(_generate_initial_plan=Mock(return_value=snapshot),
                                    repair_strategy_name="R0", backbone_llm=SimpleNamespace(
                                        input_token_count=10, output_token_count=2, input_token_maxx=10),
                                    translate_innercity_transport=Mock(), max_steps=2, llm_inference_time=1,
                                    start_clock=time.time(), information_collection_time=0.5, log_dir=directory)
            with patch.dict(STRATEGY_FACTORIES, {"R0": lambda: object()}):
                produced, plan = scope["solve"](agent, query(), "q1", True)
            self.assertTrue(produced)
            self.assertEqual(plan["personal_constraints"], [True])
            self.assertEqual(plan["input_token_count"], 10)
            agent._generate_initial_plan.assert_called_once()
            self.assertNotIn("initial_verification", loop_call.call_args.kwargs)
            self.assertEqual(loop_call.call_args.kwargs["raw_plan"], snapshot.raw_initial_plan)


if __name__ == "__main__":
    unittest.main()
