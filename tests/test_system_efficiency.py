"""System counters exercise dispatch/API boundaries without DB or network."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import tempfile

from chinatravel.agent.system_usage import (
    system_usage_scope, system_delta, tool_api, verification_execution,
)
from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
from chinatravel.agent.nesy_verifier.repair_strategies.base import RepairResult
from chinatravel.evaluation.repair_metrics import summarize_repair_history
from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from chinatravel.evaluation.repair_comparison import run_comparison
from chinatravel.agent.nesy_verifier.initial_state import InitialRepairState

ROOT = Path(__file__).resolve().parents[1]
PROBLEM = dict(uid="q", people_number=1, start_city="A", target_city="B", hard_logic_py=["result=True"])
FAIL = dict(personal_constraints=[False], passed=False)
PASS = dict(personal_constraints=[True], passed=True)


def actual_keys(module):
    """Load the real decorated API method, bypassing database-heavy imports."""
    tree = ast.parse((ROOT / f"chinatravel/environment/tools/{module}/apis.py").read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "keys")
    namespace = {"tool_api": tool_api}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "actual-tool-api", "exec"), namespace)
    return namespace["keys"]


class SystemEfficiencyTests(unittest.TestCase):
    def test_actual_api_repeat_distinct_types_failures_and_wrapper(self):
        restaurants = actual_keys("restaurants")
        attractions = actual_keys("attractions")
        instance = SimpleNamespace(key_type_tuple_list_map={"A": ["name"]})
        tree = ast.parse((ROOT / "chinatravel/environment/world_env.py").read_text())
        world = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "WorldEnv")
        methods = [node for node in world.body if isinstance(node, ast.FunctionDef) and node.name in ("_execute_command", "_parse_command_argument")]
        namespace = {"ast": ast}
        exec(compile(ast.Module(body=methods, type_ignores=[]), "actual-dispatch", "exec"), namespace)
        environment = SimpleNamespace()
        environment._parse_command_argument = lambda node: namespace["_parse_command_argument"](environment, node)
        def dispatcher(api, city):
            return namespace["_execute_command"](environment, f"call({city!r})", {"call": lambda value: api(instance, value)})
        with system_usage_scope() as usage:
            self.assertEqual(usage.snapshot()["tool_call_count"], 0)
            dispatcher(restaurants, "A")
            dispatcher(restaurants, "A")
            dispatcher(attractions, "A")
            self.assertEqual(usage.snapshot()["tool_call_count"], 3)
            self.assertEqual(usage.snapshot()["tool_call_counts_by_type"],
                             {"restaurants_keys": 2, "attractions_keys": 1})
            with self.assertRaises(KeyError):
                dispatcher(restaurants, "missing")
            dispatcher(restaurants, "A")  # actual retry
            self.assertEqual(usage.snapshot()["tool_call_count"], 5)
            self.assertEqual(usage.snapshot()["failed_tool_call_count"], 1)
            self.assertEqual(usage.snapshot()["successful_tool_call_count"], 4)
        with system_usage_scope() as usage:
            self.assertEqual(usage.snapshot()["tool_call_count"], 0)

    def test_rejected_verification_counts_and_roundtrip(self):
        strategy = SimpleNamespace(
            repair=lambda **kw: RepairResult([], {"strategy": "R0"}),
            accept=lambda *args: False)
        # One initial execution and two rejected candidates. Wrapping a verifier
        # at both public entry points must still increment once per execution.
        verifier = verification_execution(lambda *args, **kw: FAIL)
        with patch.object(loop, "verify_plan", verifier):
            outcome = loop.run_repair_loop(PROBLEM, [], strategy, {}, SimpleNamespace(), None, max_steps=2)
        records = [entry["repair_attempt"] for entry in outcome["history"][1:]]
        self.assertEqual([r["verification_count"] for r in records], [1, 1])
        summary = summarize_repair_history(outcome["history"])
        self.assertEqual(summary["initial_verification_count"], 1)
        self.assertEqual(summary["repair_verification_iterations"], 2)
        self.assertEqual(summary["verification_count_total"], 3)
        self.assertEqual(summary["rejected_attempts"], 2)
        self.assertEqual(summary["tool_call_count"], 0)
        self.assertGreaterEqual(outcome["history"][0]["pipeline_system_metrics"]["total_execution_time_s"], 0)
        self.assertEqual(RepairAttemptRecord.from_dict(json.loads(json.dumps(records[0]))).to_dict(), records[0])
        old = {key: value for key, value in records[0].items() if key not in (
            "tool_call_count", "tool_call_counts_by_type", "successful_tool_call_count", "failed_tool_call_count", "verification_count")}
        self.assertIsNone(RepairAttemptRecord.from_dict(old).tool_call_count)

    def test_verification_is_not_attempt_count_and_tools_in_verifier_count(self):
        @tool_api("goto")
        def route():
            return []
        @verification_execution
        def verifier(*args, **kwargs):
            route()
            return FAIL
        def repair(**kw):
            verifier()  # strategy's extra explicit shared verification
            return RepairResult([], {"strategy": "R0"})
        strategy = SimpleNamespace(repair=repair, accept=lambda *args: False)
        with patch.object(loop, "verify_plan", verifier):
            outcome = loop.run_repair_loop(PROBLEM, [], strategy, {}, SimpleNamespace(), None,
                                           max_steps=1, initial_verification=FAIL)
        record = outcome["history"][1]["repair_attempt"]
        self.assertEqual(record["verification_count"], 2)
        self.assertEqual(record["tool_call_count"], 2)
        self.assertEqual(record["tool_call_counts_by_type"], {"goto": 2})
        self.assertEqual(outcome["history"][0]["system_metrics"]["verification_count"], 0)

    def test_failure_before_verification_does_not_invent_execution(self):
        def fail(**kwargs):
            raise RuntimeError("generation failed")
        strategy = SimpleNamespace(repair=fail)
        saved = []
        with self.assertRaises(RuntimeError):
            loop.run_repair_loop(PROBLEM, [], strategy, {}, SimpleNamespace(), None,
                                 initial_verification=FAIL, history_callback=saved.append)
        self.assertEqual(saved[0][1]["repair_attempt"]["verification_count"], 0)

    def test_paired_timing_initial_separate_failed_and_rejected_work_persist(self):
        clock = [0.0]
        @tool_api("restaurants_select")
        def lookup():
            clock[0] += 2
        @verification_execution
        def verify(*args, **kwargs):
            clock[0] += 3
            return FAIL
        def prepare(problem):
            clock[0] += 100  # shared initial generation only
            lookup()
            verification = verify()
            return InitialRepairState("q", problem, [], {}, verification,
                                      generation_metadata={"initial_generation_tool_calls": 1})
        def repair(**kwargs):
            lookup()
            lookup()  # retry/extra actual work
            return RepairResult([], {"strategy": "R0"})
        strategy = lambda: SimpleNamespace(repair=repair, accept=lambda *args: False)
        def fail(**kwargs):
            lookup()
            raise RuntimeError("tool work consumed before failure")
        failing_strategy = lambda: SimpleNamespace(repair=fail)
        config = {"repair_strategies": ["R0", "R1", "failed"], "max_steps": 1}
        with tempfile.TemporaryDirectory() as directory:
            with patch("chinatravel.evaluation.repair_comparison.perf_counter", side_effect=lambda: clock[0]), patch.object(loop, "verify_plan", verify):
                root = run_comparison({"q": PROBLEM}, run_id="timing", output_root=directory,
                        config=config, prepare_initial_state=prepare,
                        runtime_factory=lambda *args: (SimpleNamespace(), None),
                        strategy_factories={"R0": strategy, "R1": strategy, "failed": failing_strategy})
            pairs = [json.loads(p.read_text()) for p in (root / "queries").glob("*/*.json") if p.name != "initial_state.json"]
            self.assertEqual(len(pairs), 3)
            failed = next(pair for pair in pairs if pair["repair_strategy"] == "failed")
            self.assertEqual(failed["execution_status"], "failed")
            self.assertEqual(failed["summary_metrics"]["total_execution_time_s"], 2)
            self.assertEqual(failed["summary_metrics"]["tool_call_count"], 1)
            self.assertEqual(failed["summary_metrics"]["repair_verification_count"], 0)
            self.assertEqual(failed["repair_attempts"][0]["tool_call_count"], 1)
            for pair in (pair for pair in pairs if pair["repair_strategy"] != "failed"):
                summary = pair["summary_metrics"]
                self.assertEqual(summary["total_execution_time_s"], 7)
                self.assertEqual(summary["shared_initialization_time_s"], 105)
                self.assertEqual(summary["tool_call_count"], 2)
                self.assertEqual(summary["repair_verification_count"], 1)
                self.assertEqual(summary["initial_verification_count"], 1)
                self.assertEqual(summary["verification_count_total"], 2)
                self.assertIsNone(summary["model_call_count"])
                self.assertIsNone(summary["total_tokens"])
            self.assertEqual(len((root / "attempts.jsonl").read_text().splitlines()), 3)
            self.assertIn('restaurants_select', (root / "summaries.csv").read_text())

if __name__ == "__main__":
    unittest.main()
