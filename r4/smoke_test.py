"""Exercise both R4 modes with synthetic evidence and no network/model calls."""

import argparse
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

R4_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = R4_ROOT.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
for root in (WORKSPACE_ROOT, PROJECT_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from r4.run_r4 import add_run_arguments, execute
from r4.safety import train_uids
from chinatravel.agent.model_usage import ModelUsage
from chinatravel.agent.nesy_verifier.initial_state import InitialRepairState
from chinatravel.agent.nesy_verifier import shared_repair_loop as loop
from chinatravel.evaluation.repair_attempt import RepairAttemptRecord
from scripts.build_regression_matrix import main as build_regression_matrix
from scripts.build_repair_summary import build_repair_summary


class MockModel:
    def __init__(self):
        self.usage = ModelUsage()

    def usage_snapshot(self):
        return vars(self.usage).copy()

    def __call__(self, messages, one_line=False):
        self.usage.model_calls += 1
        self.usage.observe({"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})
        return '"activities":[{"position":"Synthetic site","type":"attraction","cost":90}]}]'


def synthetic_report(plan):
    return {
        "personal_constraints": [False, True], "passed": False,
        "error_info": ["Personal constraint 1 failed: synthetic budget", "Synthetic commonsense issue"],
        "commonsense_errors": ["Synthetic commonsense issue"], "schema_errors": [],
        "translated_plan": deepcopy(plan),
    }


def run_smoke(output, *, include_r1=False):
    """Five synthetic queries per mode; all artifacts are labeled synthetic."""
    # Preload NumPy before patch.dict snapshots sys.modules. Otherwise restoring
    # the first mock runtime would unload it and trigger a second native import.
    __import__("numpy")
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Choose a new smoke-test output directory")
    output.mkdir(parents=True)
    (output / "SYNTHETIC_ONLY.txt").write_text(
        "Mock LLM/verifier and fabricated evidence. Never use these matrices for research results.\n",
        encoding="utf-8",
    )
    # Use only the train UID allowlist, never query payloads or the test split.
    uids = sorted(train_uids())[:5]
    labels = ("R0", "R1", "R2", "R3") if include_r1 else ("R0", "R2", "R3")
    constraints = ["total=0\nfor activity in allactivities(plan):\n  total+=activity_cost(activity)\nresult=total<=50",
                   "result=day_count(plan)==1"]
    for label in labels:
        directory = output / "synthetic_sources" / label
        directory.mkdir(parents=True)
        record = RepairAttemptRecord(
            step=1, repair_strategy=label, accepted=True, query_uid=uids[0],
            constraint_descriptors=[{"constraint_index": i, "hard_logic_py": dsl}
                                    for i, dsl in enumerate(constraints, 1)],
            target_constraint_indices=[1], before_personal_constraints=[False, True],
            after_personal_constraints=[True, False], fixed=[1], newly_violated=[2],
            target_constraint_labels=[], still_failed=[], still_passed=[], unknown=[],
            candidate_plan=[], accepted_plan_after=[], repair_metadata={"synthetic": True},
        )
        attempts_path = directory / "attempts.jsonl"
        attempts_path.write_text(json.dumps(record.to_dict()) + "\n", encoding="utf-8")
        build_regression_matrix(["--input", str(attempts_path), "--repair-strategy", label,
                                 "--output-dir", str(directory)])

    queries = {uid: {"uid": uid, "people_number": 1, "start_city": "Synthetic A",
                     "target_city": "Synthetic B", "nature_language": "Synthetic pipeline test",
                     "hard_logic_py": constraints} for uid in uids}
    initial_calls = []

    def prepare(problem):
        initial_calls.append(problem["uid"])
        plan = [{"day": 1, "activities": [{"position": "Synthetic site", "type": "attraction", "cost": 100}]}]
        context = {key: "" for key in ("go_train_info", "go_flight_info", "back_train_info", "back_flight_info",
                                      "attraction_info", "restaurant_info", "accommodation_info", "innercity_transport_info")}
        return InitialRepairState(problem["uid"], problem, plan, context,
                                  synthetic_report({"itinerary": plan}), generation_metadata={
                                      "input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                                      "model_calls": 1, "failed_model_calls": 0,
                                  })

    results = {}
    for mode in ("individual", "combined"):
        parser = argparse.ArgumentParser()
        add_run_arguments(parser)
        cli = ["--mode", mode, "--output-dir", str(output), "--run-id", mode]
        if not include_r1:
            cli.append("--allow-missing-r1")
        for label in labels:
            cli.extend(["--matrix-dir", f"{label}={output / 'synthetic_sources' / label}"])
        args = parser.parse_args(cli)
        args.synthetic = True
        # Exercise the actual public R4 -> run_experiments -> comparison ->
        # shared-loop path. Replace only external runtime/data dependencies.
        model_module = SimpleNamespace(
            init_llm=lambda name: MockModel(), resolve_llm_name=lambda name: name,
            init_agent=lambda config: SimpleNamespace(
                backbone_llm=config["backbone_llm"], translate_innercity_transport=None,
                prepare_initial_repair_state=prepare),
        )
        fake_modules = {"chinatravel.agent.load_model": model_module,
                        "chinatravel.environment.world_env": SimpleNamespace(WorldEnv=lambda **kw: object())}
        with patch.dict(sys.modules, fake_modules), \
             patch("chinatravel.data.load_datasets.load_query", return_value=(list(queries), deepcopy(queries))), \
             patch.object(loop, "verify_plan", side_effect=lambda problem, plan, **kw: synthetic_report(plan)), \
             patch("subprocess.check_output", return_value="synthetic"):
            run_dir = execute(args)
        metadata = json.loads((run_dir / "r4_run_metadata.json").read_text(encoding="utf-8"))
        selections = json.loads((run_dir / "r4_selection_and_costs.json").read_text(encoding="utf-8"))
        build_repair_summary(run_dir)
        for name in metadata["matrices"]:
            build_regression_matrix(["--input", str(run_dir / "attempts.jsonl"), "--repair-strategy", name,
                                     "--output-dir", str(run_dir / "regression_matrix" / name)])
        assert len(selections) == 5
        for item in selections:
            assert item["repair_attempt_count_all_trials"] == 6, item
            assert item["costs"]["all_trials_model_calls"] == 6, item
            assert item["costs"]["including_initial_model_calls"] == 7, item
            assert item["costs"]["all_trials_input_tokens_delta"] == 60, item
            assert item["costs"]["including_initial_input_tokens"] == 160, item
            assert item["costs"]["all_trials_verification_count"] == 6, item
            assert all(status == "completed" for status in item["trial_statuses"].values()), item
        results[mode] = {"query_count": len(selections), "repairs": 30,
                         "repair_budgets": metadata["repair_budgets"], "run_dir": str(run_dir)}
    assert len(initial_calls) == 10  # Five once per mode, independent of trial count.
    (output / "smoke_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "experiments" / "r4_smoke" / datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    parser.add_argument("--include-r1", action="store_true", help="Fabricate R1 as well, to check all four input paths")
    args = parser.parse_args(argv)
    print(json.dumps(run_smoke(args.output_dir, include_r1=args.include_r1), indent=2))


if __name__ == "__main__":
    main()
