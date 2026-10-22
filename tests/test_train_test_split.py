import csv
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from chinatravel.evaluation.train_test_split import (
    build_split, validate_manifest, query_group, filter_attempts, select_queries,
)
from scripts.build_train_test_split import main as split_main
from scripts.build_regression_matrix import main as matrix_main, load_input
## Allow importing sibling test modules (e.g. test_regression_matrix) regardless
## of how the suite is launched (plain `unittest discover` doesn't add the tests
## dir to sys.path, unlike pytest).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_regression_matrix import record
from types import SimpleNamespace
import run_repair_comparison as runner


class SplitTests(unittest.TestCase):
    def records(self):
        return [{"uid": f"q{i}", "semantic_case_id": f"case{i // 2}"} for i in range(20)]

    def test_reproducible_seed_order_and_coverage(self):
        rows = self.records()
        manifest = build_split(rows)
        self.assertEqual(manifest, build_split(list(reversed(rows))))
        self.assertNotEqual(manifest["train"], build_split(rows, seed=99)["train"])
        self.assertEqual(set(manifest["train"]) | set(manifest["test"]), {r["uid"] for r in rows})
        self.assertFalse(set(manifest["train"]) & set(manifest["test"]))
        for item in manifest["groups"].values():
            self.assertTrue(set(item["query_uids"]) <= set(manifest[item["split"]]))
        self.assertEqual(len(manifest["train"]), 14)

    def test_explicit_priority_source_plan_and_uid_fallback(self):
        self.assertEqual(query_group({"uid": "q"}), ("q", "query_uid"))
        self.assertEqual(query_group({"uid": "q", "semantic_case_id": "s", "case_id": "c"}), ("s", "semantic_case_id"))
        for field in ("case_id", "base_case_id", "parent_case_id", "source_plan_uid"):
            self.assertEqual(query_group({"uid": "q", field: "parent"}), ("parent", field))
        rows = [{"uid": "a", "source_plan_uid": "p"}, {"uid": "b", "source_plan_uid": "p"}, {"uid": "c"}]
        manifest = build_split(rows)
        self.assertEqual(manifest["groups"]["p"]["query_uids"], ["a", "b"])
        self.assertIn("c", manifest["groups"])

    def test_invalid_duplicates_and_leakage_fail_loudly(self):
        with self.assertRaises(ValueError):
            build_split([{"uid": "a"}, {"uid": "a"}])
        with self.assertRaises(ValueError):
            build_split([{"uid": "a"}])
        for fraction in (0, 1, -1, float("nan")):
            with self.assertRaises(ValueError):
                build_split(self.records(), fraction)
        manifest = build_split(self.records())
        bad = deepcopy(manifest)
        bad["test"].append(bad["train"][0])
        with self.assertRaises(ValueError):
            validate_manifest(bad)
        bad = deepcopy(manifest)
        group = next(g for g, item in bad["groups"].items() if item["split"] == "train")
        uid = bad["groups"][group]["query_uids"][0]
        bad["train"].remove(uid)
        bad["test"].append(uid)
        with self.assertRaises(ValueError):
            validate_manifest(bad)

    def test_query_selection_and_attempt_training_boundary(self):
        rows = self.records()
        manifest = build_split(rows)
        queries = {r["uid"]: r for r in rows}
        self.assertEqual(set(select_queries(queries, manifest, "train")), set(manifest["train"]))
        self.assertEqual(set(select_queries(queries, manifest, "test")), set(manifest["test"]))
        attempts = [{"repair_attempt": {"query_uid": r["uid"]}} for r in rows]
        train = filter_attempts(attempts, manifest, "train")
        self.assertEqual({a["repair_attempt"]["query_uid"] for a in train}, set(manifest["train"]))
        with self.assertRaises(ValueError):
            filter_attempts([{"query_uid": None}], manifest, "train")
        with self.assertRaises(ValueError):
            select_queries({}, manifest, "test")
        changed = deepcopy(queries)
        changed[manifest["train"][0]]["semantic_case_id"] = "changed"
        with self.assertRaises(ValueError):
            select_queries(changed, manifest, "train")

    def test_cli_manifest_and_matrix_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "queries.json"
            source.write_text(json.dumps(self.records()))
            output = root / "split.json"
            split_main(["--input", str(source), "--output", str(output)])
            manifest = json.loads(output.read_text())
            # Filter precedes existing matrix computation; no formula changes.
            attempts = [{"run_id": "run", "repair_attempt": record(query_uid=uid).to_dict()}
                        for uid in (manifest["train"][0], manifest["test"][0])]
            with patch("scripts.build_regression_matrix.load_input", return_value=attempts), patch("scripts.build_regression_matrix.build_regression_matrix") as build:
                build.return_value = {"aggregate": [], "aggregate_by_scope": [], "contributions": [], "coverage": {}}
                matrix_main(["--input", str(source), "--output-dir", str(root / "matrix"),
                             "--split-manifest", str(output), "--partition", "train"])
                selected = build.call_args.args[0]
                self.assertEqual([r["repair_attempt"]["query_uid"] for r in selected], [manifest["train"][0]])
            trajectories = root / "attempts.jsonl"
            trajectories.write_text("".join(json.dumps(attempt) + "\n" for attempt in attempts))
            matrix_main(["--input", str(trajectories), "--output-dir", str(root / "real-matrix"),
                         "--split-manifest", str(output), "--partition", "train"])
            with (root / "real-matrix/matrix_contributions.csv").open() as stream:
                contributions = list(csv.DictReader(stream))
            self.assertEqual({row["query_uid"] for row in contributions}, {manifest["train"][0]})
            csv_path = root / "attempts.csv"
            with csv_path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=attempts[0]["repair_attempt"])
                writer.writeheader()
                writer.writerows({key: "" if value is None else value if isinstance(value, str) else json.dumps(value)
                                  for key, value in item["repair_attempt"].items()} for item in attempts)
            # Null strings use CSV blanks in real exports.
            self.assertEqual(load_input(csv_path)[0]["repair_attempt"]["query_uid"], manifest["train"][0])
            matrix_main(["--input", str(csv_path), "--output-dir", str(root / "csv-matrix"),
                         "--split-manifest", str(output), "--partition", "train"])
            self.assertEqual((root / "csv-matrix/regression_matrix_long.csv").read_text(),
                             (root / "real-matrix/regression_matrix_long.csv").read_text())
            coverage = json.loads((root / "matrix/matrix_coverage.json").read_text())
            self.assertEqual(coverage["split_selection"]["partition"], "train")


    def test_paired_cli_selects_saved_partition_and_records_manifest(self):
        rows = self.records()
        manifest = build_split(rows)
        queries = {row["uid"]: row for row in rows}
        model_module = SimpleNamespace(init_agent=lambda *args: None,
            init_llm=lambda *args: SimpleNamespace(default_request_args={}), resolve_llm_name=lambda value: "mock")
        world_module = SimpleNamespace(WorldEnv=lambda **kwargs: None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "split.json"
            path.write_text(json.dumps(manifest))
            for partition in ("train", "test"):
                with patch.dict("sys.modules", {"chinatravel.agent.load_model": model_module,
                                                "chinatravel.environment.world_env": world_module}), \
                     patch("chinatravel.data.load_datasets.load_query", return_value=(list(queries), queries)), \
                     patch.object(runner, "run_comparison", return_value="synthetic-output") as run:
                    runner.main(["--llm", "mock", "--split-manifest", str(path), "--partition", partition])
                    self.assertEqual(set(run.call_args.args[0]), set(manifest[partition]))
                    self.assertEqual(run.call_args.kwargs["config"]["partition"], partition)
                    self.assertIn("split_manifest_hash", run.call_args.kwargs["config"])
