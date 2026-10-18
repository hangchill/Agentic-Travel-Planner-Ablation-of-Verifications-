"""Synthetic-only metric tests; no environment or verifier imports."""

from copy import deepcopy
import json
import unittest

from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from chinatravel.evaluation.repair_metrics import (
    compute_attempt_metrics, summarize_repair_history,
)


def attempt(before, after, *, accepted=True, targets=None, step=1, **kwargs):
    transitions = {name: [] for name in (
        "fixed", "newly_violated", "still_failed", "still_passed", "unknown"
    )}
    for index, (old, new) in enumerate(zip(before, after), 1):
        if old is None or new is None:
            group = "unknown"
        elif old is False and new is True:
            group = "fixed"
        elif old is True and new is False:
            group = "newly_violated"
        elif old is False and new is False:
            group = "still_failed"
        else:
            group = "still_passed"
        transitions[group].append(index)
    return RepairAttemptRecord(
        step=step, repair_strategy="Synthetic", query_uid="q-1",
        target_constraint_indices=targets or [], target_constraint_labels=[],
        accepted=accepted, before_personal_constraints=before,
        after_personal_constraints=after, **transitions,
        candidate_plan=[], accepted_plan_after=[], repair_metadata={}, **kwargs,
    )


def history(initial, *records):
    return [{"step": 0, "verification": {"personal_constraints": initial}}] + [
        {"step": record.step, "repair_attempt": record.to_dict()} for record in records
    ]


class AttemptMetricTests(unittest.TestCase):
    def test_fix(self):
        row = compute_attempt_metrics(attempt([False], [True]))
        self.assertEqual(row["failed_before_count"], 1)
        self.assertEqual(row["passed_before_count"], 0)
        self.assertEqual(row["fixed_count"], 1)
        self.assertEqual(row["repair_success_rate"], 1)
        self.assertIsNone(row["new_violation_rate"])
        self.assertEqual(row["net_repair_gain"], 1)
        self.assertTrue(row["candidate_all_personal_constraints_pass"])
        self.assertEqual(row["accepted_fixed_count"], 1)
        self.assertEqual(row["accepted_repair_success_rate"], 1)
        self.assertIsNone(row["targeted_repair_success_rate"])

    def test_regression(self):
        row = compute_attempt_metrics(attempt([True], [False]))
        self.assertEqual(row["newly_violated_count"], 1)
        self.assertEqual(row["new_violation_rate"], 1)
        self.assertEqual(row["net_repair_gain"], -1)
        self.assertEqual(row["accepted_new_violation_rate"], 1)
        self.assertEqual(row["accepted_net_repair_gain"], -1)
        self.assertIsNone(row["repair_success_rate"])
        self.assertFalse(row["candidate_all_personal_constraints_pass"])

    def test_simultaneous_fix_and_regression(self):
        row = compute_attempt_metrics(attempt([False, False, True], [True, False, False]))
        self.assertEqual(row["fixed_count"], 1)
        self.assertEqual(row["newly_violated_count"], 1)
        self.assertEqual(row["repair_success_rate"], 0.5)
        self.assertEqual(row["new_violation_rate"], 1)
        self.assertEqual(row["net_repair_gain"], 0)

    def test_unknowns_are_neither_passes_nor_failures(self):
        row = compute_attempt_metrics(attempt(
            [None, True, False, None], [False, None, None, True]
        ))
        self.assertEqual(row["failed_before_count"], 1)
        self.assertEqual(row["passed_before_count"], 1)
        self.assertEqual(row["fixed_count"], 0)
        self.assertEqual(row["newly_violated_count"], 0)
        self.assertEqual(row["repair_success_rate"], 0)
        self.assertEqual(row["new_violation_rate"], 0)
        self.assertFalse(row["candidate_all_personal_constraints_pass"])

    def test_rejected_candidate_preserves_effects_but_accepted_metrics_roll_back(self):
        row = compute_attempt_metrics(attempt([False, True], [True, False], accepted=False))
        self.assertEqual(row["fixed_count"], 1)
        self.assertEqual(row["newly_violated_count"], 1)
        self.assertEqual(row["new_violation_rate"], 1)
        for name in ("accepted_fixed_count", "accepted_newly_violated_count",
                     "accepted_net_repair_gain", "accepted_repair_success_rate",
                     "accepted_new_violation_rate", "accepted"):
            self.assertEqual(row[name], 0)
        self.assertEqual(row["attempt_count"], 1)
        self.assertIsNone(row["model_calls"])

    def test_explicit_target_subset(self):
        row = compute_attempt_metrics(attempt(
            [False, False, False, True, None], [True, False, True, False, True],
            targets=[1, 2, 4, 5],
        ))
        self.assertEqual(row["targeted_repair_success_rate"], 0.5)
        self.assertAlmostEqual(row["repair_success_rate"], 2 / 3)
        row = compute_attempt_metrics(attempt([True, None], [False, True], targets=[1, 2]))
        self.assertIsNone(row["targeted_repair_success_rate"])

    def test_empty_constraints(self):
        row = compute_attempt_metrics(attempt([], []))
        self.assertIsNone(row["candidate_all_personal_constraints_pass"])
        self.assertIsNone(row["repair_success_rate"])
        self.assertIsNone(row["new_violation_rate"])
        self.assertIsNone(row["targeted_repair_success_rate"])
        self.assertEqual(row["net_repair_gain"], 0)

    def test_tokens_and_flat_serialized_input_without_mutation(self):
        record = attempt([False], [True], input_tokens_delta=0,
                         output_tokens_delta=4, repair_time_seconds=0.25)
        payload = record.to_dict()
        snapshot = deepcopy(payload)
        row = compute_attempt_metrics(payload)
        self.assertEqual(row["total_tokens_delta"], 4)
        self.assertEqual(row["repair_time_seconds"], 0.25)
        self.assertEqual(payload, snapshot)
        self.assertEqual(json.loads(json.dumps(row)), row)
        self.assertTrue(all(not isinstance(value, (list, dict)) for value in row.values()))
        record.output_tokens_delta = None
        self.assertIsNone(compute_attempt_metrics(record)["total_tokens_delta"])


