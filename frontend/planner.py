"""Adapter from the Streamlit form to the existing verified repair pipeline."""

from copy import deepcopy
import os
from pathlib import Path
import sys
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def execute_trip(
    request: dict[str, Any],
    run_dir: Path,
    history_callback: Callable[[list[dict[str, Any]]], None],
) -> dict[str, Any]:
    """Generate, verify, and repair one trip using the project's shared loop."""
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from chinatravel.agent.load_model import init_agent, init_llm
    from chinatravel.agent.nesy_verifier.repair_strategies import (
        create_repair_strategy,
    )
    from chinatravel.agent.nesy_verifier.shared_repair_loop import run_repair_loop
    from chinatravel.environment.world_env import WorldEnv

    uid = str(request["run_id"])
    strategy_name = str(request["strategy"])
    max_steps = int(request["max_steps"])
    model_name = str(request["model"])
    strategy = None
    if strategy_name == "R4":
        matrix_value = request.get("matrix_path") or os.getenv("CHINATRAVEL_R4_MATRIX")
        if not matrix_value:
            raise ValueError("R4 requires a pooled empirical matrix path.")
        from r4.safety import train_uids, validate_final_matrix

        matrix_path = Path(matrix_value).expanduser().resolve()
        validate_final_matrix(matrix_path, train_uids("subset_train"))
        previous_matrix_path = os.environ.get("CHINATRAVEL_R4_MATRIX")
        os.environ["CHINATRAVEL_R4_MATRIX"] = str(matrix_path)
        try:
            strategy = create_repair_strategy(strategy_name)
        finally:
            if previous_matrix_path is None:
                os.environ.pop("CHINATRAVEL_R4_MATRIX", None)
            else:
                os.environ["CHINATRAVEL_R4_MATRIX"] = previous_matrix_path

    problem = {
        "uid": uid,
        "nature_language": (
            f"Plan a {request['days']}-day trip from {request['start_city']} "
            f"to {request['target_city']} for {request['people_number']} "
            f"traveller(s). User requirements: {request['prompt']}"
        ),
        "start_city": request["start_city"],
        "target_city": request["target_city"],
        "people_number": int(request["people_number"]),
        "hard_logic_py": [],
        "hard_logic_nl": [],
    }

    runtime_dir = run_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    llm = init_llm(model_name)
    agent = init_agent({
        "method": "LLM-modulo",
        "env": WorldEnv(lang="en"),
        "backbone_llm": llm,
        "model": llm,
        "cache_dir": str(runtime_dir / "cache"),
        "log_dir": str(runtime_dir / "logs"),
        "debug": True,
        "refine_steps": max_steps,
        "max_steps": max_steps,
        "repair_strategy": strategy_name,
        "lang": "en",
    })

    previous_stdout, previous_stderr = sys.stdout, sys.stderr
    try:
        state = agent.prepare_initial_repair_state(problem, prob_idx=uid)
        if strategy is None:
            strategy = create_repair_strategy(strategy_name)
        result = run_repair_loop(
            problem=problem,
            raw_plan=deepcopy(state.raw_initial_plan),
            strategy=strategy,
            context=deepcopy(state.repair_context),
            llm=agent.backbone_llm,
            translate_fn=agent.translate_innercity_transport,
            max_steps=max_steps,
            initial_verification=deepcopy(state.initial_verification),
            history_callback=history_callback,
        )
    finally:
        sys.stdout, sys.stderr = previous_stdout, previous_stderr

    verification = result["verification"]
    itinerary = deepcopy(verification.get("translated_plan", result["raw_plan"]))
    return {
        "itinerary": itinerary,
        "verification": verification,
        "generation_metadata": state.generation_metadata,
        "repair_history": result["history"],
    }
