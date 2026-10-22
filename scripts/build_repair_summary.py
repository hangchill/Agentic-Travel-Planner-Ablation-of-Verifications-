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


def build_repair_summary(run_dir, output=None):
    root = Path(run_dir)
    if (root / '.comparison.lock').exists():
        raise ValueError('Run is still locked; build summaries after the experiment finishes')
    manifest = _load(root / 'run_manifest.json')
    rows = []
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
            else:
                failure = directory / 'initial_failure.json'
                row = {**identity, 'execution_status': 'initial_generation_failed' if failure.exists() else 'missing_checkpoint',
                       'exception': _load(failure).get('exception') if failure.exists() else None}
            rows.append(row)
    import json
    columns = sorted({key for row in rows for key in row}) or ['run_id', 'query_uid', 'repair_strategy', 'execution_status']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                     for key, value in row.items()} for row in rows)
    destination = Path(output) if output else root / 'summaries.csv'
    _write(destination, stream.getvalue())
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    build_repair_summary(args.input, args.output)


if __name__ == '__main__':
    main()
