"""HTTP mock transports exercise real dispatch accounting without SDK/network."""

from itertools import count
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from chinatravel.agent.llms import OpenAICompatibleLLM
from chinatravel.agent.model_usage import instrumented_http_client, usage_snapshot, usage_delta, reported_token_count
from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
from chinatravel.agent.nesy_verifier.repair_strategies.base import RepairResult
from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from chinatravel.evaluation.repair_metrics import compute_attempt_metrics, summarize_repair_history


class EfficiencyTests(unittest.TestCase):
    def model(self, responses, retries=0, wire_api="chat"):
        model = OpenAICompatibleLLM("mock-model", wire_api=wire_api)
        responses = iter(responses)

        def handle(request):
            item = next(responses)
            if isinstance(item, Exception):
                raise item
            status, usage = item
            payload = {"text": "candidate"}
            if usage is not None:
                payload["usage"] = usage
            return httpx.Response(status, json=payload)

        client = instrumented_http_client(model, httpx.MockTransport(handle))
        self.addCleanup(client.close)

        def create(**kwargs):
            for index in range(retries + 1):
                response = client.post("https://mock.invalid/v1/" + (
                    "responses" if wire_api == "responses" else "chat/completions"), json={})
                if response.status_code >= 500 and index < retries:
                    continue
                response.raise_for_status()
                if wire_api == "responses":
                    return SimpleNamespace(output_text="candidate", usage=response.json().get("usage"))
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="candidate"))],
                                       usage=response.json().get("usage"))

        model._llm = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                                     responses=SimpleNamespace(create=create))
        return model

    def history(self, model, *, calls=1, accepted=True, fail=False):
        class Strategy:
            def repair(self, **kwargs):
                for _ in range(calls):
                    kwargs["llm"]([{"role": "user", "content": "repair"}], one_line=False)
                if fail:
                    raise ValueError("parse failed after model response")
                return RepairResult([], {"strategy": "R0", "target_constraint_indices": [1],
                                         "editable_scope": "plan"})

            def accept(self, *args):
                return accepted

        histories = []
        initial = {"personal_constraints": [False, True], "passed": False}
        with patch.object(loop, "verify_plan", return_value={"personal_constraints": [True, False], "passed": False}), \
             patch.object(loop, "perf_counter", side_effect=count(100)):
            try:
                result = loop.run_repair_loop(
                    {"uid": "q", "people_number": 1, "start_city": "A", "target_city": "B"},
                    [], Strategy(), {}, model, None, max_steps=1,
                    initial_verification=initial, history_callback=histories.append)
                return result["history"]
            except ValueError:
                if not fail:
                    raise
                return histories[-1]

    def test_two_actual_requests_not_one_attempt_and_no_nested_double_count(self):
        model = self.model([(200, {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13})] * 2)
        history = self.history(model, calls=2, accepted=False)
        record = history[1]["repair_attempt"]
        self.assertEqual(record["model_calls"], 2)
        self.assertEqual(record["repair_model_calls"], 2)
        self.assertEqual(record["verification_model_calls"], 0)
        self.assertEqual(record["input_tokens_delta"], 20)
        self.assertEqual(record["output_tokens_delta"], 6)
        self.assertEqual(record["total_tokens_delta"], 26)
        summary = summarize_repair_history(history)
        self.assertEqual(summary["attempts"], 1)
        self.assertEqual(summary["model_calls"], 2)
        self.assertEqual(summary["total_tokens_delta"], 26)
        self.assertEqual(summary["total_newly_violated"], 1)
        self.assertEqual(summary["accepted_total_newly_violated"], 0)
        self.assertEqual(summary["rejection_rate"], 1)

    def test_sdk_retry_dispatch_is_counted_and_unknown_usage_is_incomplete(self):
        model = self.model([(500, None), (200, {"input_tokens": 8, "output_tokens": 2})], retries=1)
        record = self.history(model)[1]["repair_attempt"]
        self.assertEqual(record["model_calls"], 2)
        self.assertEqual(record["failed_model_calls"], 1)
        self.assertIsNone(record["input_tokens_delta"])
        self.assertIsNone(record["output_tokens_delta"])
        self.assertIsNone(record["total_tokens_delta"])
        self.assertEqual(model.input_token_count, 8)  # legacy partial counter, not full usage
        self.assertIsNone(reported_token_count(model, "input"))
        summary = summarize_repair_history([{"step": 0, "verification": {"personal_constraints": [False, True]}},
                                            {"step": 1, "accepted": True, "verification": {"personal_constraints": [True, False]},
                                             "repair_attempt": record}])
        self.assertIsNone(summary["total_tokens_delta"])
        self.assertFalse(summary["token_data_complete"])

    def test_retry_usage_is_summed_when_both_responses_report_it(self):
        model = self.model([(500, {"prompt_tokens": 2, "completion_tokens": 0}),
                            (200, {"prompt_tokens": 8, "completion_tokens": 2})], retries=1)
        record = self.history(model)[1]["repair_attempt"]
        self.assertEqual(record["input_tokens_delta"], 10)
        self.assertEqual(record["total_tokens_delta"], 12)

    def test_responses_api_and_missing_usage(self):
        model = self.model([(200, {"input_tokens": 7, "output_tokens": 3}), (200, None)], wire_api="responses")
        model.chat([])
        before = usage_snapshot(model)
        model([], one_line=False)
        after = usage_snapshot(model)
        self.assertEqual(after["model_calls"], 2)
        self.assertEqual(before["total_tokens"], 10)
        self.assertIsNone(usage_delta(before, after, "input_tokens"))
        self.assertIsNone(usage_delta(before, after, "total_tokens"))

    def test_missing_usage_is_local_to_attempt_but_run_total_stays_incomplete(self):
        model = self.model([(200, None), (200, {"prompt_tokens": 7, "completion_tokens": 2})])
        first = self.history(model, accepted=False)
        second = self.history(model, accepted=False)[1]
        second["step"] = second["repair_attempt"]["step"] = 2
        self.assertIsNone(first[1]["repair_attempt"]["input_tokens_delta"])
        self.assertEqual(second["repair_attempt"]["input_tokens_delta"], 7)
        summary = summarize_repair_history(first + [second])
        self.assertIsNone(summary["total_input_tokens_delta"])
        self.assertIsNone(summary["total_tokens_delta"])
        self.assertEqual(summary["model_calls"], 2)

    def test_failed_dispatch_preserves_cost_and_exception_in_attempt(self):
        model = self.model([httpx.ConnectError("connection failed")])
        history = self.history(model, fail=True)
        record = history[1]["repair_attempt"]
        self.assertEqual(record["model_calls"], 1)
        self.assertEqual(record["failed_model_calls"], 1)
        self.assertIsNone(record["input_tokens_delta"])
        self.assertIsNotNone(record["exception"])
        self.assertEqual(record["after_personal_constraints"], [None, None])
        self.assertFalse(record["accepted"])
        self.assertEqual(summarize_repair_history(history)["model_calls"], 1)

    def test_initial_calls_are_excluded_and_timing_segments_are_monotonic(self):
        model = self.model([(200, {"input_tokens": 7, "output_tokens": 3})] * 2)
        model([], one_line=False)  # shared initial generation, before attempt snapshot
        history = self.history(model)
        record = history[1]["repair_attempt"]
        self.assertEqual(record["model_calls"], 1)
        self.assertEqual(record["total_tokens_delta"], 10)
        self.assertEqual(record["repair_time_seconds"], 1)
        self.assertEqual(record["verification_time_seconds"], 1)
        self.assertEqual(record["attempt_time_seconds"], 4)
        self.assertEqual(record["changed_slot_count"], 0)
        self.assertEqual(record["total_comparable_slots"], 0)
        self.assertIsNone(record["changed_slot_rate"])
        self.assertEqual(RepairAttemptRecord.from_dict(record).to_dict(), record)

    def test_usage_reset_and_total_only_response(self):
        model = self.model([(200, {"total_tokens": 10})])
        row = compute_attempt_metrics(self.history(model)[1]["repair_attempt"])
        self.assertIsNone(row["input_tokens_delta"])
        self.assertIsNone(row["output_tokens_delta"])
        self.assertEqual(row["total_tokens_delta"], 10)
        model.reset_usage()
        self.assertEqual(model.usage_snapshot()["model_calls"], 0)
        self.assertEqual(model.usage_snapshot()["missing_input"], 0)

    def test_verification_dispatches_are_separate_and_not_double_counted(self):
        model = self.model([(200, {"input_tokens": 2, "output_tokens": 1})] * 2)

        class Strategy:
            def repair(self, **kwargs):
                kwargs["llm"]([], one_line=False)
                return RepairResult([], {})

            def accept(self, *args):
                return False

        def verifier(*args, **kwargs):
            model.chat([])
            return {"personal_constraints": [False], "passed": False}

        with patch.object(loop, "verify_plan", side_effect=verifier):
            result = loop.run_repair_loop(
                {"people_number": 1, "start_city": "A", "target_city": "B"}, [], Strategy(), {}, model, None,
                max_steps=1, initial_verification={"personal_constraints": [False], "passed": False})
        record = result["history"][1]["repair_attempt"]
        self.assertEqual(record["repair_model_calls"], 1)
        self.assertEqual(record["verification_model_calls"], 1)
        self.assertEqual(record["model_calls"], 2)
        self.assertEqual(record["total_tokens_delta"], 6)

    def test_targeted_run_summary_and_scope_statistics(self):
        from test_repair_metrics import attempt, history

        records = [
            attempt([False, False, None], [True, False, True], targets=[1, 2, 3],
                    editable_scope="slot", scope_level=1),
            attempt([True, False, True], [True, False, True], step=2, targets=[2], accepted=False,
                    editable_scope="day", scope_level=2, escalation_reason="repeated_failure"),
            attempt([True, False, True], [True, True, True], step=3, targets=[2],
                    editable_scope="plan", scope_level=3),
        ]
        source = history([False, False, None], *records)
        source[-1]["verification"] = {"personal_constraints": [True, True, True], "passed": True}
        summary = summarize_repair_history(source)
        self.assertEqual(summary["targeted_repair_success_rate"], 2 / 4)
        self.assertEqual(summary["mean_targeted_repair_success_rate"], 0.5)
        self.assertEqual(summary["escalation_count"], 2)
        self.assertEqual(summary["highest_scope_level"], 3)
        self.assertEqual(summary["attempts_scope_slot"], 1)
        self.assertEqual(summary["attempts_scope_day"], 1)
        self.assertEqual(summary["attempts_scope_plan"], 1)
        self.assertEqual(summary["attempts_until_success"], 3)
        self.assertTrue(summary["repair_success"])
        self.assertEqual(summary["decision_rejected_attempts"], 1)
        self.assertEqual(summary["decision_rejection_rate"], 1 / 3)
        records[1].editable_scope = records[1].scope_level = None
        incomplete = summarize_repair_history(history([False, False, None], *records))
        self.assertIsNone(incomplete["escalation_count"])
        self.assertIsNone(incomplete["highest_scope_level"])
        self.assertFalse(incomplete["scope_data_complete"])


if __name__ == "__main__":
    unittest.main()
