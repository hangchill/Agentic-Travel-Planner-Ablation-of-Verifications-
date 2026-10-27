"""Synthetic records only: matrix semantics, audit coverage and offline CLI."""

from copy import deepcopy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from chinatravel.evaluation.regression_matrix import (
    aggregate_contributions, build_contribution_table, build_regression_matrix,
    summarize_matrix_coverage, load_regression_matrix,
)
from scripts.matrix_building.build_regression_matrix import load_input


TRIP = "result=day_count(plan)==2"
BUDGET = ("cost=0\nfor activity in allactivities(plan):\n"
          "  cost+=activity_cost(activity)\nresult=cost<=1000")
UNMAPPED = "result=True"
COMPOUND = ("result=day_count(plan)==2\nfor activity in allactivities(plan):\n"
            "  if room_count(activity)!=1: result=False")
AMBIGUOUS = ("names=set()\nfor activity in allactivities(plan):\n"
             "  if activity_type(activity) in ['attraction','lunch']: names.add(activity_position(activity))\n"
             "result={'A'}<=names")


def record(before=None, after=None, codes=None, targets=None, **kwargs):
    before = [False, True] if before is None else before
    after = [True, False] if after is None else after
    codes = [TRIP, BUDGET] if codes is None else codes
    transitions = {name: [] for name in ("fixed", "newly_violated", "still_failed", "still_passed", "unknown")}
    for index, (old, new) in enumerate(zip(before, after), 1):
        group = ("unknown" if old is None or new is None else
                 "fixed" if old is False and new is True else
                 "newly_violated" if old is True and new is False else
                 "still_failed" if old is False else "still_passed")
        transitions[group].append(index)
    values = dict(
        step=1, query_uid="q1", repair_strategy="R2", accepted=True,
        target_constraint_indices=[1] if targets is None else targets,
        target_constraint_labels=[], before_personal_constraints=before,
        after_personal_constraints=after, **transitions, candidate_plan=[],
        accepted_plan_after=[], repair_metadata={}, target_provenance="explicit",
        constraint_descriptors=[{"constraint_index": index, "hard_logic_py": code}
                                for index, code in enumerate(codes, 1)],
    )
    values.update(kwargs)
    return RepairAttemptRecord(**values)


def cell(analysis, perspective="candidate", source="trip_specification", destination="monetary_budget"):
    return next(row for row in analysis["aggregate"] if row["perspective"] == perspective
                and row["source_family"] == source and row["destination_family"] == destination)


def contribution(analysis, destination="monetary_budget", perspective="candidate"):
    return next(row for row in analysis["contributions"]
                if row["destination_family"] == destination and row["perspective"] == perspective)


