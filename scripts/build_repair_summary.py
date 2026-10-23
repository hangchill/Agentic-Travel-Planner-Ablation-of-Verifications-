"""Build repair-process summaries offline from authoritative query checkpoints."""
import argparse
import csv
import io
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chinatravel.evaluation.repair_comparison import _component, _load, _write
from chinatravel.evaluation.repair_metrics import summarize_checkpoint


## Per-query outcomes at two points of the shared 5+1 schedule, written to
## phase_outcomes.csv (kept out of summaries.csv):
##   - the end of step 5 vs the end of the run: step 6 is usually the
##     commonsense step and, for R3, can be a whole-plan rewrite with no step
##     left to recover from;
##   - the commonsense step itself, whichever step it ran at.
CHECKPOINT_STEP = 5
STEP5_COLUMNS = ('step5_repair_success', 'step5_all_personal_constraints_pass',
                 'step5_personal_constraint_satisfaction_rate', 'attempts_after_step5',
                 'after_step5_newly_violated_count')
CS_COLUMNS = ('cs_step', 'cs_scope', 'cs_accepted', 'cs_errors_before', 'cs_errors_after',
              'cs_errors_fixed', 'cs_errors_new', 'cs_passed_after', 'cs_broke_personal',
              'cs_recovered')
OUTCOME_COLUMNS = ('run_id', 'query_uid', 'repair_strategy', 'execution_status',
                   *STEP5_COLUMNS, *CS_COLUMNS)


def step5_metrics(history):
    """The accepted plan's outcome as of the end of step 5 (equal to the final
    outcome when the run stopped at or before step 5). A rejected proposal
    never changes the accepted outcome. after_step5_newly_violated_count counts
    personal constraints passing at step 5 but failing at the end."""
    verification = history[0].get('verification') or {}
    current = list(verification.get('personal_constraints') or [])
    passed = verification.get('passed')
    checkpoint, checkpoint_passed, later = list(current), passed, 0
    for entry in history[1:]:
        attempt = entry.get('repair_attempt') or {}
        if attempt.get('accepted'):
            current = list(attempt.get('after_personal_constraints') or [])
            passed = (entry.get('verification') or {}).get('passed')
        step = attempt.get('step', entry.get('step'))
        if step is not None and step <= CHECKPOINT_STEP:
            checkpoint, checkpoint_passed = list(current), passed
        else:
            later += 1
    known = [state for state in checkpoint if state is not None]
    return {
        'step5_repair_success': checkpoint_passed,
        'step5_all_personal_constraints_pass': all(s is True for s in checkpoint) if checkpoint else None,
        'step5_personal_constraint_satisfaction_rate':
            sum(s is True for s in known) / len(known) if known else None,
        'attempts_after_step5': later,
        'after_step5_newly_violated_count': sum(
            before is True and after is False for before, after in zip(checkpoint, current)),
    }


def commonsense_step_metrics(history):
    """What the scheduled commonsense step did, whichever step it ran at.

    Compares the plan just before it (the errors it was asked to fix,
    ``target_commonsense_errors``) with its candidate just after it, as verified
    by the shared loop. Errors are matched by message, duplicates kept: a message
    that changes slightly counts as one fixed plus one new; the before/after
    totals are exact. ``cs_recovered``: when the accepted step broke personal
    constraints, whether they all pass again at the end. All values are None
    without a commonsense step; "after" values are None when its verification
    is missing."""
    from collections import Counter

    metrics = dict.fromkeys(CS_COLUMNS)
    final_personal = list((history[0].get('verification') or {}).get('personal_constraints') or [])
    step_entry = None
    for entry in history[1:]:
        attempt = entry.get('repair_attempt') or {}
        if attempt.get('accepted'):
            final_personal = list(attempt.get('after_personal_constraints') or [])
        if step_entry is None and attempt.get('repair_phase') == 'commonsense':
            step_entry = entry
    if step_entry is None:
        return metrics
    attempt = step_entry['repair_attempt']
    before = list(attempt.get('target_commonsense_errors') or [])
    verification = step_entry.get('verification') or {}
    after = verification.get('commonsense_errors')
    known_after = isinstance(after, list) and not verification.get('verification_unavailable')
    broke = list(attempt.get('newly_violated') or [])
    metrics.update(
        cs_step=attempt.get('step'), cs_scope=attempt.get('editable_scope'),
        cs_accepted=attempt.get('accepted'),
        cs_errors_before=len(before) if before else attempt.get('concurrent_commonsense_failure_count'),
        cs_errors_after=len(after) if known_after else None,
        cs_passed_after=verification.get('passed') if known_after else None,
        cs_broke_personal=len(broke))
    if known_after and before:
        metrics['cs_errors_fixed'] = sum((Counter(before) - Counter(after)).values())
        metrics['cs_errors_new'] = sum((Counter(after) - Counter(before)).values())
    if broke and attempt.get('accepted'):
        metrics['cs_recovered'] = all(0 < i <= len(final_personal) and final_personal[i - 1] is True
                                      for i in broke)
    return metrics


