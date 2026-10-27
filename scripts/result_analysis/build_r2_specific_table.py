"""Build the R2 rows of the Repair_specific table, split by difficulty group.

Rows (columns Easy / Med / Hum / All):
  # queries that produced a harmful candidate
  # queries where a harmful candidate was rejected
  # queries where a harmful candidate nevertheless entered the accepted trajectory
  Harmful-candidate rejection rate          rejected harmful candidates / harmful candidates
  Harmful candidates accepted rate          accepted harmful candidates / harmful candidates
  % queries where rollback preserved the prior accepted plan
                                            queries with a rejected harmful candidate after which
                                            the kept plan equals the plan before that attempt,
                                            over all queries in the group

A harmful candidate is a proposal that turned a protected personal constraint from True to
False (hook_r2's protected_regression_count > 0). Definitions reuse
scripts/analyze_repair_strategies.py (load_run, build_tables, hook_r2), so they match the
analyzer and scripts/result_analysis/ablation_comparisons. Difficulty comes from
chinatravel/evaluation/splits/subset_origin.json, as for the analyzer's R1 table.

Works on any R2 run (train or test). Reads only saved run files.

Usage:
  python scripts/result_analysis/build_r2_specific_table.py --run experiments/subset_test-r2 \
      [--output r2_specific_table.csv]
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

GROUPS = {'Easy': 'easy', 'Med': 'medium', 'Hum': 'human', 'All': None}
COLUMNS = ['Repair Strategy', 'Metric', *GROUPS]


## ---------- per-query evidence ----------

def harmful_rows(run):
    """hook_r2's per-attempt table, restricted to harmful candidates."""
    from scripts import analyze_repair_strategies as analysis
    attempts, _, _ = analysis.build_tables(run)
    hook = analysis.hook_r2(attempts)[0]['protection_and_rollback']
    known = hook[hook.protected_regression_count.notna()]
    return known[known.protected_regression_count > 0]


def preserved_queries(run, rejected_harmful):
    """Queries where some rejected harmful attempt left the kept plan equal to the plan before it."""
    preserved = set()
    for uid in run.query_uids:
        steps = set(rejected_harmful.loc[rejected_harmful.query_uid == uid, 'step'])
        if not steps:
            continue
        before = (run.checkpoints.get(uid) or {}).get('initial_raw_plan')
        for r in sorted((r for r in run.attempts if r['query_uid'] == uid), key=lambda r: r['step']):
            after = r.get('accepted_plan_after')
            if r['step'] in steps and before is not None and after == before:
                preserved.add(uid)
            before = after
    return preserved


## ---------- table ----------

def pct(part, whole, empty):
    return f'{part / whole * 100:.2f}%' if whole else empty


def build_rows(run, origin):
    harmful = harmful_rows(run)
    rejected = harmful[harmful.rejected.eq(True)]
    accepted = harmful[harmful.accepted.eq(True)]
    preserved = preserved_queries(run, rejected)

    values = {}
    for label, group in GROUPS.items():
        uids = {u for u in run.query_uids if group is None or origin.get(u) == group}
        h, rej, acc = (frame[frame.query_uid.isin(uids)] for frame in (harmful, rejected, accepted))
        values[label] = [
            h.query_uid.nunique(),
            rej.query_uid.nunique(),
            acc.query_uid.nunique(),
            pct(len(rej), len(h), 'n/a (0 harmful)'),
            pct(len(acc), len(h), 'n/a (0 harmful)'),
            pct(len(preserved & uids), len(uids), 'n/a (0 queries)'),
        ]
    metrics = [
        '# queries that produced a harmful candidate',
        '# queries where a harmful candidate was rejected',
        '# queries where a harmful candidate nevertheless entered the accepted trajectory',
        'Harmful-candidate rejection rate',
        'Harmful candidates accepted rate',
        '% queries where rollback preserved the prior accepted plan',
    ]
    return [{'Repair Strategy': 'R2', 'Metric': metric, **{label: values[label][i] for label in GROUPS}}
            for i, metric in enumerate(metrics)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--run', required=True, help='R2 run folder, e.g. experiments/subset_test-r2')
    parser.add_argument('--output', help='CSV file to write (default: print only)')
    args = parser.parse_args(argv)

    from scripts import analyze_repair_strategies as analysis
    run = analysis.load_run('R2', Path(args.run))
    origin = json.loads((ROOT / 'chinatravel/evaluation/splits/subset_origin.json')
                        .read_text(encoding='utf-8'))['origin']
    missing = [u for u in run.query_uids if u not in origin]
    if missing:
        raise SystemExit(f'No difficulty group in subset_origin.json for: {missing}')

    rows = build_rows(run, origin)
    widths = [max(len(str(r[c])) for r in rows + [dict(zip(COLUMNS, COLUMNS))]) for c in COLUMNS]
    for r in [dict(zip(COLUMNS, COLUMNS)), *rows]:
        print(' | '.join(str(r[c]).ljust(w) for c, w in zip(COLUMNS, widths)))
    if args.output:
        with open(args.output, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print('\nWrote', args.output)


if __name__ == '__main__':
    # The analyzer reads run files with the platform default encoding; on Windows that is not
    # UTF-8, so restart in UTF-8 mode rather than fail on the first non-ASCII character.
    if not sys.flags.utf8_mode and os.name == 'nt':
        sys.exit(subprocess.run([sys.executable, '-X', 'utf8', *sys.argv]).returncode)
    main()