class RegressionMatrixTests(unittest.TestCase):
    def test_support_examples_and_multi_target_exclusion(self):
        for support, regressions in ((1, 0), (50, 0), (5, 2), (0, 0)):
            with self.subTest(support=support):
                records = [record(step=i + 1, after=[True, i >= regressions])
                           for i in range(support)]
                # Retain multi-target records for auditing, never for either count.
                records.append(record(step=support + 1, targets=[1, 2]))
                result = build_regression_matrix(records)
                for perspective in ("candidate", "accepted_trajectory"):
                    row = cell(result, perspective)
                    self.assertEqual(row["support_count"], support)
                    self.assertEqual(row["regression_count"], regressions)
                    self.assertEqual(row["regression_rate"], regressions / support if support else None)
                self.assertEqual(result["coverage"]["multi_target_attempts"], 1)

    def test_single_target_regression_and_accepted_population(self):
        result = build_regression_matrix([record()], run_id="experiment-1")
        for perspective in ("candidate", "accepted_trajectory"):
            row = cell(result, perspective)
            self.assertEqual(row["regression_count"], 1)
            self.assertEqual(row["eligible_count"], 1)
            self.assertEqual(row["regression_rate"], 1)
            self.assertEqual(row["support_attempts"], 1)
            self.assertEqual(row["support_queries"], 1)
        row = contribution(result)
        self.assertEqual(row["run_id"], "experiment-1")
        self.assertEqual(row["source_constraint_index"], 1)
        self.assertEqual(row["target_provenance"], "explicit")

    def test_eligible_destination_stays_pass(self):
        result = build_regression_matrix([record(after=[True, True])])
        self.assertEqual(cell(result)["eligible_count"], 1)
        self.assertEqual(cell(result)["regression_rate"], 0)

    def test_destination_before_fail_or_unknown_is_ineligible(self):
        for before in ([False, False], [False, None]):
            result = build_regression_matrix([record(before=before)])
            self.assertEqual(cell(result)["eligible_count"], 0)
            self.assertIsNone(cell(result)["regression_rate"])
            self.assertEqual(contribution(result)["exclusion_reason"], "destination_not_all_pass_before")

    def test_unknown_after_excludes_whole_family(self):
        for before, after, codes in (
            ([False, True], [True, None], [TRIP, BUDGET]),
            ([False, True, True], [True, False, None], [TRIP, BUDGET, BUDGET]),
        ):
            result = build_regression_matrix([record(before, after, codes)])
            self.assertEqual(cell(result)["eligible_count"], 0)
            self.assertIsNone(cell(result)["regression_rate"])
            self.assertIsNone(contribution(result)["regression"])
            self.assertEqual(cell(result)["unknown_after_excluded_attempts"], 1)
            self.assertEqual(result["coverage"]["destination_unknown_after_excluded_contributions"], 1)

    def test_many_destination_instances_count_once(self):
        result = build_regression_matrix([record(
            [False, True, True], [True, False, False], [TRIP, BUDGET, BUDGET],
        )])
        self.assertEqual(cell(result)["eligible_count"], 1)
        self.assertEqual(cell(result)["regression_count"], 1)
        self.assertEqual(result["coverage"]["candidate_eligible_contributions"], 1)
        result = build_regression_matrix([record(
            [False, True, False], [True, False, True], [TRIP, BUDGET, BUDGET],
        )])
        self.assertEqual(cell(result)["eligible_count"], 0)

    def test_unmapped_compound_ambiguous_source_exclusions(self):
        for code, status in ((UNMAPPED, "unmapped"), (COMPOUND, "compound"), (AMBIGUOUS, "ambiguous")):
            with self.subTest(status=status):
                result = build_regression_matrix([record(codes=[code, BUDGET])])
                self.assertFalse(any(row["eligible"] for row in result["contributions"]))
                self.assertEqual(contribution(result)["exclusion_reason"], "source_" + status)
                self.assertEqual(result["coverage"]["target_mapping"][status], 1)
                self.assertIn(status, contribution(result)["descriptor_exclusions"])

    def test_zero_and_multiple_targets_are_not_inferred(self):
        for targets, reason in (([], "zero_targets"), ([1, 2], "multiple_targets")):
            result = build_regression_matrix([record(targets=targets)])
            self.assertFalse(any(row["eligible"] for row in result["contributions"]))
            self.assertEqual(contribution(result)["exclusion_reason"], reason)

    def test_source_must_be_false(self):
        for state in (True, None):
            result = build_regression_matrix([record(before=[state, True])])
            self.assertEqual(contribution(result)["exclusion_reason"], "source_not_false")
            self.assertEqual(result["coverage"]["source_target_not_false_attempts"], 1)

    def test_rejected_regression_retains_denominator_for_both_perspectives(self):
        result = build_regression_matrix([record(accepted=False)])
        self.assertEqual(cell(result)["regression_count"], 1)
        accepted = cell(result, "accepted_trajectory")
        self.assertEqual(accepted["regression_count"], 0)
        self.assertEqual(accepted["eligible_count"], 1)
        self.assertEqual(accepted["regression_rate"], 0)

    def test_query_support_is_unique_across_attempts_and_runs(self):
        records = [record(), record(step=2), record(query_uid="q2")]
        result = build_regression_matrix(records)
        self.assertEqual(cell(result)["eligible_count"], 3)
        self.assertEqual(cell(result)["support_queries"], 2)
        result = build_regression_matrix([
            {"run_id": "a", "repair_attempt": record().to_dict()},
            {"run_id": "b", "repair_attempt": record().to_dict()},
        ])
        self.assertEqual(cell(result)["eligible_count"], 2)
        self.assertEqual(cell(result)["support_queries"], 1)

    def test_duplicates_count_once_and_conflicts_raise(self):
        result = build_regression_matrix([record(), record().to_dict()])
        self.assertEqual(cell(result)["eligible_count"], 1)
        self.assertEqual(result["coverage"]["total_repair_attempts"], 1)
        self.assertEqual(result["coverage"]["duplicate_records_ignored"], 1)
        self.assertEqual(aggregate_contributions(result["contributions"] * 2), result["aggregate"])
        with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
            build_regression_matrix([record(), record(accepted=False)])
        rows = result["contributions"]
        conflicting = deepcopy(rows[0])
        conflicting["accepted"] = False
        with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
            aggregate_contributions(rows + [conflicting])

    def test_diagonal_and_absent_families_are_unavailable(self):
        result = build_regression_matrix([record()])
        self.assertEqual(contribution(result, "trip_specification")["exclusion_reason"], "structurally_ineligible_diagonal")
        self.assertFalse(any(row["source_family"] == row["destination_family"] for row in result["aggregate"]))
        self.assertIsNone(cell(result, destination="dining")["regression_rate"])
        self.assertEqual(contribution(result, "dining")["exclusion_reason"], "destination_family_absent")

    def test_missing_descriptors_and_missing_identity(self):
        for codes in ([], [TRIP]):
            result = build_regression_matrix([record(codes=codes, query_uid=None)])
            self.assertFalse(any(row["eligible"] for row in result["contributions"]))
            self.assertEqual(result["coverage"]["attempts_missing_descriptors"], 1)
            self.assertEqual(result["coverage"]["missing_descriptor_instances"], 2 - len(codes))
            self.assertEqual(result["coverage"]["distinct_query_count"], 0)
            self.assertEqual(result["coverage"]["missing_query_uid_attempts"], 1)

    def test_coverage_counts_unique_attempts_and_target_instances(self):
        records = [
            record(step=1, targets=[]), record(step=2, targets=[1, 2]),
            record(step=3), record(step=4, after=[True, None]),
            record(step=5, before=[True, True]), record(step=6, codes=[]),
            record(step=7, codes=[UNMAPPED, BUDGET]),
            record(step=8, codes=[COMPOUND, BUDGET]),
            record(step=9, codes=[AMBIGUOUS, BUDGET]),
        ]
        coverage = summarize_matrix_coverage(records)
        self.assertEqual(coverage["total_repair_attempts"], 9)
        self.assertEqual(coverage["zero_target_attempts"], 1)
        self.assertEqual(coverage["single_target_attempts"], 7)
        self.assertEqual(coverage["multi_target_attempts"], 1)
        self.assertEqual(coverage["target_mapping"], {"mapped": 5, "unmapped": 1, "ambiguous": 1, "compound": 1})
        self.assertEqual(coverage["target_missing_descriptor_instances"], 1)
        self.assertEqual(coverage["source_target_not_false_attempts"], 1)
        self.assertEqual(coverage["attempts_missing_descriptors"], 1)
        self.assertEqual(coverage["destination_unknown_after_excluded_attempts"], 1)
        self.assertEqual(coverage["candidate_eligible_contributions"], 1)
        self.assertEqual(coverage["accepted_eligible_contributions"], 1)
        self.assertEqual(coverage["distinct_query_count"], 1)

    def test_no_input_mutation_and_flat_serializable_rows(self):
        payload = record().to_dict()
        snapshot = deepcopy(payload)
        result = build_regression_matrix([payload])
        self.assertEqual(payload, snapshot)
        self.assertEqual(result, json.loads(json.dumps(result)))
        self.assertEqual(build_contribution_table([payload]), result["contributions"])
        for row in result["contributions"] + result["aggregate"]:
            self.assertTrue(all(not isinstance(value, (list, dict)) for value in row.values()))
        self.assertEqual(build_regression_matrix([])["aggregate"], [])

    def test_bad_record_indices_and_mixed_definition_versions_rejected(self):
        payload = record().to_dict()
        payload["target_constraint_indices"] = [3]
        with self.assertRaises(ValueError):
            build_regression_matrix([payload])
        payload = record().to_dict()
        payload["constraint_descriptors"].append({"constraint_index": 3, "hard_logic_py": TRIP})
        with self.assertRaises(ValueError):
            build_regression_matrix([payload])
        rows = build_contribution_table([record()])
        rows[0]["normalizer_version"] = "other"
        with self.assertRaises(ValueError):
            aggregate_contributions(rows)


    def test_unchanged_attempt_excluded_from_denominator(self):
        result = build_regression_matrix([
            record(step=1, before=[False, True], after=[False, True],
                   changed_slot_count=0, total_comparable_slots=2,
                   changed_slot_rate=0.0, decision_reason="no_progress_unchanged",),
            record(step=2, before=[False, True], after=[True, False], changed_slot_count=1,
                   total_comparable_slots=2, changed_slot_rate=0.5,),])
        row = cell(result)
        self.assertEqual(row["support_count"], 1)
        self.assertEqual(row["regression_count"], 1)
        self.assertEqual(row["regression_rate"], 1.0)
        self.assertEqual(result["coverage"]["unchanged_attempts"], 1)
        self.assertEqual(result["coverage"]["total_repair_attempts"], 2)
        unchanged = next(
            row for row in result["contributions"]
            if row["step"] == 1
            and row["perspective"] == "candidate"
            and row["destination_family"] == "monetary_budget")
        self.assertFalse(unchanged["eligible"])
        self.assertEqual(unchanged["exclusion_reason"], "unchanged_candidate",)

    def test_changed_attempt_without_regression_still_counts(self):
        result = build_regression_matrix([
            record(before=[False, True], after=[True, True], changed_slot_count=1,
                   total_comparable_slots=2, changed_slot_rate=0.5,)])
        row = cell(result)
        self.assertEqual(row["support_count"], 1)
        self.assertEqual(row["regression_count"], 0)
        self.assertEqual(row["regression_rate"], 0.0)

    def test_missing_changed_slot_count_not_assumed_unchanged(self):
        result = build_regression_matrix([
            record(before=[False, True], after=[True, False],
                   changed_slot_count=None, decision_reason=None,)])
        row = cell(result)
        self.assertEqual(row["support_count"], 1)
        self.assertEqual(row["regression_count"], 1)
        self.assertEqual(result["coverage"]["unchanged_attempts"], 0)

    def test_commonsense_repair_source_captures_regression(self):
        # A changed commonsense zero-target attempt that regresses a passing
        # personal destination (monetary_budget True -> False).
        result = build_regression_matrix([record(
            before=[False, True], after=[True, False], codes=[TRIP, BUDGET],
            targets=[], repair_phase="commonsense", target_commonsense_errors=["x"],
            changed_slot_count=1, total_comparable_slots=2, changed_slot_rate=0.5,
        )])
        row = cell(result, source="commonsense_repair", destination="monetary_budget")
        self.assertEqual(row["regression_count"], 1)
        self.assertEqual(row["support_count"], 1)
        self.assertEqual(row["regression_rate"], 1.0)
        accepted = cell(result, "accepted_trajectory",
                        source="commonsense_repair", destination="monetary_budget")
        self.assertEqual(accepted["regression_count"], 1)
        self.assertEqual(accepted["support_count"], 1)
        self.assertEqual(accepted["regression_rate"], 1.0)
        contrib = next(row for row in result["contributions"]
                       if row["source_family"] == "commonsense_repair"
                       and row["destination_family"] == "monetary_budget"
                       and row["perspective"] == "candidate")
        self.assertIsNone(contrib["source_constraint_index"])
        self.assertFalse(contrib["is_single_target"])
        self.assertFalse(contrib["is_isolated_personal_target"])

    def test_commonsense_unchanged_still_excluded(self):
        result = build_regression_matrix([record(
            before=[False, True], after=[False, True], codes=[TRIP, BUDGET],
            targets=[], repair_phase="commonsense", target_commonsense_errors=["x"],
            changed_slot_count=0, total_comparable_slots=2, changed_slot_rate=0.0,
            decision_reason="no_progress_unchanged",
        )])
        row = cell(result, source="commonsense_repair", destination="monetary_budget")
        self.assertEqual(row["support_count"], 0)
        self.assertIsNone(row["regression_rate"])
        self.assertEqual(result["coverage"]["unchanged_attempts"], 1)
        # The unchanged exclusion runs first, so the attempt never becomes a
        # commonsense source and contributes no eligible support anywhere.
        self.assertFalse(any(row["source_family"] == "commonsense_repair"
                             for row in result["contributions"]))
        self.assertFalse(any(row["eligible"] for row in result["contributions"]))
        excluded = next(row for row in result["contributions"]
                        if row["destination_family"] == "monetary_budget"
                        and row["perspective"] == "candidate")
        self.assertFalse(excluded["eligible"])
        self.assertEqual(excluded["exclusion_reason"], "unchanged_candidate")

    def test_commonsense_source_unsupported_cells(self):
        def commonsense(before, after, codes):
            return record(before=before, after=after, codes=codes, targets=[],
                          repair_phase="commonsense", target_commonsense_errors=["x"],
                          changed_slot_count=1, total_comparable_slots=2, changed_slot_rate=0.5)
        cases = (
            # destination family absent from the descriptors
            (commonsense([False, True], [True, False], [TRIP, TRIP]),
             "dining", "destination_family_absent"),
            # mapped destination was FAIL before repair
            (commonsense([False, False], [True, False], [TRIP, BUDGET]),
             "monetary_budget", "destination_not_all_pass_before"),
            # mapped destination is UNKNOWN after repair
            (commonsense([False, True], [True, None], [TRIP, BUDGET]),
             "monetary_budget", "destination_unknown_after"),
        )
        for attempt, destination, reason in cases:
            with self.subTest(reason=reason):
                result = build_regression_matrix([attempt])
                row = cell(result, source="commonsense_repair", destination=destination)
                self.assertEqual(row["support_count"], 0)
                self.assertIsNone(row["regression_rate"])
                contrib = next(row for row in result["contributions"]
                               if row["source_family"] == "commonsense_repair"
                               and row["destination_family"] == destination
                               and row["perspective"] == "candidate")
                self.assertFalse(contrib["eligible"])
                self.assertEqual(contrib["exclusion_reason"], reason)

    def test_personal_zero_and_multi_target_unchanged(self):
        # Non-commonsense zero-target still excluded as zero_targets.
        zero = build_regression_matrix([record(targets=[], repair_phase=None)])
        self.assertEqual(contribution(zero)["exclusion_reason"], "zero_targets")
        self.assertFalse(any(row["source_family"] == "commonsense_repair"
                             and row["eligible"] for row in zero["contributions"]))
        # Multi-target still excluded as multiple_targets even in commonsense phase.
        multi = build_regression_matrix([record(targets=[1, 2], repair_phase="commonsense",
                                                 target_commonsense_errors=["x"])])
        self.assertEqual(contribution(multi)["exclusion_reason"], "multiple_targets")


class MatrixCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/matrix_building/build_regression_matrix.py"), *args],
            capture_output=True, text=True, check=False,
        )

    def test_cli_jsonl_history_outputs_blank_missing_cells_and_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jsonl, history_file, output = root / "records.jsonl", root / "history.json", root / "out"
            jsonl.write_text(json.dumps(record(accepted=False).to_dict()) + "\n", encoding="utf-8")
            history_file.write_text(json.dumps({"history": [
                {"step": 0, "verification": {"personal_constraints": [False, True]}},
                {"step": 1, "repair_attempt": record(accepted=False).to_dict()},
            ]}), encoding="utf-8")
            result = self.run_cli("--input", str(jsonl), str(history_file), "--run-id", "run-a", "--output-dir", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(output.iterdir())), 13)
            coverage = json.loads((output / "matrix_coverage.json").read_text())
            self.assertEqual(coverage["duplicate_records_ignored"], 1)
            with (output / "regression_matrix_by_scope_long.csv").open(newline="") as stream:
                scoped = list(csv.DictReader(stream))
            self.assertTrue(scoped)
            self.assertTrue(all(row["editable_scope"] == "" for row in scoped))
            self.assertEqual(coverage["missing_editable_scope_attempts"], 1)
            for filename, expected in (("regression_matrix_candidate.csv", "1.0"),
                                       ("regression_matrix_accepted.csv", "0.0")):
                with (output / filename).open(newline="") as stream:
                    rows = list(csv.DictReader(stream))
                row = next(row for row in rows if row["source_family"] == "trip_specification")
                self.assertEqual(row["monetary_budget"], expected)
                self.assertEqual(row["trip_specification"], "")
                self.assertEqual(row["dining"], "")

    def test_paired_exports_and_loader_global_and_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_file, output = root / "records.jsonl", root / "out"
            records = [record(step=i + 1, after=[True, i >= 2], accepted=False,
                              editable_scope="slot") for i in range(5)]
            input_file.write_text("\n".join(json.dumps(r.to_dict()) for r in records))
            result = self.run_cli("--input", str(input_file), "--output-dir", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            for directory in (output, output / "by_scope" / "slot"):
                candidate = load_regression_matrix(directory)
                accepted = load_regression_matrix(directory, "accepted_trajectory")
                self.assertEqual(candidate["trip_specification"]["monetary_budget"],
                                 dict(rate=0.4, support_count=5, regression_count=2))
                self.assertEqual(accepted["trip_specification"]["monetary_budget"],
                                 dict(rate=0.0, support_count=5, regression_count=0))
                self.assertEqual(candidate["trip_specification"]["dining"],
                                 dict(rate=None, support_count=0, regression_count=0))
                self.assertEqual(candidate["trip_specification"]["trip_specification"],
                                 dict(rate=None, support_count=0, regression_count=0))
            # A mismatched trio must fail instead of silently pairing bad evidence.
            path = output / "candidate_regression_count.csv"
            path.write_text(path.read_text().replace(
                "trip_specification,0,0,2,", "trip_specification,0,0,6,"))
            with self.assertRaises(ValueError):
                load_regression_matrix(output)

    def test_commonsense_row_in_exports_and_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_file, output = root / "records.jsonl", root / "out"
            records = [
                # single-target personal regression on monetary_budget
                record(step=1, before=[False, True], after=[True, False],
                       codes=[TRIP, BUDGET], editable_scope="plan"),
                # commonsense zero-target regression on monetary_budget
                record(step=2, before=[False, True], after=[True, False],
                       codes=[TRIP, BUDGET], targets=[], repair_phase="commonsense",
                       target_commonsense_errors=["x"], changed_slot_count=1,
                       total_comparable_slots=2, changed_slot_rate=0.5,
                       editable_scope="plan"),
            ]
            input_file.write_text("\n".join(json.dumps(r.to_dict()) for r in records), encoding="utf-8")
            result = self.run_cli("--input", str(input_file), "--output-dir", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            pivots = (
                "candidate_regression_rate.csv", "candidate_regression_support.csv",
                "candidate_regression_count.csv", "accepted_regression_rate.csv",
                "accepted_regression_support.csv", "accepted_regression_count.csv",
                "regression_matrix_candidate.csv", "regression_matrix_accepted.csv",
            )
            for filename in pivots:
                with (output / filename).open(newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), 10)
                self.assertEqual(rows[-1]["source_family"], "commonsense_repair")
            matrix = load_regression_matrix(output)
            self.assertIn("commonsense_repair", matrix)
            self.assertEqual(matrix["commonsense_repair"]["monetary_budget"],
                             dict(rate=1.0, support_count=1, regression_count=1))

    def test_cli_strategy_filter_and_multiple_strategy_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_file, output = root / "attempts.jsonl", root / "out"
            input_file.write_text("\n".join(json.dumps(r.to_dict()) for r in
                                  [record(), record(repair_strategy="R0", query_uid="q2")]), encoding="utf-8")
            result = self.run_cli("--input", str(input_file), "--output-dir", str(output))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--repair-strategy", result.stderr)
            self.assertFalse(output.exists())
            result = self.run_cli("--input", str(input_file), "--output-dir", str(output), "--repair-strategy", "R2")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((output / "matrix_coverage.json").read_text())["total_repair_attempts"], 1)

    def test_loader_rejects_legacy_history_without_attempt_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.json"
            path.write_text(json.dumps([{"step": 1, "accepted": True}]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "lacks a formal"):
                load_input(path)


if __name__ == "__main__":
    unittest.main()