def build_repair_summary(run_dir, output=None):
    root = Path(run_dir)
    if (root / '.comparison.lock').exists():
        raise ValueError('Run is still locked; build summaries after the experiment finishes')
    manifest = _load(root / 'run_manifest.json')
    rows = []
    outcomes = []       ## phase_outcomes.csv rows, one per summaries.csv row
    report_rows = []    ## summary + outcome values of checkpointed queries, for pass_rates.csv
    for uid in manifest['query_uids']:
        directory = root / 'queries' / _component(uid)
        initial = directory / 'initial_state.json'
        metadata = _load(initial)['state'].get('generation_metadata', {}) if initial.exists() else {}
        for strategy in manifest['repair_strategies_requested']:
            path = directory / (_component(strategy) + '.json')
            identity = dict(run_id=manifest['run_id'], query_uid=uid, repair_strategy=strategy)
            if path.exists():
                result = _load(path)
                if any(result.get(key) != value for key, value in identity.items()):
                    raise ValueError(f'Checkpoint identity mismatch: {path}')
                row = {**summarize_checkpoint(result, metadata), **identity,
                       'initial_plan_hash': result.get('initial_plan_hash'),
                       'execution_status': result['execution_status'],
                       'exception': result.get('exception'), 'stop_reason': result.get('stop_reason')}
                outcome = {**identity, 'execution_status': row['execution_status'],
                           **step5_metrics(result['repair_history']),
                           **commonsense_step_metrics(result['repair_history'])}
                report_rows.append({**row, **outcome})
            else:
                failure = directory / 'initial_failure.json'
                row = {**identity, 'execution_status': 'initial_generation_failed' if failure.exists() else 'missing_checkpoint',
                       'exception': _load(failure).get('exception') if failure.exists() else None}
                outcome = {**dict.fromkeys(OUTCOME_COLUMNS), **identity,
                           'execution_status': row['execution_status']}
            rows.append(row)
            outcomes.append(outcome)
    import json
    columns = sorted({key for row in rows for key in row}) or ['run_id', 'query_uid', 'repair_strategy', 'execution_status']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                     for key, value in row.items()} for row in rows)
    destination = Path(output) if output else root / 'summaries.csv'
    _write(destination, stream.getvalue())
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=OUTCOME_COLUMNS)
    writer.writeheader()
    writer.writerows(outcomes)
    _write(destination.with_name('phase_outcomes.csv'), stream.getvalue())
    _write_pass_rates(report_rows, destination.with_name('pass_rates.csv'))
    return rows


## Commonsense steps are grouped by the step they ran at (for R3 this is also
## the scope: 1-2 slot, 3-4 day, 5-6 plan). Early groups are the queries whose
## personal constraints all passed before step 5.
CS_STEP_GROUPS = (('1_2', (1, 2)), ('3_4', (3, 4)), ('5_6', (5, 6)))

PASS_RATE_COLUMNS = ['repair_strategy', 'queries', 'step5_pass_rate', 'final_pass_rate',
                     'step5_personal_all_pass_rate', 'final_personal_all_pass_rate',
                     'queries_with_attempt_after_step5', 'queries_broken_after_step5',
                     'cs_steps', 'cs_errors_before', 'cs_errors_fixed', 'cs_errors_new',
                     'cs_fix_rate', 'cs_pass_after_rate',
                     *[f'{name}_{group}' for group, _ in CS_STEP_GROUPS
                       for name in ('cs_steps', 'cs_pass_after_rate')],
                     'cs_broke_personal_queries', 'cs_recovered_queries']


