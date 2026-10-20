"""Build a deterministic group-aware train/test manifest from query JSON/JSONL."""
import argparse
import json
from pathlib import Path
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chinatravel.evaluation.train_test_split import build_split, _unique_object


def load_queries(path):
    path = Path(path)
    if path.is_dir():
        return [record for child in sorted(path.glob("*.json")) for record in load_queries(child)]
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line, object_pairs_hook=_unique_object) for line in text.splitlines() if line.strip()]
    value = json.loads(text, object_pairs_hook=_unique_object)
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and "uid" in value:
        return [value]
    if isinstance(value, dict) and all(isinstance(record, dict) and record.get("uid") == uid for uid, record in value.items()):
        return list(value.values())
    raise ValueError(f"Unsupported query data: {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    records = [record for path in args.input for record in load_queries(path)]
    manifest = build_split(records, args.train_fraction, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
