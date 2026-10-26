"""Run train-only R4 with combined or individually evaluated R0-R3 matrices."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

R4_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = R4_ROOT.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
for root in (WORKSPACE_ROOT, PROJECT_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from r4.build_main_matrix import build_main_matrix
from r4.safety import LABELS, labeled_paths, sha256, train_uids, validate_limits, validate_matrix_dir, validate_final_matrix
from r4.select_outcomes import select_outcomes


def add_run_arguments(parser):
    parser.add_argument("--mode", choices=("individual", "combined"), default="combined")
    parser.add_argument("--allow-missing-r1", action="store_true",
                        help="Pipeline check using R0/R2/R3 only; mark evidence incomplete")
    parser.add_argument("--matrix", type=Path, help="Previously pooled final matrix (combined mode)")
    parser.add_argument("--allow-synthetic-matrix", action="store_true",
                        help="Explicitly allow the clearly labeled synthetic test fixture matrix")
    parser.add_argument("--matrix-dir", action="append", default=[], metavar="R0=PATH",
                        help="Repeat for each R0-R3 regression_matrix directory")
    parser.add_argument("--perspective", choices=("candidate", "accepted"), default="candidate")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "experiments")
    parser.add_argument("--run-id")
    parser.add_argument("--splits", default="subset_train")
    parser.add_argument("--index", nargs="+")
    parser.add_argument("--query-limit", type=int, default=5)
    parser.add_argument("--llm", default="deepseek/deepseek-chat")
    parser.add_argument("--lang", choices=("en", "zh"), default="en")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--seed", type=int, default=4213)
    parser.add_argument("--dry-run", action="store_true", help="Validate evidence and save plan without model calls")


def repair_budgets(mode, maximum, labels=LABELS):
    if mode == "combined":
        return {"R4": maximum}
    if not len(labels) <= maximum <= 6:
        raise ValueError("Individual mode needs one repair per supplied matrix and at most six total")
    # All four independent trials share this cap; never four times six repairs.
    return {"R4_" + label: maximum // len(labels) + int(index < maximum % len(labels))
            for index, label in enumerate(labels)}


def prepare_run(args):
    selected_allowlist = validate_limits(args)
    training_allowlist = train_uids("subset_train")
    selected = args.index or sorted(selected_allowlist)[:args.query_limit]
    if not selected:
        raise ValueError("No queries selected")
    if args.matrix and args.matrix_dir:
        raise ValueError("Use either --matrix or four --matrix-dir arguments")
    if args.allow_synthetic_matrix and not args.matrix:
        raise ValueError("--allow-synthetic-matrix requires --matrix")
    if args.mode == "individual" and args.matrix:
        raise ValueError("Individual mode needs four labeled --matrix-dir arguments")
    sources = labeled_paths(args.matrix_dir, allow_missing_r1=args.allow_missing_r1) if args.matrix_dir else {}
    for label, directory in sources.items():
        validate_matrix_dir(directory, training_allowlist, label)
    if not sources and not args.matrix:
        raise ValueError("Supply four labeled --matrix-dir inputs or a combined --matrix")
    final_manifest = validate_final_matrix(
        args.matrix, training_allowlist, allow_missing_r1=args.allow_missing_r1,
        allow_synthetic_fixture=args.allow_synthetic_matrix,
    ) if args.matrix else None
    synthetic_matrix_fixture = bool(
        final_manifest and final_manifest.get("fixture_type") == "synthetic_test_fixture"
    )
    run_id = args.run_id or "r4-" + args.mode + "-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    if Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("--run-id must be one nonempty path component")
    output = args.output_dir.resolve()
    if (output / run_id).exists():
        raise ValueError("Run already exists; choose a new --run-id to avoid duplicate costs")
    # The runner explicitly validates this prepared directory before using it.
    run_dir = output / run_id
    inputs = run_dir / "inputs"
    if inputs.exists():
        raise ValueError("Run input directory already exists; choose a new --run-id")
    inputs.mkdir(parents=True)
    matrices = {}
    if args.mode == "individual":
        for label in sources:
            path = inputs / label / "main_matrix.csv"
            build_main_matrix([sources[label]], path, perspective=args.perspective)
            matrices["R4_" + label] = path
    elif sources:
        path = inputs / "pooled" / "main_matrix.csv"
        build_main_matrix(list(sources.values()), path, perspective=args.perspective)
        matrices["R4"] = path
    else:
        # Copy the matrix and manifest to keep an immutable per-run input snapshot.
        path = inputs / "pooled" / "main_matrix.csv"
        path.parent.mkdir()
        path.write_bytes(args.matrix.read_bytes())
        path.with_name("main_matrix_manifest.json").write_text(
            json.dumps(final_manifest, indent=2) + "\n", encoding="utf-8")
        matrices["R4"] = path
    labels = tuple(sources) if sources else LABELS
    budgets = repair_budgets(args.mode, args.max_steps, labels)
    metadata = {
        "strategy": "R4", "mode": args.mode, "split": args.splits,
        "synthetic": bool(getattr(args, "synthetic", False) or synthetic_matrix_fixture),
        "synthetic_matrix_fixture": synthetic_matrix_fixture,
        "synthetic_runtime": bool(getattr(args, "synthetic", False)),
        "allow_missing_r1": args.allow_missing_r1,
        "evidence_complete_r0_r3": (len(sources) == 4 if sources else len(final_manifest["input_matrices"]) == 4),
        "selected_query_ids": selected, "query_count": len(selected),
        "evaluation_split_partition": "test" if args.splits.endswith("_test") else "train",
        "max_repairs_per_query_total": args.max_steps, "repair_budgets": budgets,
        "max_repairs_entire_run": len(selected) * sum(budgets.values()),
        "artifact_layout_version": 2,
        "matrices": {name: {"matrix_used": name.removeprefix("R4_") if name != "R4" else "pooled",
                              "path": path.relative_to(run_dir).as_posix(), "sha256": sha256(path),
                              "manifest_sha256": sha256(path.with_name("main_matrix_manifest.json"))}
                     for name, path in matrices.items()},
        "implementation_sha256": {str(path.relative_to(WORKSPACE_ROOT)): sha256(path)
            for path in [*sorted(R4_ROOT.glob("*.py")),
                         PROJECT_ROOT / "chinatravel/agent/nesy_verifier/repair_strategies/r4.py"]},
        "training_uid_allowlist_sha256": hashlib.sha256(
            "\n".join(sorted(training_allowlist)).encode()).hexdigest(),
        "model": args.llm, "language": args.lang, "seed": args.seed,
        "matrix_update_policy": "fixed prior evidence; re-rank using each current verification report",
        "initial_plan_policy": "one generation and initial verification per query, shared by all trials",
    }
    (run_dir / "r4_run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return run_dir, matrices, metadata


def execute(args):
    run_dir, matrices, metadata = prepare_run(args)
    if args.dry_run:
        print(json.dumps(metadata, indent=2))
        return None
    from chinatravel.agent.nesy_verifier.repair_strategies import STRATEGY_FACTORIES
    from chinatravel.agent.nesy_verifier.repair_strategies.r4 import MatrixGuidedRepair
    import run_experiments

    old_factories = dict(STRATEGY_FACTORIES)
    try:
        for name, path in matrices.items():
            STRATEGY_FACTORIES[name] = lambda path=path: MatrixGuidedRepair(path)
        arguments = [
            "--strategy", *matrices, "--splits", args.splits,
            "--index", *metadata["selected_query_ids"], "--lang", args.lang,
            "--llm", args.llm, "--max-steps", str(args.max_steps),
            "--seed", str(args.seed), "--output-dir", str(run_dir.parent), "--run-id", run_dir.name,
            "--prepared-r4-inputs",
        ]
        for name, budget in metadata["repair_budgets"].items():
            arguments.extend(["--strategy-max-steps", f"{name}={budget}"])
        run_experiments.main(arguments)
    finally:
        STRATEGY_FACTORIES.clear()
        STRATEGY_FACTORIES.update(old_factories)
        if run_dir.is_dir():
            (run_dir / "r4_run_metadata.json").write_text(
                json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            select_outcomes(run_dir, metadata)
    print(f"R4 results, selection and all-trial costs: {run_dir}")
    return run_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_run_arguments(parser)
    execute(parser.parse_args(argv))


if __name__ == "__main__":
    main()