def _commonsense_report(done):
    """Per-strategy totals of the scheduled commonsense step (cs_* columns of
    phase_outcomes.csv). cs_fix_rate = errors fixed / errors it was asked to fix,
    over steps whose after-verification is known; pass-after rates count a
    missing result as not passed."""
    steps = [row for row in done if row.get('cs_step') is not None]
    known = [row for row in steps if row.get('cs_errors_fixed') is not None]
    before = sum(row['cs_errors_before'] for row in known)
    fixed = sum(row['cs_errors_fixed'] for row in known)
    pass_rate = lambda group: (sum(row.get('cs_passed_after') is True for row in group) / len(group)
                               if group else None)
    report = {'cs_steps': len(steps), 'cs_errors_before': before, 'cs_errors_fixed': fixed,
              'cs_errors_new': sum(row['cs_errors_new'] for row in known),
              'cs_fix_rate': fixed / before if before else None,
              'cs_pass_after_rate': pass_rate(steps),
              'cs_broke_personal_queries': sum((row.get('cs_broke_personal') or 0) > 0 for row in steps),
              'cs_recovered_queries': sum(row.get('cs_recovered') is True for row in steps)}
    for group, numbers in CS_STEP_GROUPS:
        members = [row for row in steps if row['cs_step'] in numbers]
        report[f'cs_steps_{group}'] = len(members)
        report[f'cs_pass_after_rate_{group}'] = pass_rate(members)
    return report


def pass_rate_report(rows):
    """Per-strategy pass rates at the end of step 5 and at the end of the run.

    The difference shows what the last step (usually the commonsense step) did.
    Rates are over all queries with a checkpoint; a None outcome counts as not
    passed. queries_broken_after_step5 counts queries where a personal constraint
    passing at step 5 was failing at the end."""
    report = []
    for strategy in sorted({row['repair_strategy'] for row in rows}):
        done = [row for row in rows if row['repair_strategy'] == strategy and 'step5_repair_success' in row]
        rate = lambda key: sum(row.get(key) is True for row in done) / len(done) if done else None
        report.append({
            'repair_strategy': strategy, 'queries': len(done),
            'step5_pass_rate': rate('step5_repair_success'),
            'final_pass_rate': rate('repair_success'),
            'step5_personal_all_pass_rate': rate('step5_all_personal_constraints_pass'),
            'final_personal_all_pass_rate': rate('final_all_personal_constraints_pass'),
            'queries_with_attempt_after_step5': sum(row['attempts_after_step5'] > 0 for row in done),
            'queries_broken_after_step5': sum(row['after_step5_newly_violated_count'] > 0 for row in done),
            **_commonsense_report(done),
        })
    return report


def _write_pass_rates(rows, destination):
    report = pass_rate_report(rows)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=PASS_RATE_COLUMNS)
    writer.writeheader()
    writer.writerows(report)
    _write(destination, stream.getvalue())
    fmt = lambda value: 'n/a' if value is None else f'{value:.1%}'
    for line in report:
        print(f"{line['repair_strategy']}: {line['queries']} queries | pass rate step 5 "
              f"{fmt(line['step5_pass_rate'])} -> final {fmt(line['final_pass_rate'])} | "
              f"all personal pass step 5 {fmt(line['step5_personal_all_pass_rate'])} -> final "
              f"{fmt(line['final_personal_all_pass_rate'])} | broken after step 5: "
              f"{line['queries_broken_after_step5']}/{line['queries_with_attempt_after_step5']}")
        groups = ', '.join(f"steps {group.replace('_', '-')}: {line[f'cs_steps_{group}']} "
                           f"({fmt(line[f'cs_pass_after_rate_{group}'])} pass)"
                           for group, _ in CS_STEP_GROUPS)
        print(f"  commonsense step: {line['cs_steps']} queries | errors {line['cs_errors_before']} -> "
              f"fixed {line['cs_errors_fixed']}, new {line['cs_errors_new']} "
              f"(fix rate {fmt(line['cs_fix_rate'])}) | pass right after "
              f"{fmt(line['cs_pass_after_rate'])} [{groups}] | broke personal: "
              f"{line['cs_broke_personal_queries']}, recovered {line['cs_recovered_queries']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    build_repair_summary(args.input, args.output)


if __name__ == '__main__':
    main()
