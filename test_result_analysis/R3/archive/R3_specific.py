"""Build the R3 editing-scope tables (slot / day / plan), split by difficulty group.

Writes to <output-dir> (default test_result_analysis/R3/, the folder of this script):
  table5_scope.csv              metric, Easy, Medium, Human, All, source
  table6_scope_fulfillment.csv  PC / CS fulfillment before repair and after the slot, day and
                                plan rounds, and what each stage's rounds fixed and broke
  scope_per_query.csv           every per-query value the tables are built from

Metrics (table 5):
  - highest scope reached per query, and number of escalations per query
  - % of queries reaching slot / day / plan scope
  - scope at which the successful repair occurred, and % of successful repairs at each scope
  - round-wise: % of rounds at each scope that improved the plan

Definitions:
  - Scope: each round's repair_attempt.editable_scope in the checkpoint's repair_history
    (slot < day < plan). R3 widens on a fixed schedule (rounds 1-2 slot, 3-4 day, 5+ plan),
    so its scope depends only on how many rounds a query used.
  - Escalation: a round whose scope is wider than the round before it.
  - Successful repair: the first accepted round after which the loop verifier passed
    (verification.passed); the loop stops there.
  - Improving round: an accepted round with more personal constraints (PC) True or fewer
    commonsense (CS) errors than the plan in place before it, and no PC True -> False and no
    increase in CS errors (loop verifier).
  - Stage (table 6): the plan in place before repair, and after the last round of each scope.
    A query that stopped earlier (it passed) keeps its last plan for the later stages, so
    "level" rows always cover every query. "[<scope> rounds]" rows cover only the queries
    with a round at that scope and compare the plan before and after that scope's rounds.
    Benchmark rows score each stage's plan with the functions eval_exp.py uses (as in
    tables 1-2); loop rows show what the R3 loop itself saw.

Caveat: scope and round number are the same thing in R3, and the loop's phase schedule
(personal rounds first, then commonsense) puts the only commonsense round of queries with
failing PCs at round 6 (plan scope). The plan-round CS gain therefore mixes scope with
"first commonsense round".

The row "also passes the benchmark" reads all_pass_final from <output-dir>/per_query.csv
(written by test_result_analysis/build_test_result_tables.py). Run that script first; without
the file the row is empty.

Reads only saved run files (no model calls, no changes to the run folder).

Usage (from the repository root):
  python test_result_analysis/R3/R3_specific.py
  python test_result_analysis/R3/R3_specific.py --run experiments/subset_test-r3 \
      --output-dir test_result_analysis/R3
"""
import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for path in (REPO, HERE.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import scripts.result_analysis.build_test_result_tables as builder  # noqa: E402  (test_result_analysis/build_test_result_tables.py)
from chinatravel.evaluation.repair_comparison import pair_path  # noqa: E402

## score_plans reads builder.REPO to find output_schema.json; set it to the repository root
## so that scoring does not depend on where the builder file is.
builder.REPO = REPO
TABLE_COLUMNS = builder.TABLE_COLUMNS
benchmark_dir, load_json, mean = builder.benchmark_dir, builder.load_json, builder.mean
metric_row, plan_or_empty, score_plans = builder.metric_row, builder.plan_or_empty, builder.score_plans
true_count, write_csv = builder.true_count, builder.write_csv

SCOPES = ("slot", "day", "plan")
STAGES = ("initial", *SCOPES)
STAGE_NAMES = {"initial": "before repair", "slot": "after slot rounds", "day": "after day rounds",
               "plan": "after plan rounds"}
SRC_SCOPE = "checkpoint repair_history: repair_attempt.editable_scope of each round"
SRC_SUCCESS = (SRC_SCOPE + "; success = first accepted round whose loop verification passed "
               "(the loop then stops)")
SRC_IMPROVE = (SRC_SCOPE + "; improving round = accepted, and (more PC True or fewer CS errors), and no PC "
               "True -> False and no more CS errors than the plan in place before it (loop verifier)")
SRC_STAGE = ("plan in place after the last round of each scope (checkpoint repair_history; last accepted "
             "verification.translated_plan); a query that stopped earlier keeps its last plan")
SRC_STAGE_BENCH = "benchmark (eval_exp functions, same as tables 1-2) on the " + SRC_STAGE
SRC_STAGE_LOOP = "loop verifier (verification.personal_constraints / commonsense_errors) of the " + SRC_STAGE


def pct(part, whole):
    return round(100 * part / whole, 1) if whole else ""


## ---------- per-query scope data (table 5) ----------

def improved(before, after):
    """True when a round fixed something and broke nothing (loop verifier)."""
    pc_before, pc_after = before.get("personal_constraints") or [], after.get("personal_constraints") or []
    cs_before, cs_after = len(before.get("commonsense_errors") or []), len(after.get("commonsense_errors") or [])
    regressed = any(b is True and a is False for b, a in zip(pc_before, pc_after)) or cs_after > cs_before
    gained = true_count(pc_after) > true_count(pc_before) or cs_after < cs_before
    return gained and not regressed


def scope_data(checkpoint):
    """Scope of each round: highest scope, escalations, and the scope where repair succeeded."""
    history = checkpoint.get("repair_history") or []
    current = (history[0].get("verification") if history else None) or checkpoint.get("initial_verification") or {}
    scopes, success_step, success_scope = [], None, None
    rounds_at = dict.fromkeys(SCOPES, 0)
    improved_at = dict.fromkeys(SCOPES, 0)
    for entry in history[1:]:
        attempt = entry.get("repair_attempt") or {}
        scope = attempt.get("editable_scope")
        verification = entry.get("verification") or {}
        accepted = bool(entry.get("accepted"))
        if scope in SCOPES:
            scopes.append(scope)
            rounds_at[scope] += 1
            improved_at[scope] += accepted and improved(current, verification)
        if accepted:
            current = verification
            if success_step is None and verification.get("passed") is True:
                success_step, success_scope = entry.get("step", attempt.get("step")), scope
    levels = [SCOPES.index(s) for s in scopes]
    return dict(
        rounds=len(history[1:]),
        scope_sequence=" > ".join(scopes),
        highest_scope=SCOPES[max(levels)] if levels else "none",
        escalations=sum(b > a for a, b in zip(levels, levels[1:])),
        **{f"reached_{s}": s in scopes for s in SCOPES},
        repair_success=success_step is not None,
        success_step=success_step, success_scope=success_scope,
        **{f"rounds_{s}": rounds_at[s] for s in SCOPES},
        **{f"improving_rounds_{s}": improved_at[s] for s in SCOPES},
    )


## ---------- per-query stage data (table 6) ----------

def stage_states(checkpoint):
    """Loop verification of the plan in place before repair and after the last round of each scope."""
    history = checkpoint.get("repair_history") or []
    current = (history[0].get("verification") if history else None) or checkpoint.get("initial_verification") or {}
    states, last = {"initial": current}, {}
    for entry in history[1:]:
        if entry.get("accepted"):
            current = entry.get("verification") or {}
        scope = (entry.get("repair_attempt") or {}).get("editable_scope")
        if scope in SCOPES:
            last[scope] = current
    previous = states["initial"]
    for scope in SCOPES:
        states[scope] = previous = last.get(scope, previous)
    return states


def loop_values(verification):
    states = verification.get("personal_constraints") or []
    return dict(pc_true=true_count(states), pc_total=len(states),
                cs_errors=len(verification.get("commonsense_errors") or []))


def stage_rows(root, rows):
    """Add benchmark and loop-verifier fulfillment at each stage to every row (in place)."""
    manifest = load_json(root / "run_manifest.json")
    strategy = manifest["repair_strategies_requested"][0]
    references = load_json(benchmark_dir(root, strategy) / "evaluation_population.json")["queries"]
    lang = manifest.get("language", "en")
    ids = [r["query_uid"] for r in rows]
    states = {uid: stage_states(load_json(pair_path(root, uid, strategy))) for uid in ids}
    for stage in STAGES:
        plans = {uid: plan_or_empty(states[uid][stage].get("translated_plan")) for uid in ids}
        scores = score_plans(ids, references, plans, lang)
        for r in rows:
            score, loop = scores[r["query_uid"]], loop_values(states[r["query_uid"]][stage])
            r[f"bm_pc_{stage}"] = score["pc"]
            r[f"bm_cs_failed_{stage}"] = set(score["cs_failed"])
            r[f"bm_cs_total_{stage}"] = score["cs_total"]
            r[f"bm_all_pass_{stage}"] = score["all_pass"]
            r[f"loop_pc_true_{stage}"] = loop["pc_true"]
            r[f"loop_pc_total_{stage}"] = loop["pc_total"]
            r[f"loop_cs_errors_{stage}"] = loop["cs_errors"]
            r[f"loop_passed_{stage}"] = states[r["query_uid"]][stage].get("passed") is True


def per_query_stage_columns(r):
    """Flat per-query stage values for scope_per_query.csv."""
    out = {}
    for stage in STAGES:
        out[f"bm_pc_passed_{stage}"] = sum(r[f"bm_pc_{stage}"])
        out[f"bm_cs_failed_{stage}"] = len(r[f"bm_cs_failed_{stage}"])
        out[f"loop_pc_true_{stage}"] = r[f"loop_pc_true_{stage}"]
        out[f"loop_cs_errors_{stage}"] = r[f"loop_cs_errors_{stage}"]
    return out


## ---------- loading ----------

def benchmark_pass(output_dir):
    """all_pass_final per query from build_test_result_tables.py's per_query.csv, if it is there."""
    path = output_dir / "per_query.csv"
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as handle:
        return {r["query_uid"]: r["all_pass_final"] == "True" for r in csv.DictReader(handle)}


def build_rows(root, origin, passes):
    manifest = load_json(root / "run_manifest.json")
    strategy = manifest["repair_strategies_requested"][0]
    if strategy != "R3":
        print(f"warning: {root} is a {strategy} run; these tables are meant for R3", file=sys.stderr)
    rows = []
    for uid in manifest["query_uids"]:
        if uid not in origin:
            raise SystemExit(f"{uid} has no difficulty group in the origin file")
        path = pair_path(root, uid, strategy)
        checkpoint = load_json(path) if path.is_file() else {}
        rows.append(dict(query_uid=uid, group=origin[uid], **scope_data(checkpoint),
                         benchmark_all_pass_final=passes.get(uid)))
    return rows


## ---------- tables ----------

def table_scope(rows):
    successes = lambda g: [r for r in g if r["repair_success"]]
    t = []
    t.append(metric_row("[per query] Queries", rows, len, "run_manifest.json query_uids"))
    t.append(metric_row("[per query] Queries with at least one repair round", rows,
                        lambda g: sum(r["rounds"] > 0 for r in g), SRC_SCOPE))
    for scope in SCOPES:
        t.append(metric_row(f"[per query] Queries whose highest scope was {scope}", rows,
                            lambda g, s=scope: sum(r["highest_scope"] == s for r in g), SRC_SCOPE))
    t.append(metric_row("[per query] Avg highest scope level (1 = slot, 2 = day, 3 = plan; queries with a round)",
                        rows, lambda g: mean(SCOPES.index(r["highest_scope"]) + 1 for r in g
                                             if r["highest_scope"] in SCOPES), SRC_SCOPE))
    t.append(metric_row("[per query] Avg escalations per query (a round wider than the round before it)", rows,
                        lambda g: mean(r["escalations"] for r in g), SRC_SCOPE))
    t.append(metric_row("[per query] Max escalations in a query", rows,
                        lambda g: max((r["escalations"] for r in g), default=""), SRC_SCOPE))
    for scope in SCOPES:
        t.append(metric_row(f"[per query] % of queries reaching {scope} scope (at least one round at it)", rows,
                            lambda g, s=scope: pct(sum(r[f"reached_{s}"] for r in g), len(g)), SRC_SCOPE))
    t.append(metric_row("[per query] Successful repairs (queries whose plan passed the loop verifier after a round)",
                        rows, lambda g: len(successes(g)), SRC_SUCCESS))
    t.append(metric_row("[per query] % of queries repaired", rows,
                        lambda g: pct(len(successes(g)), len(g)), SRC_SUCCESS))
    for scope in SCOPES:
        t.append(metric_row(f"[per query] Successful repairs at {scope} scope", rows,
                            lambda g, s=scope: sum(r["success_scope"] == s for r in successes(g)), SRC_SUCCESS))
    for scope in SCOPES:
        t.append(metric_row(f"[per query] % of successful repairs at {scope} scope", rows,
                            lambda g, s=scope: pct(sum(r["success_scope"] == s for r in successes(g)),
                                                   len(successes(g))), SRC_SUCCESS))
    t.append(metric_row("[per query] Avg round of the successful repair", rows,
                        lambda g: mean(r["success_step"] for r in successes(g)), SRC_SUCCESS))
    has_benchmark = any(r["benchmark_all_pass_final"] is not None for r in rows)
    t.append(metric_row("[per query] Successful repairs whose final plan also passes the benchmark", rows,
                        lambda g: sum(r["benchmark_all_pass_final"] is True for r in successes(g))
                        if has_benchmark else "",
                        SRC_SUCCESS + "; benchmark = all_pass_final in per_query.csv (build_test_result_tables.py)"))
    for scope in SCOPES:
        t.append(metric_row(f"[round-wise] Rounds at {scope} scope", rows,
                            lambda g, s=scope: sum(r[f"rounds_{s}"] for r in g), SRC_SCOPE))
    for scope in SCOPES:
        t.append(metric_row(f"[round-wise] % of {scope}-scope rounds that improved the plan", rows,
                            lambda g, s=scope: pct(sum(r[f"improving_rounds_{s}"] for r in g),
                                                   sum(r[f"rounds_{s}"] for r in g)), SRC_IMPROVE))
    for scope in SCOPES:
        t.append(metric_row(f"[round-wise] % of improving rounds at {scope} scope", rows,
                            lambda g, s=scope: pct(sum(r[f"improving_rounds_{s}"] for r in g),
                                                   sum(r[f"improving_rounds_{x}"] for r in g for x in SCOPES)),
                            SRC_IMPROVE))
    return t


def table_fulfillment(rows):
    pc_share = lambda r, s: 100 * sum(r[f"bm_pc_{s}"]) / len(r[f"bm_pc_{s}"]) if r[f"bm_pc_{s}"] else None
    cs_share = lambda r, s: 100 * (1 - len(r[f"bm_cs_failed_{s}"]) / r[f"bm_cs_total_{s}"])
    loop_pc_share = lambda r, s: (100 * r[f"loop_pc_true_{s}"] / r[f"loop_pc_total_{s}"]
                                  if r[f"loop_pc_total_{s}"] else None)
    t = []
    ## Level at each stage (every query; a query that stopped earlier keeps its last plan).
    level_rows = (
        ("Avg % PC passed (benchmark)", lambda g, s: mean((pc_share(r, s) for r in g), 1), SRC_STAGE_BENCH),
        ("Avg % CS checks passed (benchmark, 28 checks)", lambda g, s: mean((cs_share(r, s) for r in g), 1),
         SRC_STAGE_BENCH),
        ("Avg CS checks failed (benchmark)", lambda g, s: mean(len(r[f"bm_cs_failed_{s}"]) for r in g),
         SRC_STAGE_BENCH),
        ("% of queries with all PC passed (benchmark)",
         lambda g, s: pct(sum(all(r[f"bm_pc_{s}"]) for r in g), len(g)), SRC_STAGE_BENCH),
        ("% of queries passing the benchmark (schema + CS + PC)",
         lambda g, s: pct(sum(r[f"bm_all_pass_{s}"] for r in g), len(g)), SRC_STAGE_BENCH),
        ("Avg % PC True (loop verifier, as R3 sees it)", lambda g, s: mean((loop_pc_share(r, s) for r in g), 1),
         SRC_STAGE_LOOP),
        ("Avg CS errors (loop verifier, as R3 sees it)", lambda g, s: mean(r[f"loop_cs_errors_{s}"] for r in g),
         SRC_STAGE_LOOP),
        ("% of queries passing the loop verifier",
         lambda g, s: pct(sum(r[f"loop_passed_{s}"] for r in g), len(g)), SRC_STAGE_LOOP),
    )
    for name, func, source in level_rows:
        for stage in STAGES:
            t.append(metric_row(f"[level] {name} - {STAGE_NAMES[stage]}", rows,
                                lambda g, f=func, s=stage: f(g, s), source))

    ## What each stage's rounds did, over the queries that had a round at that scope.
    src_change = ("benchmark (eval_exp functions): plan after the previous stage vs after this stage's rounds; "
                  "only queries with at least one round at this scope; pooled over constraints / checks")
    for prev, stage in zip(STAGES, SCOPES):
        active = lambda g, s=stage: [r for r in g if r[f"rounds_{s}"] > 0]
        label = f"[{stage} rounds]"

        def pc_moves(g, p=prev, s=stage, act=active, want_before=False, want_after=True):
            pairs = [(b, a) for r in act(g) for b, a in zip(r[f"bm_pc_{p}"], r[f"bm_pc_{s}"])]
            base = sum(b == want_before for b, _ in pairs)
            return pct(sum(b == want_before and a == want_after for b, a in pairs), base)

        def cs_moves(g, p=prev, s=stage, act=active, fixed=True):
            if fixed:
                part = sum(len(r[f"bm_cs_failed_{p}"] - r[f"bm_cs_failed_{s}"]) for r in act(g))
                base = sum(len(r[f"bm_cs_failed_{p}"]) for r in act(g))
            else:
                part = sum(len(r[f"bm_cs_failed_{s}"] - r[f"bm_cs_failed_{p}"]) for r in act(g))
                base = sum(r[f"bm_cs_total_{p}"] - len(r[f"bm_cs_failed_{p}"]) for r in act(g))
            return pct(part, base)

        def query_moves(g, key, better, p=prev, s=stage, act=active):
            before = (lambda r: sum(r[f"bm_pc_{p}"])) if key == "pc" else (lambda r: -len(r[f"bm_cs_failed_{p}"]))
            after = (lambda r: sum(r[f"bm_pc_{s}"])) if key == "pc" else (lambda r: -len(r[f"bm_cs_failed_{s}"]))
            return sum((after(r) > before(r)) if better else (after(r) < before(r)) for r in act(g))

        t.append(metric_row(f"{label} Queries with at least one round at this scope", rows,
                            lambda g, a=active: len(a(g)), SRC_SCOPE))
        t.append(metric_row(f"{label} % of failing PC fixed (failing before, passing after)", rows,
                            lambda g, f=pc_moves: f(g), src_change))
        t.append(metric_row(f"{label} % of passing PC broken (passing before, failing after)", rows,
                            lambda g, f=pc_moves: f(g, want_before=True, want_after=False), src_change))
        t.append(metric_row(f"{label} % of failing CS checks fixed", rows,
                            lambda g, f=cs_moves: f(g), src_change))
        t.append(metric_row(f"{label} % of passing CS checks broken", rows,
                            lambda g, f=cs_moves: f(g, fixed=False), src_change))
        t.append(metric_row(f"{label} Queries with more PC passed", rows,
                            lambda g, f=query_moves: f(g, "pc", True), src_change))
        t.append(metric_row(f"{label} Queries with fewer PC passed", rows,
                            lambda g, f=query_moves: f(g, "pc", False), src_change))
        t.append(metric_row(f"{label} Queries with fewer CS checks failed", rows,
                            lambda g, f=query_moves: f(g, "cs", True), src_change))
        t.append(metric_row(f"{label} Queries with more CS checks failed", rows,
                            lambda g, f=query_moves: f(g, "cs", False), src_change))
    return t


## ---------- main ----------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, default=REPO / "experiments/subset_test-r3")
    parser.add_argument("--origin", type=Path, default=REPO / "chinatravel/evaluation/splits/subset_origin.json")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args(argv)

    origin = load_json(args.origin)["origin"]
    rows = build_rows(args.run, origin, benchmark_pass(args.output_dir))
    base_columns = list(rows[0].keys())
    stage_rows(args.run, rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "table5_scope.csv", table_scope(rows), TABLE_COLUMNS)
    write_csv(args.output_dir / "table6_scope_fulfillment.csv", table_fulfillment(rows), TABLE_COLUMNS)
    flat = [{**{k: r[k] for k in base_columns}, **per_query_stage_columns(r)} for r in rows]
    write_csv(args.output_dir / "scope_per_query.csv", flat, list(flat[0].keys()))
    print(f"{len(rows)} queries -> {args.output_dir / 'table5_scope.csv'}, "
          f"{args.output_dir / 'table6_scope_fulfillment.csv'}")


if __name__ == "__main__":
    main()
