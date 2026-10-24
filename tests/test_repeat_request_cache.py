"""The shared loop's per-query repeat-request cache (applies to every strategy)."""
import unittest

from chinatravel.agent.nesy_verifier.shared_repair_loop import RepeatRequestCache


class CountingLLM:
    def __init__(self, fail_first=False):
        self.calls = []
        self.input_token_count = self.output_token_count = 0
        self.fail_first = fail_first

    def __call__(self, messages, one_line=True, json_mode=False, **kwargs):
        self.calls.append(messages)
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("provider error")
        self.input_token_count += 100
        self.output_token_count += 10
        return f"reply {len(self.calls)}"


class RepeatRequestCacheTests(unittest.TestCase):
    def test_identical_request_reuses_reply_and_counts_saved_tokens(self):
        llm = CountingLLM()
        cache = RepeatRequestCache(llm)
        ask = [{"role": "user", "content": "fix it"}]
        self.assertEqual(cache(ask, one_line=False), "reply 1")
        self.assertEqual(cache(ask, one_line=False), "reply 1")
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(cache.counters(), (1, 100, 10, 0))
        # Token accounting reads the real LLM: the hit cost nothing.
        self.assertEqual((cache.input_token_count, llm.input_token_count), (100, 100))

    def test_different_content_or_options_is_a_new_request(self):
        llm = CountingLLM()
        cache = RepeatRequestCache(llm)
        cache([{"role": "user", "content": "a"}], one_line=False)
        cache([{"role": "user", "content": "b"}], one_line=False)
        cache([{"role": "user", "content": "a"}], one_line=True)
        self.assertEqual(len(llm.calls), 3)
        self.assertEqual(cache.hits, 0)

    def test_failed_call_is_not_cached(self):
        llm = CountingLLM(fail_first=True)
        cache = RepeatRequestCache(llm)
        ask = [{"role": "user", "content": "x"}]
        with self.assertRaises(RuntimeError):
            cache(ask)
        self.assertEqual(cache(ask), "reply 2")
        self.assertEqual(cache.hits, 0)

    def test_unknown_original_cost_is_counted_separately(self):
        cache = RepeatRequestCache(lambda messages, **kwargs: "same")
        cache([{"content": "x"}])
        cache([{"content": "x"}])
        self.assertEqual(cache.counters(), (1, 0, 0, 1))

    def test_attribute_reads_and_writes_reach_the_wrapped_llm(self):
        llm = CountingLLM()
        cache = RepeatRequestCache(llm)
        cache.input_token_count = 5
        self.assertEqual(llm.input_token_count, 5)
        self.assertEqual(cache.output_token_count, 0)


class CacheHitMetricsTests(unittest.TestCase):
    """End to end: the shared loop logs cache activity; the summary turns it into
    the per-query llm_cache_hits.csv columns."""

    class EchoStrategy:
        """Asks the LLM the same question every round and keeps the plan."""
        def repair(self, problem, raw_plan, verification_results, context, llm):
            from chinatravel.agent.nesy_verifier.repair_strategies.base import RepairResult
            llm([{"role": "user", "content": "same question"}], one_line=False)
            return RepairResult(raw_plan, {"strategy": "R0", "target_constraint_indices": [1]})

        def accept(self, current, candidate):
            return True

    def run_loop(self, llm, rounds=3):
        from unittest.mock import patch
        from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
        failing = dict(personal_constraints=[False], commonsense_errors=[], passed=False)
        with patch.object(loop, "verify_plan", side_effect=[dict(failing) for _ in range(rounds)]):
            return loop.run_repair_loop(dict(uid="q", people_number=1, start_city="A", target_city="B",
                                             hard_logic_py=["result=True"]),
                                        [{"day": 1}], self.EchoStrategy(), {}, llm, None,
                                        max_steps=rounds, initial_verification=dict(failing))

    def test_loop_records_hits_and_summary_counts_them(self):
        from scripts.build_repair_summary import cache_hit_metrics
        llm = CountingLLM()
        out = self.run_loop(llm)
        self.assertEqual(len(llm.calls), 1)
        hits = [h["repair_attempt"]["repair_metadata"]["llm_cache_hits"] for h in out["history"][1:]]
        self.assertEqual(hits, [0, 1, 1])
        m = cache_hit_metrics(out["history"])
        self.assertEqual((m["rounds"], m["llm_cache_hits"], m["rounds_with_cache_hit"]), (3, 2, 2))
        self.assertAlmostEqual(m["cache_hit_round_rate"], 2 / 3)
        self.assertEqual(m["first_cache_hit_step"], 2)
        self.assertEqual((m["tokens_saved"], m["tokens_saved_unknown_hits"]), (220, 0))
        self.assertTrue(m["cache_data_complete"])

    def test_every_csv_column_has_a_meaning_written_next_to_it(self):
        import csv, tempfile
        from pathlib import Path
        from scripts.build_repair_summary import CACHE_COLUMNS, CACHE_COLUMN_MEANINGS, _write_cache_hits
        self.assertTrue(all(CACHE_COLUMN_MEANINGS[c].strip() for c in CACHE_COLUMNS))
        with tempfile.TemporaryDirectory() as tmp:
            _write_cache_hits([], Path(tmp) / "llm_cache_hits.csv")
            with open(Path(tmp) / "llm_cache_hits_columns.csv", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            with open(Path(tmp) / "llm_cache_hits.csv", newline="", encoding="utf-8") as f:
                header = next(csv.reader(f))
        self.assertEqual([r["column"] for r in rows], header)
        self.assertEqual({r["column"]: r["meaning"] for r in rows}, CACHE_COLUMN_MEANINGS)

    def test_old_runs_without_cache_data(self):
        from scripts.build_repair_summary import cache_hit_metrics
        history = [{}, {"repair_attempt": {"step": 1, "repair_metadata": {}, "total_tokens_delta": 50}}]
        m = cache_hit_metrics(history)
        self.assertFalse(m["cache_data_complete"])
        self.assertEqual((m["rounds"], m["tokens_spent"]), (1, 50))
        self.assertIsNone(m["llm_cache_hits"])


if __name__ == "__main__":
    unittest.main()
