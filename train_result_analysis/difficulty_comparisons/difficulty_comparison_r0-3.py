"""Plans passing all PC and repair cost for R0-R3 on Easy / Medium / Human (subset_train, 20 per group).

Same layout as test_result_analysis/difficulty_comparison_graphs/logical_macro_with_cost.png:
bars of final plans passing all PC (= ChinaTravel logical macro) on top, and avg tokens and
avg repair time per query directly under each bar.

Data:
  R0, R2, R3  train_result_analysis/merged/table1_pc.csv, table3_repair_process.csv, table4_eval_exp.csv
  R1          experiments/subset_train-r1: attempts.jsonl (tokens, time) and
              benchmark_eval/R1-*/logical_py.csv (plans passing all PC). The run kept only
              attempts.jsonl, so the "score" step reconstructs its queries/ and benchmark_eval/.

How the "score" step reconstructs R1 train (offline, no model calls):
  1. Reference queries: from experiments/subset_train-r0 (the 60 problems are identical in
     every train run).
  2. Final plan: accepted_plan_after of each query's last attempt (R1 accepts every
     candidate), translated with the loop's own LLMModuloAgent.translate_innercity_transport
     and wrapped as verify_plan does. A translation error keeps the partly translated copy,
     as verify_plan does.
  3. It writes, in the layout of the other train runs:
       queries/<uid>-<hash>/reference/query.json   (copied from subset_train-r0)
       queries/<uid>-<hash>/initial_state.json     (problem only; "reconstructed" key)
       queries/<uid>-<hash>/R1-<hash>.json         (final_verification.translated_plan only;
                                                    "reconstructed_from" key; no execution_status,
                                                    so analyze_repair_strategies.py does not count
                                                    it as a persisted terminal status; none for a
                                                    query with no plan)
       reconstructed_checkpoints.json              (method and one note per query)
     and scores the run in place with evaluate_repair_run (the same pipeline as every other
     run), which writes benchmark_eval/R1-<hash>/. run_manifest.json and attempts.jsonl are
     not changed. The step stops, and changes nothing, if a query already has a checkpoint
     that is not marked as reconstructed.
  Tokens and time: sums of total_tokens_delta and repair_time_seconds over each query's
  attempts (0 for a query with no attempts), as in table 3.
  Checked with "score --validate": the same rebuild of experiments/subset_test-r1 (in a temp
  folder) gives 30/30 identical translated plans, identical logical_py.csv and commonsense.csv,
  and the same plans-passing-all-PC, token and time values as the merged test tables.
  Known gap: h20241029143754236194 (Human) has no attempts (its initial plan passed the loop
  verifier), and its initial plan was not saved. It is scored as an empty plan (fail), so R1
  Human may be 1 plan (5 pp) too low.

Output next to this script (train_result_analysis/difficulty_comparisons/):
  difficulty_comparison_r0-3.png

Usage (from the repository root):
  .venv/Scripts/python.exe train_result_analysis/difficulty_comparisons/difficulty_comparison_r0-3.py score [--validate]
  python train_result_analysis/difficulty_comparisons/difficulty_comparison_r0-3.py plot     (needs matplotlib)
"score" is needed only once (or after a change to the R1 run). The project .venv has no
matplotlib and the system Python has no project packages, so the two steps can use
different interpreters.
"""
import argparse
import collections
import csv
import json
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent  ## train_result_analysis/difficulty_comparisons
REPO = HERE.parents[1]
OUT = HERE  ## the PNG goes next to this script
MERGED = REPO / "train_result_analysis" / "merged"
R1_RUN = REPO / "experiments" / "subset_train-r1"
REFS_RUN = REPO / "experiments" / "subset_train-r0"
GROUPS = ["Easy", "Medium", "Human"]
METHODS = ["R0", "R1", "R2", "R3"]
MACRO = "Logical macro (%)"
TOKENS = "[per query] Avg tokens spent per query (queries with complete token data)"
TIME = "[per query] Avg repair time per query (s)"
METHOD_NOTE = ("Reconstructed offline from attempts.jsonl by train_result_analysis/difficulty_comparisons/"
               "difficulty_comparison_r0-3.py (score step): final plan = accepted_plan_after of the last "
               "attempt, translated with LLMModuloAgent.translate_innercity_transport; reference queries "
               "from subset_train-r0. Not a checkpoint written by the repair loop.")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


## ---------- shared: R1 values per group (standard library only) ----------