class HistoryMetricTests(unittest.TestCase):
    def test_mixed_trajectory_and_complete_efficiency(self):
        initial = [False, True, None]
        first = attempt(initial, [True, False, None], accepted=False, step=1,
                        input_tokens_delta=10, output_tokens_delta=2, repair_time_seconds=0.5)
        second = attempt(initial, [True, True, None], step=2,
                         input_tokens_delta=20, output_tokens_delta=3, repair_time_seconds=1)
        third = attempt([True, True, None], [True, False, True], step=3,
                        input_tokens_delta=30, output_tokens_delta=4, repair_time_seconds=1.5)
        source = history(initial, first, second, third)
        snapshot = deepcopy(source)
        row = summarize_repair_history(source)
        self.assertEqual(source, snapshot)
        self.assertEqual(row["query_uid"], "q-1")
        self.assertEqual(row["repair_strategy"], "Synthetic")
        self.assertEqual(row["attempts"], 3)
        self.assertEqual(row["accepted_attempts"], 2)
        self.assertEqual(row["rejected_attempts"], 1)
        self.assertAlmostEqual(row["acceptance_rate"], 2 / 3)
        self.assertEqual(row["total_fixed"], 2)
        self.assertEqual(row["total_newly_violated"], 2)
        self.assertEqual(row["cumulative_net_repair_gain"], 0)
        self.assertEqual(row["mean_repair_success_rate"], 1)
        self.assertEqual(row["mean_new_violation_rate"], 0.5)
        self.assertEqual(row["accepted_total_fixed"], 1)
        self.assertEqual(row["accepted_total_newly_violated"], 1)
        self.assertEqual(row["accepted_cumulative_net_repair_gain"], 0)
        self.assertEqual(row["total_input_tokens_delta"], 60)
        self.assertEqual(row["total_output_tokens_delta"], 9)
        self.assertEqual(row["total_tokens_delta"], 69)
        self.assertTrue(row["token_data_complete"])
        self.assertEqual(row["total_repair_time_seconds"], 3)
        self.assertIsNone(row["model_calls"])
        self.assertEqual(row["initial_failed_count"], 1)
        self.assertEqual(row["final_failed_count"], 1)
        self.assertEqual(row["initial_unknown_count"], 1)
        self.assertEqual(row["final_unknown_count"], 0)
        self.assertAlmostEqual(row["final_personal_constraint_satisfaction_rate"], 2 / 3)
        self.assertFalse(row["final_all_personal_constraints_pass"])
        self.assertTrue(all(not isinstance(value, (list, dict)) for value in row.values()))

    def test_final_rejected_candidate_cannot_change_final_state(self):
        row = summarize_repair_history(history(
            [False, True],
            attempt([False, True], [True, True]),
            attempt([True, True], [False, False], accepted=False, step=2),
        ))
        self.assertEqual(row["final_failed_count"], 0)
        self.assertEqual(row["final_personal_constraint_satisfaction_rate"], 1)
        self.assertTrue(row["final_all_personal_constraints_pass"])
        self.assertEqual(row["total_newly_violated"], 2)
        self.assertEqual(row["accepted_total_newly_violated"], 0)

    def test_missing_usage_and_duration_are_not_zero(self):
        row = summarize_repair_history(history(
            [False], attempt([False], [False], input_tokens_delta=4, output_tokens_delta=1,
                             repair_time_seconds=0.5),
            attempt([False], [True], step=2, input_tokens_delta=6),
        ))
        self.assertEqual(row["total_input_tokens_delta"], 10)
        self.assertIsNone(row["total_output_tokens_delta"])
        self.assertIsNone(row["total_tokens_delta"])
        self.assertFalse(row["token_data_complete"])
        self.assertIsNone(row["total_repair_time_seconds"])
        self.assertFalse(row["timing_data_complete"])
        row = summarize_repair_history(history([False], attempt([False], [True])))
        self.assertIsNone(row["total_input_tokens_delta"])
        self.assertIsNone(row["total_output_tokens_delta"])

    def test_initial_only_and_empty_or_unknown_states(self):
        for initial, satisfaction, all_pass in (
            ([], None, None), ([None], None, False), ([True], 1, True),
            ([True, None], 1, False), ([False, None], 0, False),
        ):
            with self.subTest(initial=initial):
                row = summarize_repair_history(history(initial))
                self.assertIsNone(row["query_uid"])
                self.assertIsNone(row["repair_strategy"])
                self.assertEqual(row["attempts"], 0)
                self.assertIsNone(row["acceptance_rate"])
                self.assertIsNone(row["mean_repair_success_rate"])
                self.assertEqual(row["total_tokens_delta"], 0)
                self.assertTrue(row["token_data_complete"])
                self.assertEqual(row["final_personal_constraint_satisfaction_rate"], satisfaction)
                self.assertEqual(row["final_all_personal_constraints_pass"], all_pass)

    def test_invalid_histories_do_not_silently_produce_metrics(self):
        valid = history([False], attempt([False], [True]))
        missing_record = history([False]) + [{"step": 1}]
        inconsistent = history([True], attempt([False], [True]))
        mixed_queries = history([False], attempt([False], [False]), attempt([False], [True], step=2))
        mixed_queries[2]["repair_attempt"]["query_uid"] = "q-2"
        wrong_step = deepcopy(valid)
        wrong_step[1]["step"] = 2
        mixed_strategies = deepcopy(mixed_queries)
        mixed_strategies[2]["repair_attempt"]["query_uid"] = "q-1"
        mixed_strategies[2]["repair_attempt"]["repair_strategy"] = "Other"
        for source in ([], [{"step": 0}], missing_record, inconsistent,
                       mixed_queries, wrong_step, mixed_strategies):
            with self.subTest(source=source), self.assertRaises(ValueError):
                summarize_repair_history(source)


if __name__ == "__main__":
    unittest.main()
