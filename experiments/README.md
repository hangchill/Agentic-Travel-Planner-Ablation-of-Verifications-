# Experiments — shared results

This folder holds the **committed** results of our repair-strategy experiments, so
everyone on the team sees the same outputs and can compare strategies directly.

## Where results go (and why not `results/` or `cache/`)

- `experiments/` (this folder) is **tracked by git** — results here are shared.
- `results/` and `cache/` are **git-ignored** — the original ChinaTravel code writes
  there, but those outputs never reach the team. Don't rely on them for sharing.

So: always put results you want to share in `experiments/`, using the runner below
(which does this for you).

## How to run an experiment

Use `run_experiment.py` (at the repo root). It runs one strategy over one split and
saves one JSON per query into a standard folder. It is **resume-safe** — a query that
already has a result is skipped, so re-running costs nothing extra.

```bash
# R0 on the shared 5-query pilot set (quick, ~$0.20 on DeepSeek V3)
python run_experiment.py --strategy R0 --split pilot5

# Your strategy on the same pilot set, to compare against R0
python run_experiment.py --strategy R1 --split pilot5

# Cheap trial of just the first 2 queries
python run_experiment.py --strategy R1 --split pilot5 --limit 2

# Scale up to the training subset once the pilot looks right
python run_experiment.py --strategy R1 --split subset_train
```

Defaults (do not change these for the shared comparison): **DeepSeek V3**
(`deepseek/deepseek-chat`), **repair budget 5** (`--refine-steps 5`), **English**
(`--lang en`). Keeping them identical across R0–R4 is what makes the comparison fair.

## Folder naming

Results are saved to:

```
experiments/<strategy>_<model>_<split>/<uid>.json
```

For example `experiments/r0_deepseek-chat_pilot5/` holds R0's results on `pilot5`.
Your R1 run on `pilot5` will create `experiments/r1_deepseek-chat_pilot5/` right
next to it — so comparing strategies is just comparing sibling folders.

## Recommended workflow for R1–R4

1. Implement your strategy (`chinatravel/agent/nesy_verifier/repair_strategies/rX.py`)
   and register it (see the main `README.md` / `framework_r0.ipynb`).
2. `python run_experiment.py --strategy RX --split pilot5 --limit 2` — cheap sanity check.
3. `python run_experiment.py --strategy RX --split pilot5` — full pilot (5 queries).
4. Commit your `experiments/rX_deepseek-chat_pilot5/` folder so the team gets it.
5. Compare against R0 in `experiments/r0_deepseek-chat_pilot5/`.
6. When ready, run on `--split subset_train` (69 queries) for the fuller results.

The split definitions live in `chinatravel/evaluation/default_splits/` and each
query's difficulty is in `chinatravel/evaluation/splits/*_origin.json`.

## What's here

| Folder | What it is |
| --- | --- |
| `r0_deepseek-chat_pilot5/` | R0 baseline on the shared pilot set (DeepSeek V3, language-aware verifier). Compare your strategy against this. |
| `_archive_gpt4.1/` | Old GPT-4.1 sample runs, kept for reference only. Predate the language fix, so their error counts are inflated — not the current baseline. |
