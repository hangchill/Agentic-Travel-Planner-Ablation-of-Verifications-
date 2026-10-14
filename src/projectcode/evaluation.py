"""Pure scoring of saved outputs; no model imports or calls."""
from collections import defaultdict
from .recovery import statuses


def ratio(n, d):
    return n / d if d else None


def score(records):
    groups = defaultdict(list)
    details = []
    for row in records:
        result = row.get('result') or {}
        expected = row['case']['constraints']
        final = statuses(result.get('final_report', []))
        initial = statuses(row.get('initial_report') or [])
        hard = [c['constraint_id'] for c in expected if c['hardness'] == 'hard']
        failed = row.get('execution_error', False) or result.get('execution_error', False)
        success = bool(hard) and not failed and all(final.get(i) == 'PASS' for i in hard)
        # Unsupported-information benchmark cases are not proofs of infeasibility.
        unsolvable = row['case'].get('expected_solvability') == 'UNSOLVABLE'
        detail = dict(case_id=row['case']['semantic_case_id'], strategy=row['strategy'],
            difficulty=row['case'].get('difficulty', 'unknown'), synthetic=row.get('synthetic', False),
            excluded_unsolvable=unsolvable, execution_error=failed,
            expected_checks=len(expected), passes=sum(not failed and final.get(c['constraint_id']) == 'PASS' for c in expected),
            unverifiable=sum(final.get(c['constraint_id'], 'UNVERIFIABLE') == 'UNVERIFIABLE' for c in expected),
            hard_eligible=bool(hard), hard_success=success,
            initially_failing=bool(hard) and any(initial.get(i) == 'FAIL' for i in hard),
            initially_unknown=bool(hard) and any(initial.get(i, 'UNVERIFIABLE') == 'UNVERIFIABLE' for i in hard),
            repair_attempts=len(result.get('history', [])),
            new_violations=sum(len(h.get('new_violations', [])) for h in result.get('history', [])),
            accepted_attempts=sum(h.get('accepted', False) for h in result.get('history', [])),
            accepted_new_violations=sum(len(h.get('new_violations', [])) for h in result.get('history', []) if h.get('accepted')),
            verified_attempts=sum('report' in h for h in result.get('history', [])),
            elapsed_seconds=row.get('elapsed_seconds', result.get('elapsed_seconds')),
            model_calls=result.get('model_calls', 0),
            tokens=None)
        calls = row.get('model_metadata', [])
        token_values = [(c.get('usage') or {}).get('total_tokens') for c in calls]
        if token_values and all(isinstance(t, int) for t in token_values):
            detail['tokens'] = sum(token_values)
        details.append(detail)
        groups[(row['strategy'], detail['difficulty'], detail['synthetic'])].append(detail)
    summaries = []
    for (strategy, difficulty, synthetic), all_rows in groups.items():
        eligible = [d for d in all_rows if not d['excluded_unsolvable']]
        sums = lambda key: sum(d[key] for d in eligible)
        hard_n = sums('hard_eligible')
        repair_n = sums('initially_failing')
        tokens = [d['tokens'] for d in all_rows if d['tokens'] is not None]
        runtimes = [d['elapsed_seconds'] for d in all_rows if d['elapsed_seconds'] is not None]
        summaries.append(dict(strategy=strategy, difficulty=difficulty, synthetic=synthetic,
            runs=len(all_rows), eligible_runs=len(eligible), excluded_unsolvable=len(all_rows)-len(eligible),
            expected_checks=sums('expected_checks'), constraint_satisfaction_rate=ratio(sums('passes'), sums('expected_checks')),
            hard_eligible=hard_n, hard_success_rate=ratio(sums('hard_success'), hard_n),
            initially_failing=repair_n, repair_success_rate=ratio(sum(d['hard_success'] for d in eligible if d['initially_failing']), repair_n),
            unverifiable_checks=sums('unverifiable'), repair_attempts=sums('repair_attempts'),
            verified_attempts=sums('verified_attempts'),
            new_violations_per_attempt=ratio(sums('new_violations'), sums('repair_attempts')),
            accepted_attempts=sums('accepted_attempts'),
            new_violations_per_accepted_attempt=ratio(sums('accepted_new_violations'), sums('accepted_attempts')),
            execution_failure_rate=ratio(sum(d['execution_error'] for d in all_rows), len(all_rows)),
            mean_elapsed_seconds=ratio(sum(runtimes), len(runtimes)), runtime_observed_runs=len(runtimes),
            observed_tokens=sum(tokens) if tokens else None, token_observed_runs=len(tokens),
            model_calls=sum(d['model_calls'] for d in all_rows)))
    return {'details': details, 'summary': summaries}
