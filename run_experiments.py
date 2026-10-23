"""Run one repair strategy and persist evidence for separate offline evaluation."""

import argparse
from copy import deepcopy
import os
from pathlib import Path
import random
import subprocess
import sys
import uuid

from chinatravel.agent.nesy_verifier.repair_strategies import STRATEGY_FACTORIES
from chinatravel.evaluation.train_test_split import load_manifest, select_queries
from chinatravel.evaluation.repair_comparison import run_comparison, stable_hash
from dotenv import load_dotenv


def model_settings(llm):
    return {"model": getattr(llm, "model", None), "name": getattr(llm, "name", None),
            "default_request_args": deepcopy(getattr(llm, "default_request_args", {})),
            "max_tokens": getattr(llm, "max_tokens", None),
            "wire_api": getattr(llm, "wire_api", None),
            "token_limit_arg": getattr(llm, "token_limit_arg", None),
            "endpoint_override": os.getenv("CHINATRAVEL_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL")}


def main(argv=None):
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", default="easy")
    parser.add_argument("--index", nargs="+", help="Optional query UID subset")
    parser.add_argument("--lang", choices=("zh", "en"), default="en")
    parser.add_argument("--llm")
    parser.add_argument("--strategy", default="R0")
    parser.add_argument("--skip-unavailable", action="store_true")
    parser.add_argument("--max-steps", "--refine_steps", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=Path("results/experiments"))
    parser.add_argument("--run-id")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--top-p", type=float)
    parser.add_argument("--seed", type=int, help="Seed Python/NumPy locally; does not guarantee provider determinism")
    parser.add_argument("--oracle-translation", "--oracle_translation", action="store_true", default=True)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--partition", choices=("train", "test"))
    args = parser.parse_args(argv)
    args.repair_strategies = [args.strategy]
    if bool(args.split_manifest) != bool(args.partition):
        parser.error("--split-manifest and --partition must be supplied together")
    if args.resume and not args.run_id:
        parser.error("--resume requires --run-id")
    if args.retry_failed and not args.resume:
        parser.error("--retry-failed requires --resume")
    unavailable = sorted(set(args.repair_strategies) - STRATEGY_FACTORIES.keys())
    if unavailable and not args.skip_unavailable:
        parser.error(f"Unavailable strategies: {unavailable}; registered: {sorted(STRATEGY_FACTORIES)}")
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative")
    from chinatravel.agent.load_model import init_agent, init_llm, resolve_llm_name
    from chinatravel.data.load_datasets import load_query
    from chinatravel.environment.world_env import WorldEnv

    model = resolve_llm_name(args.llm)
    if not model:
        parser.error("Specify --llm or configure CHINATRAVEL_OPENAI_MODEL/OPENAI_MODEL")
    if args.seed is not None:
        import numpy as np

        random.seed(args.seed)
        np.random.seed(args.seed)
    run_id = args.run_id or uuid.uuid4().hex
    root = args.output_dir / run_id

    def new_llm():
        llm = init_llm(model)
        if args.temperature is not None:
            llm.default_request_args["temperature"] = args.temperature
        if args.top_p is not None:
            llm.default_request_args["top_p"] = args.top_p
        return llm

    settings = model_settings(new_llm())

    def agent_factory(label):
        llm = new_llm()
        if model_settings(llm) != settings:
            raise ValueError("Model configuration changed during comparison")
        return init_agent({"method": "LLM-modulo", "env": WorldEnv(lang=args.lang),
                           "backbone_llm": llm, "model": llm,
                           "cache_dir": str(root / "runtime_cache"),
                           "log_dir": str(root / "logs" / label), "debug": True,
                           "refine_steps": args.max_steps, "max_steps": args.max_steps,
                           "repair_strategy": None, "lang": args.lang})

    def prepare(problem):
        agent = agent_factory("initial_generation")
        stdout, stderr = sys.stdout, sys.stderr
        try:
            return agent.prepare_initial_repair_state(problem)
        finally:
            sys.stdout, sys.stderr = stdout, stderr

    def runtime(state, name):
        agent = agent_factory(name)
        agent.problem = deepcopy(state.problem)
        return agent.backbone_llm, agent.translate_innercity_transport

    ids, data = load_query(args)
    if args.split_manifest and len(ids) != len(set(ids)):
        parser.error("Query UIDs must be unique before partition selection")
    if args.split_manifest:
        data = select_queries(data, load_manifest(args.split_manifest), args.partition)
        ids = list(data)
    selected = args.index or ids
    if any(uid not in data for uid in selected):
        parser.error("Requested UID is not present in the selected split")
    if len(set(selected)) != len(selected):
        parser.error("Query UIDs must be unique")
    project = Path(__file__).resolve().parent
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip()
        diff = subprocess.check_output(["git", "diff", "HEAD"], cwd=project, text=True)
    except (OSError, subprocess.CalledProcessError):
        commit, diff = None, None
    # Include uncommitted implementation bytes, not just HEAD, in resume compatibility.
    source_paths = [Path(__file__), project / "chinatravel/evaluation/repair_comparison.py",
                    project / "chinatravel/evaluation/repair_metrics.py",
                    project / "chinatravel/evaluation/edit_footprint.py",
                    project / "chinatravel/evaluation/train_test_split.py",
                    project / "chinatravel/agent/llms.py", project / "chinatravel/agent/model_usage.py", project / "chinatravel/agent/system_usage.py",
                    *sorted((project / "chinatravel/agent/nesy_verifier").rglob("*.py")),
                    *sorted((project / "chinatravel/environment").rglob("*.py"))]
    code_hash = stable_hash({str(path.resolve().relative_to(project.resolve())):
                             path.read_text(encoding="utf-8")
        for path in source_paths})
    config = {"split_query_source": args.splits, "language": args.lang, "model_identifier": model,
              "repair_strategies": args.repair_strategies, "max_steps": args.max_steps,
              "oracle_translation": True, "sampling_settings": settings,
              "seed": args.seed, "seed_scope": "Python and NumPy only",
              "git_commit": commit, "git_diff_hash": stable_hash(diff), "implementation_hash": code_hash}
    if args.split_manifest:
        config["partition"] = args.partition
        config["split_manifest_hash"] = stable_hash(load_manifest(args.split_manifest))
    directory = run_comparison(
        {uid: data[uid] for uid in selected}, run_id=run_id, output_root=args.output_dir,
        config=config, prepare_initial_state=prepare, runtime_factory=runtime,
        skip_unavailable=args.skip_unavailable, resume=args.resume, retry_failed=args.retry_failed, raw_only=True,
    )
    print(f"Comparison outputs: {directory}")



if __name__ == "__main__":
    main()
