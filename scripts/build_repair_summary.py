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


## Per-query outcomes of the shared schedule, written to phase_outcomes.csv
## (kept out of summaries.csv):
##   - the end of step 5 vs the end of the run: step 6 is the last round and,
##     for R3, can be a whole-plan rewrite with no round left to recover from;
##   - the commonsense rounds, taken together (a query can have several: the
##     loop repeats commonsense rounds while errors remain).
CHECKPOINT_STEP = 5
STEP5_COLUMNS = ('step5_repair_success', 'step5_all_personal_constraints_pass',
                 'step5_personal_constraint_satisfaction_rate', 'attempts_after_step5',
                 'after_step5_newly_violated_count')
CS_COLUMNS = ('cs_attempts', 'cs_step', 'cs_scope', 'cs_accepted', 'cs_errors_before', 'cs_errors_after',
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
    """What the commonsense rounds of one query did, taken together.

    ``cs_attempts`` counts commonsense rounds and ``cs_accepted`` how many were
    accepted; ``cs_step`` / ``cs_scope`` describe the first one. The errors the
    first round was asked to fix (``target_commonsense_errors``) are compared with
    the accepted plan right after the last round, as verified by the shared loop
    (a rejected last candidate leaves the earlier accepted plan in place). Errors
    are matched by message, duplicates kept: a message that changes slightly counts
    as one fixed plus one new; the before/after totals are exact.
    ``cs_broke_personal``: distinct personal constraints any commonsense candidate
    broke. ``cs_recovered``: when accepted commonsense rounds broke personal
    constraints, whether they all pass again at the end. All values are None
    without a commonsense round; "after" values are None when that verification
    is missing."""
    from collections import Counter

    metrics = dict.fromkeys(CS_COLUMNS)
    current = history[0].get('verification') or {}
    final_personal = list(current.get('personal_constraints') or [])
    first, after_last = None, None
    attempts = accepted = 0
    broke, accepted_broke = set(), set()
    for entry in history[1:]:
        attempt = entry.get('repair_attempt') or {}
        if attempt.get('accepted'):
            final_personal = list(attempt.get('after_personal_constraints') or [])
            current = entry.get('verification') or {}
        if attempt.get('repair_phase') == 'commonsense':
            attempts += 1
            first = first or attempt
            newly = set(attempt.get('newly_violated') or [])
            broke |= newly
            if attempt.get('accepted'):
                accepted += 1
                accepted_broke |= newly
            after_last = current
    if first is None:
        return metrics
    before = list(first.get('target_commonsense_errors') or [])
    after = after_last.get('commonsense_errors')
    known_after = isinstance(after, list) and not after_last.get('verification_unavailable')
    metrics.update(
        cs_attempts=attempts, cs_step=first.get('step'), cs_scope=first.get('editable_scope'),
        cs_accepted=accepted,
        cs_errors_before=len(before) if before else first.get('concurrent_commonsense_failure_count'),
        cs_errors_after=len(after) if known_after else None,
        cs_passed_after=after_last.get('passed') if known_after else None,
        cs_broke_personal=len(broke))
    if known_after and before:
        metrics['cs_errors_fixed'] = sum((Counter(before) - Counter(after)).values())
        metrics['cs_errors_new'] = sum((Counter(after) - Counter(before)).values())
    if accepted_broke:
        metrics['cs_recovered'] = all(0 < i <= len(final_personal) and final_personal[i - 1] is True
                                      for i in accepted_broke)
    return metrics


## Shared repeat-request cache, per query, written to llm_cache_hits.csv. A cache
## hit is a request a strategy had already sent for this query (identical
## messages and options), answered from the earlier reply without calling the
## model (see RepeatRequestCache in shared_repair_loop.py). Many hits mean the
## strategy kept asking the same thing, i.e. it got stuck.
## Plain-language meaning of every llm_cache_hits.csv column, written next to it
## as llm_cache_hits_columns.csv (columns: column, meaning).
CACHE_COLUMN_MEANINGS = {
    'run_id': 'Experiment run the row comes from.',
    'query_uid': 'Query ID.',
    'repair_strategy': 'Repair strategy (R0-R4).',
    'execution_status': 'Whether the query finished (completed) or failed / is missing.',
    'rounds': 'Repair rounds taken (at most 6).',
    'cache_data_complete': 'False for runs made before the shared repeat-request cache existed; '
                           'their cache columns are left empty.',
    'llm_cache_hits': 'Requests answered from the cache: the strategy sent exactly the same request '
                      'again for this query, so the earlier reply was reused without calling the model. '
                      'R1 can send several requests per round, so this can exceed rounds.',
    'rounds_with_cache_hit': 'Rounds with at least one cache hit, i.e. rounds where the strategy was '
                             'stuck repeating itself.',
    'cache_hit_round_rate': 'rounds_with_cache_hit / rounds: share of rounds spent repeating.',
    'first_cache_hit_step': 'Round in which the strategy first repeated a request (empty if never).',
    'tokens_spent': 'Tokens of real model calls during repair (input + output).',
    'tokens_saved': 'Tokens the reused replies originally cost, i.e. avoided by the cache.',
    'tokens_saved_unknown_hits': 'Cache hits whose original token cost was not reported, so they '
                                 'are missing from tokens_saved.',
    'tokens_without_cache': 'tokens_spent + tokens_saved: what the query would have cost without the cache.',
}
CACHE_COLUMNS = tuple(CACHE_COLUMN_MEANINGS)


def cache_hit_metrics(history):
    """Per-query cache activity from each attempt's ``repair_metadata``.

    rounds: repair rounds taken. llm_cache_hits: requests answered from the
    cache (a round can contain several requests, e.g. R1). rounds_with_cache_hit
    / cache_hit_round_rate: rounds with at least one hit, and their share of
    rounds. tokens_spent: tokens of real model calls; tokens_saved: what the
    reused replies originally cost (tokens_saved_unknown_hits counts hits whose
    original cost was not reported); tokens_without_cache = spent + saved.
    Runs made before the cache existed have no cache data: cache_data_complete
    is False and the cache values are None."""
    attempts = [entry.get('repair_attempt') or {} for entry in history[1:]]
    metadata = [attempt.get('repair_metadata') or {} for attempt in attempts]
    complete = all('llm_cache_hits' in item for item in metadata)
    metrics = dict.fromkeys(CACHE_COLUMNS[4:])
    metrics.update(rounds=len(attempts), cache_data_complete=complete)
    spent = [attempt.get('total_tokens_delta') for attempt in attempts]
    if all(type(value) is int for value in spent):
        metrics['tokens_spent'] = sum(spent)
    if not complete:
        return metrics
    hits = [item['llm_cache_hits'] for item in metadata]
    hit_steps = [attempt.get('step') for attempt, count in zip(attempts, hits) if count > 0]
    saved = sum(item['llm_cache_saved_input_tokens'] + item['llm_cache_saved_output_tokens']
                for item in metadata)
    metrics.update(
        llm_cache_hits=sum(hits), rounds_with_cache_hit=len(hit_steps),
        cache_hit_round_rate=len(hit_steps) / len(attempts) if attempts else None,
        first_cache_hit_step=hit_steps[0] if hit_steps else None,
        tokens_saved=saved,
        tokens_saved_unknown_hits=sum(item['llm_cache_saved_unknown'] for item in metadata))
    if metrics['tokens_spent'] is not None:
        metrics['tokens_without_cache'] = metrics['tokens_spent'] + saved
    return metrics


def _write_cache_hits(rows, destination):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=CACHE_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    _write(destination, stream.getvalue())
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(('column', 'meaning'))
    writer.writerows(CACHE_COLUMN_MEANINGS.items())
    _write(destination.with_name(destination.stem + '_columns.csv'), stream.getvalue())
    for strategy in sorted({row['repair_strategy'] for row in rows}):
        done = [row for row in rows if row['repair_strategy'] == strategy and row.get('cache_data_complete')]
        missing = sum(row['repair_strategy'] == strategy and row.get('cache_data_complete') is False
                      for row in rows)
        if missing:
            print(f"{strategy}: {missing} queries have no cache data (run made before the shared "
                  f"repeat-request cache); cache totals skipped")
            continue
        if not done:
            continue
        total = lambda key: sum(row[key] or 0 for row in done)
        rounds = total('rounds')
        rate = f"{total('rounds_with_cache_hit') / rounds:.1%}" if rounds else 'n/a'
        print(f"{strategy}: cache hits {total('llm_cache_hits')} in {total('rounds_with_cache_hit')}/{rounds} "
              f"rounds ({rate}) | queries with a hit "
              f"{sum((row['llm_cache_hits'] or 0) > 0 for row in done)}/{len(done)} | tokens spent "
              f"{total('tokens_spent')}, saved {total('tokens_saved')}")


def build_repair_summary(run_dir, output=None):
    root = Path(run_dir)
    if (root / '.comparison.lock').exists():
        raise ValueError('Run is still locked; build summaries after the experiment finishes')
    manifest = _load(root / 'run_manifest.json')
    rows = []
    outcomes = []       ## phase_outcomes.csv rows, one per summaries.csv row
    report_rows = []    ## summary + outcome values of checkpointed queries, for pass_rates.csv
    cache_rows = []     ## llm_cache_hits.csv rows, one per summaries.csv row
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
                cache = {**identity, 'execution_status': row['execution_status'],
                         **cache_hit_metrics(result['repair_history'])}
            else:
                failure = directory / 'initial_failure.json'
                row = {**identity, 'execution_status': 'initial_generation_failed' if failure.exists() else 'missing_checkpoint',
                       'exception': _load(failure).get('exception') if failure.exists() else None}
                outcome = {**dict.fromkeys(OUTCOME_COLUMNS), **identity,
                           'execution_status': row['execution_status']}
                cache = {**dict.fromkeys(CACHE_COLUMNS), **identity,
                         'execution_status': row['execution_status']}
            rows.append(row)
            outcomes.append(outcome)
            cache_rows.append(cache)
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
    _write_cache_hits(cache_rows, destination.with_name('llm_cache_hits.csv'))
    return rows


## Queries are grouped by the step of their FIRST commonsense round (for R3
## this is also its scope: 1-2 slot, 3-4 day, 5-6 plan). Early groups are the
## queries whose personal constraints all passed early, so they get more
## commonsense rounds.
CS_STEP_GROUPS = (('1_2', (1, 2)), ('3_4', (3, 4)), ('5_6', (5, 6)))

PASS_RATE_COLUMNS = ['repair_strategy', 'queries', 'step5_pass_rate', 'final_pass_rate',
                     'step5_personal_all_pass_rate', 'final_personal_all_pass_rate',
                     'queries_with_attempt_after_step5', 'queries_broken_after_step5',
                     'cs_steps', 'cs_attempts', 'cs_errors_before', 'cs_errors_fixed', 'cs_errors_new',
                     'cs_fix_rate', 'cs_pass_after_rate',
                     *[f'{name}_{group}' for group, _ in CS_STEP_GROUPS
                       for name in ('cs_steps', 'cs_pass_after_rate')],
                     'cs_broke_personal_queries', 'cs_recovered_queries']


def _commonsense_report(done):
    """Per-strategy totals of the commonsense rounds (cs_* columns of
    phase_outcomes.csv). cs_steps = queries with at least one commonsense round,
    cs_attempts = commonsense rounds in total. cs_fix_rate = errors fixed / errors
    the first round was asked to fix, over queries whose after-verification is
    known; pass-after rates count a missing result as not passed."""
    steps = [row for row in done if row.get('cs_step') is not None]
    known = [row for row in steps if row.get('cs_errors_fixed') is not None]
    before = sum(row['cs_errors_before'] for row in known)
    fixed = sum(row['cs_errors_fixed'] for row in known)
    pass_rate = lambda group: (sum(row.get('cs_passed_after') is True for row in group) / len(group)
                               if group else None)
    report = {'cs_steps': len(steps),
              'cs_attempts': sum(row.get('cs_attempts') or 0 for row in steps),
              'cs_errors_before': before, 'cs_errors_fixed': fixed,
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

    The difference shows what the last round (step 6) gained or broke.
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
        print(f"  commonsense: {line['cs_steps']} queries, {line['cs_attempts']} rounds | "
              f"errors {line['cs_errors_before']} -> "
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
