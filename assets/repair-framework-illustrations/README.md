# Repair framework illustrations

Hand-drawn explainer images of the project's pipeline and shared repair loop, in the
[Ian Xiaohei](https://github.com/helloianneo/ian-xiaohei-illustrations) style (MIT, by Ian).
All are 1280x720 (16:9).

| Image | What it shows | Code |
|---|---|---|
| `01-codebase-flow.png` | Request + constraints → sandbox data → draft plan → repair loop (R0–R4) → logs → matrix M, which guides R4 | `llm_modulo.py`, `shared_repair_loop.py`, `scripts/build_regression_matrix.py` |
| `02-same-start-plan.png` | One draft plan is made once per query and copied to every strategy, so only the repair differs | `run_experiments.py` (`prepare_initial_repair_state`) |
| `03-loop-core.png` | One round: failed checks → `repair()` → verify the candidate → `accept()`? If not, keep the old plan | `run_repair_loop` |
| `04-phase-schedule.png` | Personal constraints first (up to 5 rounds), then commonsense; back to personal if one breaks; stop when the plan passes | `run_repair_loop` phase schedule |
| `05-verifier-triage.png` | Personal results are True / False / None (unknown). Only real violations reach the repair prompt; technical errors are kept separate | `shared_verifier.py::verify_plan` |
| `06-regression-matrix.png` | Fixing constraint i breaks j ("newly violated"), which is tallied into M[i→j] | `compare_constraint_results`, `regression_matrix.py` |
| `07-editing-scope.png` | How much each strategy may edit: R1 one slot, R3 widens slot → day → plan, R0 everything, R2 rolls back | `repair_strategies/r0.py`–`r3.py` |

How they were made:
- **01** was made with GPT-Image-2 via OpenRouter, from `prompts/01-codebase-flow.txt`.
- **02–07** were made locally with Z-Image-Turbo (Apache-2.0; Q5_K_M GGUF from
  `unsloth/Z-Image-Turbo-GGUF`), from `prompts/local/*.txt` using `prompts/local/local_gen.py`.
  Settings: 9 steps, guidance 0. Seeds used: 02 → 2, 03 → 2, 04 → 6, 05 → 1, 06 → 1, 07 → 4.
