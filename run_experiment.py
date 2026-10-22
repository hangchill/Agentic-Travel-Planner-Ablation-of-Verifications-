#!/usr/bin/env python3
"""Standard runner for the repair-strategy experiments.

Runs one repair strategy (R0-R4) over a split and saves one result file per
query to a single shared, tracked location:

    experiments/<strategy>_<model>_<split>/<uid>.json

Why this exists: the original `run_exp.py` writes to `results/` and `cache/`,
which are git-ignored, so those outputs never reach teammates. This wrapper
writes committed results in one consistent folder scheme so everyone's runs are
comparable and shared. It is resume-safe: a query that already has a result file
is skipped (no repeat API cost), so re-running only fills in what's missing.

Usage (defaults match our study: DeepSeek V3, repair budget 5, English):

    python run_experiment.py --strategy R0 --split pilot5
    python run_experiment.py --strategy R1 --split subset_train
    python run_experiment.py --strategy R0 --split pilot5 --limit 2   # cheap trial

Compare strategies by running the same --split with different --strategy; the
output folders sit side by side under experiments/.
"""

import argparse
import io
import contextlib
import json
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _slug(text):
    """Filesystem-safe short label (e.g. 'deepseek/deepseek-chat' -> 'deepseek')."""
    text = str(text)
    # Use the last path segment of a provider/model id, then sanitize.
    tail = text.split("/")[-1]
    return re.sub(r"[^0-9A-Za-z.-]+", "-", tail).strip("-") or "model"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strategy", required=True,
                        choices=["R0", "R1", "R2", "R3", "R4"],
                        help="Repair strategy to run.")
    parser.add_argument("--split", required=True,
                        help="Split name, e.g. pilot5, subset_train, subset_test.")
    parser.add_argument("--llm", default="deepseek/deepseek-chat",
                        help="Model id (default: DeepSeek V3 via OpenRouter).")
    parser.add_argument("--refine-steps", type=int, default=5,
                        help="Repair budget, fixed at 5 for a fair comparison.")
    parser.add_argument("--lang", default="en", choices=["en", "zh"])
    parser.add_argument("--limit", type=int, default=None,
                        help="Only run the first N queries (cheap trial). Default: all.")
    parser.add_argument("--out-dir", default=None,
                        help="Override the output folder (default: the standard scheme).")
    args = parser.parse_args(argv)

    from chinatravel.data.load_datasets import load_query
    from chinatravel.agent.load_model import create_agent_runtime
    from types import SimpleNamespace

    out_dir = args.out_dir or os.path.join(
        PROJECT_ROOT, "experiments",
        f"{args.strategy.lower()}_{_slug(args.llm)}_{args.split}",
    )
    os.makedirs(out_dir, exist_ok=True)
    print(f"strategy={args.strategy} | split={args.split} | llm={args.llm} "
          f"| refine_steps={args.refine_steps} | lang={args.lang}")
    print(f"output -> {out_dir}")

    # Load the split's queries (English, with oracle translation as the study uses).
    with contextlib.redirect_stdout(io.StringIO()):
        ids, data = load_query(SimpleNamespace(
            splits=args.split, lang=args.lang, oracle_translation=True))
    ids = sorted(ids)
    if args.limit is not None:
        ids = ids[: args.limit]
    print(f"{len(ids)} queries to process\n")

    runtime = None  # built lazily so a fully-cached run makes no API calls
    done = ran = 0
    for i, uid in enumerate(ids, start=1):
        path = os.path.join(out_dir, f"{uid}.json")
        if os.path.exists(path):
            done += 1
            print(f"[{i:>3}/{len(ids)}] skip (already done) {uid}")
            continue
        if runtime is None:
            with contextlib.redirect_stdout(io.StringIO()):
                runtime = create_agent_runtime(
                    "LLM-modulo", args.llm, project_root_path=PROJECT_ROOT,
                    lang=args.lang, oracle_translation=True,
                    refine_steps=args.refine_steps, repair_strategy=args.strategy)
        with contextlib.redirect_stdout(io.StringIO()):
            succ, plan = runtime.agent.solve(data[uid], prob_idx=uid, oracle_verifier=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        ran += 1
        errs = len(plan.get("error_info", []))
        pc = plan.get("personal_constraints", [])
        ok = (errs == 0) and (all(x is True for x in pc) if pc else True)
        print(f"[{i:>3}/{len(ids)}] ran  {uid}: {'PASS' if ok else 'needs work'} "
              f"| errors={errs} | personal={pc}")

    print(f"\ndone. loaded {done} existing, ran {ran} new. results in {out_dir}")


if __name__ == "__main__":
    main()
