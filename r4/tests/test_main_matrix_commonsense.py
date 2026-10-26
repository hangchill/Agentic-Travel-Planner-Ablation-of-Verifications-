"""Check missing evidence and accepted-history semantics for the tenth column."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from chinatravel.evaluation.constraint_families import CONSTRAINT_FAMILIES
from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from r4.build_main_matrix import SOURCE_FAMILIES, STRATEGIES, build_main_matrix
from r4.commonsense_evidence import COMMONSENSE_FAMILY
from r4.safety import train_uids, validate_final_matrix


class CommonsenseMatrixTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.uid = sorted(train_uids())[0]

    def source(self, label, *, histories=True, unknown_after=False):
        run = self.root / label
        matrix = run / "regression_matrix"
        matrix.mkdir(parents=True)
        for prefix in ("candidate", "accepted"):
            for kind in ("count", "support", "rate"):
                with (matrix / f"{prefix}_regression_{kind}.csv").open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=["source_family", *CONSTRAINT_FAMILIES])
                    writer.writeheader()
                    for source in SOURCE_FAMILIES:
                        writer.writerow({"source_family": source, **{
                            dest: "" if kind == "rate" else 0 for dest in CONSTRAINT_FAMILIES}})
        # Step 1 is rejected. Step 2 must use the original accepted PASS state.
        reports = [
            {"personal_constraints": [False], "commonsense_errors": []},
            {"personal_constraints": [False], "commonsense_errors": ["new error"]},
            {"personal_constraints": [False], "commonsense_errors": []},
            {"personal_constraints": [False], "commonsense_errors": ["new error"]},
        ]
        if unknown_after:
            reports[3]["verifier_errors"] = ["check did not finish"]
        entries = [{"step": 0, "accepted": True, "verification": reports[0]}]
        for step in range(1, 4):
            accepted = step != 1
            record = RepairAttemptRecord(
                step=step, repair_strategy=label, target_constraint_indices=[1], target_constraint_labels=[],
                accepted=accepted, before_personal_constraints=[False], after_personal_constraints=[False],
                fixed=[], newly_violated=[], still_failed=[1], still_passed=[], unknown=[],
                candidate_plan=[], accepted_plan_after=[], repair_metadata={}, repair_phase="personal",
                query_uid=self.uid, constraint_descriptors=[{
                    "constraint_index": 1, "hard_logic_py": "result=(room_count(plan)==1)"}],
                changed_slot_count=1, total_comparable_slots=1, changed_slot_rate=1.0)
            entries.append({"step": step, "accepted": accepted, "verification": reports[step],
                            "repair_attempt": record.to_dict()})
        with (matrix / "matrix_contributions.csv").open("w", newline="") as stream:
            fields = ["run_id", "query_uid", "step", "repair_strategy", "source_family",
                      "destination_family", "perspective", "eligible"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for step in range(1, 4):
                for perspective in ("candidate", "accepted_trajectory"):
                    writer.writerow(dict(run_id=label, query_uid=self.uid, step=step, repair_strategy=label,
                        source_family="accommodation", destination_family="monetary_budget",
                        perspective=perspective, eligible=False))
        if histories:
            (run / "run_manifest.json").write_text(json.dumps({
                "split_query_source": "subset_train", "query_uids": [self.uid]}))
            folder = run / "queries" / self.uid
            folder.mkdir(parents=True)
            (folder / f"{label}-fixture.json").write_text(json.dumps({
                "matrix_run_id": label, "query_uid": self.uid, "repair_strategy": label,
                "initial_verification": reports[0], "repair_history": entries}))
        return run

    @staticmethod
    def cell(rows):
        return next(row for row in rows if row["source_family"] == "accommodation"
                    and row["destination_family"] == COMMONSENSE_FAMILY)

    def test_partial_history_pools_counts_and_deduplicates_query_support(self):
        sources = [self.source(label, histories=label != "R1") for label in STRATEGIES]
        output = self.root / "pooled/main_matrix.csv"
        rows, manifest = build_main_matrix(sources, output)
        self.assertEqual(len(rows), 100)
        cell = self.cell(rows)
        self.assertEqual((cell["regression_count"], cell["support_count"], cell["support_query_count"]), (6, 9, 1))
        self.assertAlmostEqual(float(cell["regression_probability"]), 2 / 3)
        self.assertEqual(cell["evidence_status"], "observed_partial")
        self.assertIsNone(cell["R1_support_count"])
        self.assertIsNone(cell["R1_regression_count"])
        self.assertEqual(manifest["commonsense_destination_unavailable_strategies"], ["R1"])
        with output.with_name(manifest["probability_pivot"]["file"]).open() as stream:
            grid = list(csv.DictReader(stream))
        self.assertEqual((len(grid), len(grid[0]) - 1), (10, 10))
        self.assertEqual(grid[0][COMMONSENSE_FAMILY], "unavailable")
        validate_final_matrix(output, train_uids())
        history = sources[0] / "queries" / self.uid / "R0-fixture.json"
        history.write_text(history.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "history provenance changed"):
            validate_final_matrix(output, train_uids())

    def test_rejections_do_not_regress_accepted_trajectory(self):
        source = self.source("R0")
        rows, _ = build_main_matrix([source], self.root / "accepted/main_matrix.csv", perspective="accepted")
        self.assertEqual((self.cell(rows)["regression_count"], self.cell(rows)["support_count"]), (1, 3))

    def test_incomplete_verification_is_excluded(self):
        source = self.source("R0", unknown_after=True)
        rows, manifest = build_main_matrix([source], self.root / "unknown/main_matrix.csv")
        self.assertEqual((self.cell(rows)["regression_count"], self.cell(rows)["support_count"]), (1, 2))
        audit = manifest["input_matrices"][0]["commonsense_destination_evidence"]
        self.assertEqual(audit["excluded_attempts"]["commonsense_unknown_after"], 1)

    def test_all_missing_histories_produce_blank_counts_not_zero(self):
        source = self.source("R0", histories=False)
        output = self.root / "missing/main_matrix.csv"
        rows, _ = build_main_matrix([source], output)
        self.assertEqual(self.cell(rows)["evidence_status"], "unavailable")
        for name in ("regression_count", "support_count", "support_query_count"):
            self.assertIsNone(self.cell(rows)[name])
        from chinatravel.agent.nesy_verifier.repair_strategies.r4 import MatrixGuidedRepair
        strategy = MatrixGuidedRepair(output)
        recommendation, _ = strategy._recommend_target(
            {"hard_logic_py": ["result=(room_count(plan)==1)"]},
            {"personal_constraints": [False], "commonsense_errors": []})
        self.assertEqual(recommendation["destination_risks"][0]["evidence_status"], "unavailable")
        self.assertEqual(recommendation["expected_regressed_families"], 0.5)

    def test_legacy_matrix_loads_with_unavailable_commonsense_destination(self):
        source = self.source("R0", histories=False)
        output = self.root / "legacy/main_matrix.csv"
        rows, _ = build_main_matrix([source], output)
        with output.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(row for row in rows if row["destination_family"] != COMMONSENSE_FAMILY)
        from chinatravel.agent.nesy_verifier.repair_strategies.r4 import MatrixGuidedRepair
        matrix, _ = MatrixGuidedRepair._load_matrix(output)
        cell = matrix["accommodation"][COMMONSENSE_FAMILY]
        self.assertEqual(cell["evidence_status"], "unavailable")
        self.assertIsNone(cell["support_count"])


if __name__ == "__main__":
    unittest.main()