def group_metrics(attempts_run, scored_run):
    """Per group: plans passing all PC (count, %), avg tokens and avg repair time per query."""
    origin = load_json(REPO / "chinatravel/evaluation/splits/subset_origin.json")["origin"]
    uids = load_json(Path(attempts_run) / "run_manifest.json")["query_uids"]
    tokens, time = collections.Counter(), collections.Counter()
    for line in open(Path(attempts_run) / "attempts.jsonl", encoding="utf-8"):
        row = json.loads(line)
        tokens[row["query_uid"]] += row["total_tokens_delta"] or 0
        time[row["query_uid"]] += row["repair_time_seconds"] or 0
    found = list((Path(scored_run) / "benchmark_eval").glob("*/logical_py.csv"))
    if len(found) != 1:
        sys.exit(f"{scored_run}: expected one benchmark_eval/*/logical_py.csv, found {len(found)}. "
                 "Run the score step first (see the docstring).")
    passed = {}
    with open(found[0], encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            cells = [v for k, v in row.items() if k.startswith("logic_py_") and v not in ("", None)]
            passed[row["data_id"]] = all(float(v) == 1 for v in cells)
    result = {}
    for group in GROUPS + ["All"]:
        members = [u for u in uids if group == "All" or origin[u] == group.lower()]
        result[group] = dict(n=len(members), all_pc=sum(passed[u] for u in members),
                             pct=round(100 * sum(passed[u] for u in members) / len(members), 2),
                             tokens=round(sum(tokens[u] for u in members) / len(members)),
                             time=round(sum(time[u] for u in members) / len(members), 1))
    return result


## ---------- score step (needs the project packages: run with .venv) ----------

def rebuild_and_score(src, refs, out, initial_from=None):
    """Write reconstructed queries/ files for the run src into out (src itself, or a temp
    folder for validation) and score out with evaluate_repair_run."""
    from chinatravel.agent.nesy_verifier.llm_modulo import LLMModuloAgent
    from chinatravel.environment.world_env import WorldEnv
    from chinatravel.evaluation.export_final_plans import evaluate_repair_run
    from chinatravel.evaluation.repair_comparison import _component, _save

    src, refs, out = Path(src), Path(refs), Path(out)
    in_place = src.resolve() == out.resolve()

    def query_dir(run, uid):
        return Path(run) / "queries" / _component(uid)

    class Translator:  ## only the attributes translate_innercity_transport uses
        def __init__(self, lang):
            self.env, self.problem = WorldEnv(lang=lang), None

        def __call__(self, itinerary, problem):
            self.problem = problem
            try:  ## in place, as verify_plan does; on an error the partly translated copy stays
                LLMModuloAgent.translate_innercity_transport(self, itinerary, problem)
                return None
            except Exception as exc:
                return f"{type(exc).__name__}: {exc}"

    manifest = load_json(src / "run_manifest.json")
    strategy = manifest["repair_strategies_requested"][0]
    checkpoint_name = _component(strategy) + ".json"
    if in_place:  ## never replace files written by the repair loop
        for uid in manifest["query_uids"]:
            for path in (query_dir(out, uid) / checkpoint_name, query_dir(out, uid) / "initial_state.json"):
                if path.exists() and not ({"reconstructed", "reconstructed_from"} & set(load_json(path))):
                    sys.exit(f"{path} is a real file of the run, not a reconstruction: nothing changed.")
    rows = collections.defaultdict(list)
    for line in open(src / "attempts.jsonl", encoding="utf-8"):
        row = json.loads(line)
        rows[row["query_uid"]].append(row)
    translate, notes, statuses = Translator(manifest["language"]), {}, {}
    for uid in manifest["query_uids"]:
        problem = load_json(query_dir(refs, uid) / "initial_state.json")["state"]["problem"]
        directory = query_dir(out, uid)
        reference = query_dir(refs, uid) / "reference" / "query.json"
        if reference.exists():
            (directory / "reference").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(reference, directory / "reference" / "query.json")
        _save(directory / "initial_state.json",
              {"query_uid": uid, "reconstructed": METHOD_NOTE, "state": {"problem": problem}})
        attempts = sorted(rows.get(uid, []), key=lambda r: r["step"])
        if attempts:
            itinerary, status = attempts[-1]["accepted_plan_after"], "completed"
            notes[uid] = f"final plan = accepted_plan_after of attempt step {attempts[-1]['step']}"
        elif initial_from:
            itinerary = load_json(query_dir(initial_from, uid) / "initial_state.json")["state"]["raw_initial_plan"]
            status = "completed"
            notes[uid] = "no attempts: initial plan from --initial-from"
        else:
            itinerary, status = None, "initial_plan_missing"
            notes[uid] = ("no attempts (initial plan passed the loop verifier) and the initial plan was "
                          "not saved: scored as an empty plan (fail)")
        plan = None
        if isinstance(itinerary, list) and itinerary:
            plan = {"people_number": problem["people_number"], "start_city": problem["start_city"],
                    "target_city": problem["target_city"], "itinerary": deepcopy(itinerary)}
            error = translate(plan["itinerary"], problem)
            if error:
                notes[uid] += f"; translation error, partly translated plan kept as in verify_plan ({error})"
        statuses[uid] = status
        checkpoint = directory / checkpoint_name
        if plan is None:  ## no plan: no checkpoint (the evaluator scores it as an empty plan anyway)
            checkpoint.unlink(missing_ok=True)
            continue
        ## No execution_status / stop_reason / verification results: the loop did not persist
        ## them, and analyze_repair_strategies.py would report them as "directly persisted".
        _save(checkpoint, {"query_uid": uid, "repair_strategy": strategy, "reconstructed_from": "attempts.jsonl",
                           "final_verification": {"translated_plan": plan}})
    if not in_place:
        _save(out / "run_manifest.json", manifest)
    _save(out / "reconstructed_checkpoints.json", {"method": METHOD_NOTE, "queries": notes})
    evaluate_repair_run(out)
    ## Without execution_status the evaluator lists every query as "initial_generation_failed";
    ## replace that with the reconstructed status, marked as such.
    [population_path] = (out / "benchmark_eval").glob("*/evaluation_population.json")
    population = load_json(population_path)
    population["statuses"] = {u: "reconstructed_" + s for u, s in statuses.items()}
    population["statuses_source"] = "reconstructed from attempts.jsonl (not persisted by the repair loop)"
    _save(population_path, population)
    return manifest, strategy


def validate(tmp):
    """Rebuild R1 test (which has real checkpoints) in tmp and compare with its real files and tables."""
    from chinatravel.evaluation.repair_comparison import pair_path
    run = REPO / "experiments" / "subset_test-r1"
    manifest, strategy = rebuild_and_score(run, run, tmp, initial_from=run)
    same = sum(json.dumps(load_json(pair_path(run, u, strategy))["final_verification"]["translated_plan"],
                          sort_keys=True)
               == json.dumps(load_json(pair_path(tmp, u, strategy))["final_verification"]["translated_plan"],
                             sort_keys=True)
               for u in manifest["query_uids"])
    print(f"validate: rebuilt plans identical to the real ones: {same}/{len(manifest['query_uids'])}")
    for name in ("logical_py.csv", "commonsense.csv"):
        [real] = (run / "benchmark_eval").glob(f"*/{name}")
        [new] = (Path(tmp) / "benchmark_eval").glob(f"*/{name}")
        print(f"validate: {name} identical:", real.read_text(encoding="utf-8") == new.read_text(encoding="utf-8"))
    tables = {n: load_table(REPO / "test_result_analysis/merged", n)
              for n in ("table3_repair_process.csv", "table4_eval_exp.csv")}
    result = group_metrics(run, tmp)
    for g in GROUPS + ["All"]:
        expected = (table_value(tables["table4_eval_exp.csv"], MACRO, g, "R1"),
                    table_value(tables["table3_repair_process.csv"], TOKENS, g, "R1"),
                    table_value(tables["table3_repair_process.csv"], TIME, g, "R1"))
        got = (result[g]["pct"], result[g]["tokens"], result[g]["time"])
        print(f"validate: {g}: {'OK' if all(abs(a - b) < 0.01 for a, b in zip(got, expected)) else 'DIFFERS'}"
              f" (rebuilt {got}, table {expected})")


def score(args):
    os.chdir(REPO)  ## the sandbox database and eval_exp are found from the repository root
    sys.path.insert(0, str(REPO))
    if args.validate:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:  ## the validation rebuild is not kept
            validate(Path(tmp))
    rebuild_and_score(R1_RUN, REFS_RUN, R1_RUN)
    print(json.dumps(group_metrics(R1_RUN, R1_RUN), indent=2))


## ---------- plot step (needs matplotlib) ----------

def load_table(folder, name):
    with open(Path(folder) / name, encoding="utf-8") as stream:
        return {row["metric"]: row for row in csv.DictReader(stream)}


def table_value(table, metric, group, method):
    if metric not in table:  ## a unique prefix is accepted (the table 4 names are long)
        matches = [m for m in table if m.startswith(metric)]
        assert len(matches) == 1, (metric, matches)
        metric = matches[0]
    return float(table[metric][f"{group} {method}"])


def plot(_args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    ## Same colours as the test plots (dataviz palette validator: all checks pass).
    color = {"R0": "#2a78d6", "R1": "#1baf7a", "R2": "#eda100", "R3": "#e87ba4"}
    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9"
    plt.rcParams.update({
        "figure.facecolor": surface, "axes.facecolor": surface, "savefig.facecolor": surface,
        "axes.edgecolor": grid, "axes.labelcolor": ink2, "xtick.color": ink2, "ytick.color": ink2,
        "text.color": ink, "axes.grid": True, "grid.color": grid, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
        "axes.titleweight": "bold", "axes.titlesize": 11, "axes.axisbelow": True,
    })
    r1 = group_metrics(R1_RUN, R1_RUN)
    t1, t3, t4 = (load_table(MERGED, n) for n in ("table1_pc.csv", "table3_repair_process.csv", "table4_eval_exp.csv"))
    n = int(table_value(t1, "Queries (n)", "Easy", "R0"))

    def value(table, metric, group, method):  ## R1 from its run folder, the others from the merged tables
        if method == "R1":
            return r1[group][{MACRO: "pct", TOKENS: "tokens", TIME: "time"}[metric]]
        return table_value(table, metric, group, method)

    for g in GROUPS:  ## the bars must equal table 1's count of plans with 0 failed PC, as a %
        for m in METHODS:
            if m != "R1":
                assert abs(value(t4, MACRO, g, m) - 100 * table_value(t1, "Final plans with 0 failed PC", g, m) / n) < 0.01

    width = 0.8 / len(METHODS)
    fig, axes = plt.subplots(3, 1, figsize=(10, 9.4), sharex=True, height_ratios=(1.3, 1, 1))
    for i, m in enumerate(METHODS):
        x = np.arange(3) + (i - (len(METHODS) - 1) / 2) * width
        macro = [value(t4, MACRO, g, m) for g in GROUPS]
        bars = axes[0].bar(x, macro, width=width - 0.02, color=color[m])
        for bar, v in zip(bars, macro):
            axes[0].annotate(f"{v:.0f}", (bar.get_x() + bar.get_width() / 2, v), xytext=(0, 2),
                             textcoords="offset points", ha="center", fontsize=10, color=ink2)
        for ax, metric, scale in ((axes[1], TOKENS, 1000), (axes[2], TIME, 1)):
            values = [value(t3, metric, g, m) / scale for g in GROUPS]
            ax.vlines(x, 0, values, color=grid, lw=1.2, zorder=1)  ## thin stem, ties the point to the bar
            ax.scatter(x, values, s=90, color=color[m], edgecolor=surface, linewidth=1.5, zorder=3)
    axes[0].set_ylim(0, 100)
    axes[0].set_ylabel("Final plans passing\nall PC (%)")
    axes[1].set_ylim(0, 260)
    axes[1].set_ylabel("Avg tokens per query\n(thousands)")
    axes[2].set_ylim(0, 260)
    axes[2].set_ylabel("Avg repair time\nper query (s)")
    for ax in axes:
        ax.grid(axis="x", visible=False)
        for x in (0.5, 1.5):  ## separate the difficulty groups across all three panels
            ax.axvline(x, color=grid, lw=1)
    axes[2].set_xticks(range(3), GROUPS)
    axes[2].tick_params(axis="x", labelsize=11)
    handles = [plt.Rectangle((0, 0), 1, 1, color=color[m]) for m in METHODS]
    fig.legend(handles, METHODS, frameon=False, ncols=len(METHODS), loc="upper right", bbox_to_anchor=(0.99, 0.955))
    fig.suptitle(f"TRAIN: plans passing all PC and repair cost by difficulty (n={n} per group)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    path = OUT / "difficulty_comparison_r0-3.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    steps = parser.add_subparsers(dest="step", required=True)
    score_parser = steps.add_parser("score", help="reconstruct and score R1 train in place (project .venv)")
    score_parser.add_argument("--validate", action="store_true", help="first check the method on R1 test")
    score_parser.set_defaults(run=score)
    steps.add_parser("plot", help="draw the figure (needs matplotlib)").set_defaults(run=plot)
    args = parser.parse_args()
    args.run(args)
