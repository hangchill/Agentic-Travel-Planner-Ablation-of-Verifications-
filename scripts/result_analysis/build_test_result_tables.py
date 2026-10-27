"""Build per-repair result tables (CSV), split by difficulty group, for test-split runs.

For each run given with --run LABEL=DIR, writes to <output-dir>/<LABEL>/:
  table1_pc.csv                  personal constraints (PC), benchmark, initial vs final plan
  table1b_pc_failure_by_kind.csv PC failure rate by constraint kind, whole cohort
  table2_cs.csv                  commonsense (CS) checks, benchmark, initial vs final plan
  table3_repair_process.csv      tokens, time, changed-round effect, round split
  table4_eval_exp.csv            ChinaTravel's own micro / macro metrics on the final plans
  per_query.csv                  every per-query value the tables are built from
and <output-dir>/README.md describing the files, definitions, sources and caveats.

Table columns are Easy / Medium / Human / All. Unless a row says otherwise, a value is
computed for each query first and then averaged over the group's queries.

Reads only saved run files (no model calls, no changes to the run folders):
  - final plan:    benchmark_eval/*/plans/<uid>.json (written by evaluate_repair_run.py)
  - initial plan:  the checkpoint's initial_verification.translated_plan
  - reference:     benchmark_eval/*/evaluation_population.json -> queries[uid]
  - rounds/tokens: the checkpoint (queries/<uid>/<strategy>.json, or trials/ for R4)
Initial and final plans are scored with the same evaluator functions eval_exp.py uses.

Usage:
  python scripts/build_test_result_tables.py --run R2=experiments/subset_test-r2 \
      --run R3=experiments/subset_test-r3 --run R4=experiments/subset_test-r4
"""
import argparse
import contextlib
import csv
import io
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from chinatravel.evaluation.repair_comparison import pair_path

REPO = Path(__file__).resolve().parents[2]
GROUPS = ("easy", "medium", "human")
COLUMNS = ("Easy", "Medium", "Human", "All")
CS_PASS_THRESHOLD = 0.85
CS_EXCEPTION_COLUMN = "Commonsense Evaluator Exception"
## Text the model wrapper (chinatravel/agent/llms.py REQUEST_ERROR_RESPONSE) returns when a call fails.
REQUEST_ERROR_TEXT = "Request failed, please try again."


## ---------- loading ----------

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_runs(values):
    runs = []
    for value in values:
        label, sep, directory = value.partition("=")
        if not sep or not label or not directory:
            raise SystemExit(f"--run expects LABEL=DIR, got {value!r}")
        runs.append((label, Path(directory)))
    if len({label for label, _ in runs}) != len(runs):
        raise SystemExit("Duplicate --run labels")
    return runs


def benchmark_dir(root, strategy):
    matches = sorted((root / "benchmark_eval").glob(f"{strategy}-*"))
    if len(matches) != 1:
        raise SystemExit(f"{root}: expected one benchmark_eval/{strategy}-* folder; "
                         "run scripts/result_analysis/evaluate_repair_run.py first")
    return matches[0]


def plan_or_empty(plan):
    return plan if isinstance(plan, dict) else {}


def initial_generation_failed(plan):
    """True when the initial plan is the generator's error placeholder (no activities)."""
    days = plan.get("itinerary") if isinstance(plan, dict) else None
    if not isinstance(days, list) or not days:
        return True
    return any(not isinstance(day, dict) or "activities" not in day for day in days)


## ---------- scoring with the benchmark evaluator ----------

def score_plans(ids, references, plans, lang):
    """Per-query benchmark results, using the functions eval_exp.evaluate_final_plans calls."""
    from chinatravel.evaluation.commonsense_constraint import evaluate_commonsense_constraints
    from chinatravel.evaluation.hard_constraint import evaluate_hard_constraints_v2
    from chinatravel.evaluation.schema_constraint import evaluate_schema_constraints

    schema = load_json(REPO / "chinatravel/evaluation/output_schema.json")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _, _, schema_pass = evaluate_schema_constraints(ids, plans, schema)
        _, _, cs_rows, cs_pass = evaluate_commonsense_constraints(ids, references, plans, lang=lang)
        _, _, _, _, pc_rows, pc_pass = evaluate_hard_constraints_v2(
            ids, references, plans, env_pass_id=cs_pass, lang=lang)
    raw_columns = [c for c in cs_rows.columns if c != "data_id"]
    ## The evaluator adds this column only when it crashes on a plan, and then marks
    ## nothing else, so a plan it could not check would look like it passed every check.
    checks = [c for c in raw_columns if c != CS_EXCEPTION_COLUMN]
    cs_by_id = {row["data_id"]: row for _, row in cs_rows.iterrows()}
    pc_by_id = {row["data_id"]: row for _, row in pc_rows.iterrows()}
    schema_pass, cs_pass, pc_pass = set(schema_pass), set(cs_pass), set(pc_pass)
    failed = lambda row, column: str(row[column]).strip() not in ("0", "0.0", "", "nan")
    out = {}
    for uid in ids:
        constraints = len(references[uid]["hard_logic_py"])
        pc = [int(pc_by_id[uid][f"logic_py_{i}"]) == 1 for i in range(constraints)]
        row = cs_by_id[uid]
        exception = CS_EXCEPTION_COLUMN in raw_columns and failed(row, CS_EXCEPTION_COLUMN)
        failed_checks = list(checks) if exception else [c for c in checks if failed(row, c)]
        out[uid] = dict(pc=pc, cs_failed=failed_checks, cs_total=len(checks), cs_exception=exception,
                        cs_failed_raw=sum(failed(row, c) for c in raw_columns), cs_total_raw=len(raw_columns),
                        schema=uid in schema_pass,
                        all_pass=uid in schema_pass and uid in cs_pass and uid in pc_pass)
    return out


## ---------- constraint kinds ----------

def original_code(query):
    """Constraints as the query states them. English runs score translated named-place
    names (`hard_logic_py`); the Chinese original (`hard_logic_py_original`) keeps the kind visible."""
    return query.get("hard_logic_py_original") or query["hard_logic_py"]


def constraint_kind(code):
    text = " ".join(code.split())
    if re.search(r"_name_set\)", text) and re.search(r"[一-鿿]", text):
        return "Must include a named place"
    if "total_cost" in text:
        return "Total budget"
    if "food_cost" in text:
        return "Food cost per person"
    if "_type_set" in text:
        return "Required attraction / restaurant / hotel type"
    if "intercity_transport_type" in text:
        return "Intercity transport mode"
    if "room_count" in text or "room_type" in text:
        return "Rooms / room type"
    if "tickets" in text or "cars" in text:
        return "Ticket / taxi counts"
    if "innercity_transport_type" in text:
        return "Inner-city transport mode"
    if "day_count" in text or "people_count" in text:
        return "Days / people count"
    if "go_end_time" in text or "return_start_time" in text:
        return "Departure / return times"
    return "Other"


## ---------- per-round data from the checkpoint ----------

def true_count(states):
    return sum(state is True for state in states or [])


def round_data(checkpoint):
    """Changed / cached / other rounds and the effect of each changed round (loop verifier)."""
    history = checkpoint.get("repair_history") or []
    current = (history[0].get("verification") if history else None) or checkpoint.get("initial_verification") or {}
    current_plan = json.dumps(current.get("translated_plan"), sort_keys=True)
    rounds = changed = cached = error_replies = 0
    delta_pc, delta_cs = [], []
    for entry in history[1:]:
        rounds += 1
        attempt = entry.get("repair_attempt") or {}
        if REQUEST_ERROR_TEXT in str((attempt.get("repair_metadata") or {}).get("raw_response") or ""):
            error_replies += 1
        verification = entry.get("verification") or {}
        candidate_plan = json.dumps(verification.get("translated_plan"), sort_keys=True)
        if candidate_plan != current_plan:
            changed += 1
            delta_pc.append(true_count(verification.get("personal_constraints"))
                            - true_count(current.get("personal_constraints")))
            delta_cs.append(len(verification.get("commonsense_errors") or [])
                            - len(current.get("commonsense_errors") or []))
        elif ((attempt.get("repair_metadata") or {}).get("llm_cache_hits") or 0) > 0:
            cached += 1
        if entry.get("accepted"):
            current, current_plan = verification, candidate_plan
    return dict(rounds=rounds, error_reply_rounds=error_replies, changed=changed, unchanged_cache=cached,
                unchanged_other=rounds - changed - cached,
                dpc_per_changed=statistics.mean(delta_pc) if delta_pc else None,
                dcs_per_changed=statistics.mean(delta_cs) if delta_cs else None)


def counted_tokens(attempt):
    """Tokens the provider reported during one round, even when the round's total is unknown.

    total_tokens_delta is left empty when any request in the round returned no usage
    (a failed request). The cumulative input/output counters still include every
    request that did report usage, so their difference counts those tokens.
    """
    if attempt.get("total_tokens_delta") is not None:
        return attempt["total_tokens_delta"]
    total = 0
    for side in ("input", "output"):
        before, after = attempt.get(f"{side}_tokens_before"), attempt.get(f"{side}_tokens_after")
        if type(before) is int and type(after) is int and after >= before:
            total += after - before
    return total


def summed(values):
    values = list(values)
    return sum(values) if values and all(v is not None for v in values) else None


## ---------- per-query table ----------

def build_queries(root, origin):
    manifest = load_json(root / "run_manifest.json")
    strategy = manifest["repair_strategies_requested"][0]
    bench = benchmark_dir(root, strategy)
    population = load_json(bench / "evaluation_population.json")
    references = population["queries"]
    ids = list(manifest["query_uids"])
    lang = manifest.get("language", "en")
    budget = min(int(manifest.get("max_steps", 6)), 6)

    checkpoints, initial_plans, final_plans = {}, {}, {}
    for uid in ids:
        path = pair_path(root, uid, strategy)
        checkpoint = load_json(path) if path.is_file() else {}
        checkpoints[uid] = checkpoint
        initial = (checkpoint.get("initial_verification") or {}).get("translated_plan")
        if initial is None and checkpoint.get("repair_history"):
            initial = (checkpoint["repair_history"][0].get("verification") or {}).get("translated_plan")
        initial_plans[uid] = plan_or_empty(initial)
        final_plans[uid] = plan_or_empty(load_json(bench / "plans" / f"{uid}.json"))

    initial_scores = score_plans(ids, references, initial_plans, lang)
    final_scores = score_plans(ids, references, final_plans, lang)

    rows = []
    for uid in ids:
        if uid not in origin:
            raise SystemExit(f"{uid} has no difficulty group in the origin file")
        code = references[uid]["hard_logic_py"]
        kinds = [constraint_kind(c) for c in original_code(references[uid])]
        init, final = initial_scores[uid], final_scores[uid]
        kept = [i for i, kind in enumerate(kinds) if kind != "Must include a named place"]
        checkpoint = checkpoints[uid]
        attempts = checkpoint.get("repair_attempts") or []
        rounds = round_data(checkpoint)
        final_loop = checkpoint.get("final_verification") or {}
        rows.append(dict(
            query_uid=uid, group=origin[uid], repair_strategy=strategy,
            execution_status=checkpoint.get("execution_status", "missing_checkpoint"),
            stop_reason=checkpoint.get("stop_reason"),
            initial_generation_failed=initial_generation_failed(initial_plans[uid]),
            final_plan_is_error_stub=initial_generation_failed(final_plans[uid]),
            stopped_early_while_failing=(rounds["rounds"] < budget and final_loop.get("passed") is not True),
            pc_total=len(code),
            pc_passed_initial=sum(init["pc"]), pc_passed_final=sum(final["pc"]),
            pc_share_initial=sum(init["pc"]) / len(code), pc_share_final=sum(final["pc"]) / len(code),
            pc_failed_final=len(code) - sum(final["pc"]),
            pc_failed_kinds_final="; ".join(kinds[i] for i, ok in enumerate(final["pc"]) if not ok),
            pc_total_excl_named=len(kept),
            pc_passed_final_excl_named=sum(final["pc"][i] for i in kept),
            cs_total=final["cs_total"],
            cs_passed_initial=init["cs_total"] - len(init["cs_failed"]),
            cs_passed_final=final["cs_total"] - len(final["cs_failed"]),
            cs_failed_checks_final="" if final["cs_exception"] else "; ".join(final["cs_failed"]),
            cs_evaluator_exception_initial=init["cs_exception"], cs_evaluator_exception_final=final["cs_exception"],
            cs_failed_raw_final=final["cs_failed_raw"], cs_total_raw_final=final["cs_total_raw"],
            schema_initial=init["schema"], schema_final=final["schema"],
            all_pass_initial=init["all_pass"], all_pass_final=final["all_pass"],
            ## A completed query with no repair rounds (its initial plan already passed the
            ## loop verifier) spent 0 repair tokens and time; only a missing checkpoint is unknown.
            tokens_spent=(0 if checkpoint and not attempts else summed(a.get("total_tokens_delta") for a in attempts)),
            tokens_spent_known=sum(counted_tokens(a) for a in attempts),
            rounds_missing_tokens=sum(a.get("total_tokens_delta") is None for a in attempts),
            repair_time_s=(0.0 if checkpoint and not attempts else summed(a.get("repair_time_seconds") for a in attempts)),
            **rounds,
        ))
    return strategy, manifest, rows, references


## ---------- table helpers ----------

def by_group(rows):
    groups = {name: [r for r in rows if r["group"] == name] for name in GROUPS}
    groups["all"] = list(rows)
    return [groups[name] for name in (*GROUPS, "all")]


def mean(values, digits=2):
    values = [v for v in values if v is not None]
    if not values:
        return ""
    value = round(statistics.mean(values), digits)
    return int(value) if digits == 0 else value


def row(metric, per_group, source):
    return dict(metric=metric, **dict(zip(COLUMNS, per_group)), source=source)


def metric_row(metric, rows, func, source):
    return row(metric, [func(group) for group in by_group(rows)], source)


def top_three(counter):
    return "; ".join(f"{name} ({count})" for name, count in counter.most_common(3)) or "none"


def write_csv(path, records, columns):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)


TABLE_COLUMNS = ("metric", *COLUMNS, "source")
SRC_PC = ("benchmark (eval_exp functions): final = benchmark_eval/*/logical_py.csv plans; "
          "initial = checkpoint initial_verification.translated_plan scored the same way")
SRC_CS = ("benchmark (eval_exp functions): final = benchmark_eval/*/commonsense.csv plans; "
          "initial = checkpoint initial_verification.translated_plan scored the same way")


def table_pc(rows):
    t = []
    t.append(metric_row("Queries (n)", rows, len, "chinatravel/evaluation/splits/subset_origin.json"))
    t.append(metric_row("Avg personal constraints per query", rows,
                        lambda g: mean(r["pc_total"] for r in g), "evaluation_population.json queries[uid].hard_logic_py"))
    t.append(metric_row("Avg PC failed per query - initial plan", rows,
                        lambda g: mean(r["pc_total"] - r["pc_passed_initial"] for r in g), SRC_PC))
    t.append(metric_row("Avg PC failed per query - final plan", rows, lambda g: mean(r["pc_failed_final"] for r in g), SRC_PC))
    t.append(metric_row("Avg PC passed per query - initial plan", rows, lambda g: mean(r["pc_passed_initial"] for r in g), SRC_PC))
    t.append(metric_row("Avg PC passed per query - final plan", rows, lambda g: mean(r["pc_passed_final"] for r in g), SRC_PC))
    t.append(metric_row("Avg PC passed per query - change (final - initial)", rows,
                        lambda g: mean(r["pc_passed_final"] - r["pc_passed_initial"] for r in g), SRC_PC))
    t.append(metric_row("Avg % PC passed per query - initial plan", rows,
                        lambda g: mean((100 * r["pc_share_initial"] for r in g), 1), SRC_PC))
    t.append(metric_row("Avg % PC passed per query - final plan", rows,
                        lambda g: mean((100 * r["pc_share_final"] for r in g), 1), SRC_PC))
    t.append(metric_row("Avg % PC passed per query - change (percentage points)", rows,
                        lambda g: mean((100 * (r["pc_share_final"] - r["pc_share_initial"]) for r in g), 1), SRC_PC))
    t.append(metric_row("Queries where % PC passed increased", rows,
                        lambda g: sum(r["pc_passed_final"] > r["pc_passed_initial"] for r in g), SRC_PC))
    t.append(metric_row("Queries where % PC passed remained the same", rows,
                        lambda g: sum(r["pc_passed_final"] == r["pc_passed_initial"] for r in g), SRC_PC))
    t.append(metric_row("  of which already 100% in the initial plan", rows,
                        lambda g: sum(r["pc_passed_final"] == r["pc_passed_initial"] == r["pc_total"] for r in g), SRC_PC))
    t.append(metric_row("Queries where % PC passed decreased", rows,
                        lambda g: sum(r["pc_passed_final"] < r["pc_passed_initial"] for r in g), SRC_PC))
    t.append(metric_row("Final plans with 0 failed PC", rows, lambda g: sum(r["pc_failed_final"] == 0 for r in g), SRC_PC))
    t.append(metric_row("Final plans with 1 failed PC", rows, lambda g: sum(r["pc_failed_final"] == 1 for r in g), SRC_PC))
    t.append(metric_row("Final plans with 2 failed PC", rows, lambda g: sum(r["pc_failed_final"] == 2 for r in g), SRC_PC))
    t.append(metric_row("Final plans with 3+ failed PC", rows, lambda g: sum(r["pc_failed_final"] >= 3 for r in g), SRC_PC))
    t.append(metric_row("Top 3 failing PC kinds in final plans (failures)", rows,
                        lambda g: top_three(Counter(k for r in g for k in r["pc_failed_kinds_final"].split("; ") if k)),
                        SRC_PC + "; kind classified from hard_logic_py"))
    t.append(metric_row("Final plans passing all PC, excluding named-place constraints", rows,
                        lambda g: sum(r["pc_passed_final_excl_named"] == r["pc_total_excl_named"] for r in g),
                        SRC_PC + "; named-place names translated to English for scoring"))
    t.append(metric_row("Avg % PC passed per query - final plan, excluding named-place constraints", rows,
                        lambda g: mean((100 * r["pc_passed_final_excl_named"] / r["pc_total_excl_named"]
                                        for r in g if r["pc_total_excl_named"]), 1),
                        SRC_PC + "; named-place names translated to English for scoring"))
    return t


def table_pc_kinds(rows, references):
    failed, total = Counter(), Counter()
    for r in rows:
        kinds = [constraint_kind(c) for c in original_code(references[r["query_uid"]])]
        total.update(kinds)
        failed.update(k for k in r["pc_failed_kinds_final"].split("; ") if k)
    records = [dict(kind=kind, failed=failed[kind], total=total[kind],
                    failure_rate_pct=round(100 * failed[kind] / total[kind], 1))
               for kind in sorted(total, key=lambda k: (-failed[k] / total[k], -total[k], k))]
    return records


def table_cs(rows):
    """Commonsense in failed-check counts (fewer is better); each plan is checked against the same checks."""
    failed_initial = lambda r: r["cs_total"] - r["cs_passed_initial"]
    failed_final = lambda r: r["cs_total"] - r["cs_passed_final"]
    total = rows[0]["cs_total"] if rows else 0
    max_failed = max(n for n in range(total + 1) if (total - n) / total > CS_PASS_THRESHOLD) if total else 0
    t = []
    t.append(metric_row("Avg CS checks failed per query - initial plan", rows, lambda g: mean(failed_initial(r) for r in g), SRC_CS))
    t.append(metric_row("Avg CS checks failed per query - final plan", rows, lambda g: mean(failed_final(r) for r in g), SRC_CS))
    t.append(metric_row("Avg CS checks failed per query - change (final - initial; negative = fewer failures)", rows,
                        lambda g: mean(failed_final(r) - failed_initial(r) for r in g), SRC_CS))
    share = lambda passed, r: 100 * passed / r["cs_total"]
    t.append(metric_row("Avg % CS checks passed per query - initial plan", rows,
                        lambda g: mean((share(r["cs_passed_initial"], r) for r in g), 1), SRC_CS))
    t.append(metric_row("Avg % CS checks passed per query - final plan", rows,
                        lambda g: mean((share(r["cs_passed_final"], r) for r in g), 1), SRC_CS))
    t.append(metric_row("Avg % CS checks passed per query - change (percentage points)", rows,
                        lambda g: mean((share(r["cs_passed_final"], r) - share(r["cs_passed_initial"], r) for r in g), 1),
                        SRC_CS))
    t.append(metric_row("Queries where failed CS checks decreased (improved)", rows,
                        lambda g: sum(failed_final(r) < failed_initial(r) for r in g), SRC_CS))
    t.append(metric_row("Queries where failed CS checks stayed the same", rows,
                        lambda g: sum(failed_final(r) == failed_initial(r) for r in g), SRC_CS))
    t.append(metric_row("Queries where failed CS checks increased (got worse)", rows,
                        lambda g: sum(failed_final(r) > failed_initial(r) for r in g), SRC_CS))
    t.append(metric_row("Final plans with 0 failed CS checks", rows, lambda g: sum(failed_final(r) == 0 for r in g), SRC_CS))
    t.append(metric_row("Final plans with 1 failed CS check", rows, lambda g: sum(failed_final(r) == 1 for r in g), SRC_CS))
    t.append(metric_row("Final plans with 2 failed CS checks", rows, lambda g: sum(failed_final(r) == 2 for r in g), SRC_CS))
    t.append(metric_row("Final plans with 3 failed CS checks", rows, lambda g: sum(failed_final(r) == 3 for r in g), SRC_CS))
    t.append(metric_row("Final plans with 4+ failed CS checks", rows, lambda g: sum(failed_final(r) >= 4 for r in g), SRC_CS))
    t.append(metric_row(f"Final plans with at most {max_failed} failed CS checks "
                        f"(more than {int(CS_PASS_THRESHOLD * 100)}% of the {total} checks passed)", rows,
                        lambda g: sum(failed_final(r) <= max_failed for r in g), SRC_CS))
    t.append(metric_row("Final plans the CS evaluator could not check (counted as failing every check)", rows,
                        lambda g: sum(r["cs_evaluator_exception_final"] for r in g),
                        SRC_CS + "; 'Commonsense Evaluator Exception' column = 1"))
    t.append(metric_row("Top 3 failing CS checks in final plans (plans failing)", rows,
                        lambda g: top_three(Counter(c for r in g for c in r["cs_failed_checks_final"].split("; ") if c)), SRC_CS))
    return t


def table_process(rows):
    src_ckpt = "checkpoint repair_attempts (queries/<uid>/<strategy>.json or trials/)"
    src_round = ("checkpoint repair_history: candidate verification.translated_plan vs the plan in place "
                 "before the round; cache = repair_attempt.repair_metadata.llm_cache_hits > 0")
    with_tokens = lambda g: [r for r in g if r["tokens_spent"] is not None]

    def pct(g, key):
        total = sum(r["rounds"] for r in g)
        return round(100 * sum(r[key] for r in g) / total, 1) if total else ""

    t = []
    t.append(metric_row("[per query] Queries with token data", rows, lambda g: len(with_tokens(g)), src_ckpt))
    t.append(metric_row("[per query] Avg tokens spent per query (queries with complete token data)", rows,
                        lambda g: mean((r["tokens_spent"] for r in g), 0), src_ckpt + ": sum of total_tokens_delta"))
    t.append(metric_row("[per query] Rounds with no recorded token count", rows,
                        lambda g: sum(r["rounds_missing_tokens"] for r in g), src_ckpt + ": total_tokens_delta is null"))
    t.append(metric_row("[per query] Avg tokens spent per query - all queries, failed requests counted as 0 (lower bound)", rows,
                        lambda g: mean((r["tokens_spent_known"] for r in g), 0),
                        src_ckpt + ": every request that reported usage (input/output token counters before vs after "
                        "each round); failed requests reported none and add 0"))
    t.append(metric_row("[per query] Avg repair time per query (s)", rows,
                        lambda g: mean((r["repair_time_s"] for r in g), 1), src_ckpt + ": sum of repair_time_seconds"))
    t.append(metric_row("[per query] Queries with at least one round that changed the plan", rows,
                        lambda g: sum(r["changed"] > 0 for r in g), src_round))
    t.append(metric_row("[per query] Avg change in PC passed per changed round (loop verifier)", rows,
                        lambda g: mean(r["dpc_per_changed"] for r in g), src_round +
                        "; each query's own average, then averaged over queries with a changed round"))
    t.append(metric_row("[per query] Avg change in CS errors per changed round (loop verifier; negative = fewer errors)", rows,
                        lambda g: mean(r["dcs_per_changed"] for r in g), src_round +
                        "; each query's own average, then averaged over queries with a changed round"))
    t.append(metric_row("[round-wise] Repair rounds in total", rows, lambda g: sum(r["rounds"] for r in g), src_round))
    t.append(metric_row("[round-wise] % of rounds where the model call failed (error text instead of a plan; "
                        "includes cached repeats of a failed reply)", rows, lambda g: pct(g, "error_reply_rounds"),
                        "checkpoint repair_attempt.repair_metadata.raw_response contains the wrapper's "
                        f"'{REQUEST_ERROR_TEXT}' text"))
    t.append(metric_row("[round-wise] % of rounds where the plan changed", rows, lambda g: pct(g, "changed"), src_round))
    t.append(metric_row("[round-wise] % of rounds unchanged - answered from cache (exact repeat of an earlier request)",
                        rows, lambda g: pct(g, "unchanged_cache"), src_round))
    t.append(metric_row("[round-wise] % of rounds unchanged - from a different request (model called)",
                        rows, lambda g: pct(g, "unchanged_other"), src_round))
    return t


def table_eval_exp(rows):
    """ChinaTravel's own definitions (see commonsense_constraint.py / hard_constraint.py)."""
    def cs_micro(g):
        ## Benchmark definition, including its exception column (see README caveat).
        cells = sum(r["cs_total_raw_final"] for r in g)
        return round(100 * (1 - sum(r["cs_failed_raw_final"] for r in g) / cells), 2) if cells else ""

    def lg_micro(g):
        total = sum(r["pc_total"] for r in g)
        return round(100 * sum(r["pc_passed_final"] for r in g) / total, 2) if total else ""

    pct = lambda g, ok: round(100 * sum(ok(r) for r in g) / len(g), 2) if g else ""
    src = "benchmark_eval/*/commonsense.csv, logical_py.csv, schema.csv (final plans); eval_exp definitions"
    return [
        metric_row("Commonsense micro (%) - share of all (plan, check) pairs passed", rows, cs_micro, src),
        metric_row("Commonsense macro (%) - plans passing every CS check", rows,
                   lambda g: pct(g, lambda r: r["cs_failed_raw_final"] == 0), src),
        metric_row("Logical micro (%) - share of all personal constraints passed (pooled)", rows, lg_micro, src),
        metric_row("Logical macro (%) - plans passing every personal constraint", rows,
                   lambda g: pct(g, lambda r: r["pc_failed_final"] == 0), src),
        metric_row("All-pass ratio (%) - schema + CS + PC all passed", rows,
                   lambda g: pct(g, lambda r: r["all_pass_final"]), src),
    ]


## ---------- README ----------

def readme(run_notes):
    lines = [
        "# Test result analysis",
        "",
        "Generated by `scripts/result_analysis/build_test_result_tables.py`. Do not edit by hand; rerun the script.",
        "",
        "One folder per repair method. Every table CSV has the columns `metric, Easy, Medium, Human, All, source`.",
        "Difficulty groups come from `chinatravel/evaluation/splits/subset_origin.json` (not the uid prefix).",
        "Unless a row says otherwise, a value is computed for each query first and then averaged over the group.",
        "",
        "| File | Contents |",
        "|---|---|",
        "| `table1_pc.csv` | Personal constraints (PC), benchmark: avg failed and avg passed initial vs final, queries up / same / down, 0 / 1 / 2 / 3+ failed, top failing kinds, results without named-place constraints |",
        "| `table1b_pc_failure_by_kind.csv` | PC failure rate by constraint kind, whole cohort |",
        "| `table2_cs.csv` | Commonsense (CS) checks, benchmark: avg failed checks and avg % passed initial vs final, queries improved / same / worse, plans with 0 / 1 / 2 / 3 / 4+ failed, plans with at most 4 failed, top failing checks |",
        "| `table3_repair_process.csv` | Avg tokens and repair time, effect of a changed round, and the round split (changed / cached / other) |",
        "| `table4_eval_exp.csv` | ChinaTravel's own micro / macro metrics on the final plans, per group |",
        "| `per_query.csv` | Every per-query value the tables are built from |",
        "",
        "`merged/` holds the same tables side by side for all methods, with columns ordered by group then method "
        "(Easy R2, Easy R3, Easy R4, Medium R2, ..., All R4). `MERGED_TABLES.md` shows the same merged tables as "
        "Markdown. Both are written when more than one `--run` is given.",
        "",
        "## Definitions",
        "",
        "- **Final plan:** the plan the benchmark scored, `benchmark_eval/*/plans/<uid>.json` (written by `scripts/result_analysis/evaluate_repair_run.py`): the last accepted plan of the repair loop. For R4 this is the trial's last accepted plan; R4's \"best plan seen\" selection in `final_state.json` is not used.",
        "- **Initial plan:** the plan before any repair round, the checkpoint's `initial_verification.translated_plan`.",
        "- **Benchmark scoring:** both plans are scored with the functions `eval_exp.evaluate_final_plans` uses (`evaluate_schema_constraints`, `evaluate_commonsense_constraints`, `evaluate_hard_constraints_v2`). Table 4's All column therefore matches `benchmark_eval/*/benchmark_summary.json`.",
        "- **PC kinds** are classified from each `hard_logic_py` string (named place, total budget, required type, and so on).",
        "- **CS checks:** every plan is checked against the same 28 pass/fail check categories. Table 2 reports how many of them failed (fewer is better). \"More than 85% passed\" means at most 4 of 28 failed.",
        "- **Changed round:** a repair round whose candidate plan differs from the plan in place before it. Its ΔPC / ΔCS use the loop verifier's results (True count of `personal_constraints`, number of `commonsense_errors`), so ΔPC also counts constraints that were UNKNOWN before and became checkable. For R2 this includes candidates its rollback later rejected.",
        "- **Round split:** every round is exactly one of: plan changed; plan unchanged and the request was an exact repeat answered from the cache (`repair_metadata.llm_cache_hits > 0`); plan unchanged although the model was called with a different request.",
        "- **Tokens / time:** sums over the checkpoint's `repair_attempts` (`total_tokens_delta`, `repair_time_seconds`); repair only, initial plan generation excluded. A query with any missing token value has no token figure.",
        "",
        "## Caveats",
        "",
        "- **Named-place constraints are translated for scoring.** The query DSL keeps Chinese place names (for example `{'寒山寺'}<=attraction_name_set`), but English plans use English names. `evaluate_repair_run` replaces each name with the English name of the same database row before scoring (`chinatravel/evaluation/named_place_translation.py`; log in `benchmark_eval/*/named_place_translations.json`). The repair loop still checked the Chinese name, so during repair it reported these constraints as failed even when the plan had the right place. The \"excluding named-place constraints\" rows show results without them.",
        "- **Missing walking-leg `price`.** `translate_innercity_transport` (`llm_modulo.py`) leaves `price` off direct walking legs, which fails the schema check and the \"Incorrect Information of Inner-City Transport on price, distance, and duration\" CS check for many plans.",
        "- **Loop time-check crash.** `collect_time_error` raises `KeyError: 'position'` on a train or flight that departs before its transport arrives. That hides timing errors from repair and can stop a query early while it is still failing.",
        "- **Plans the CS evaluator can't check.** When `evaluate_commonsense_constraints` crashes on a plan (for example an error placeholder with no activities), it marks only an extra `Commonsense Evaluator Exception` column. That plan would look like it passed every real check. Tables 1–3 use the 28 standard checks and count such a plan as failing all of them. Table 4 keeps ChinaTravel's own definition so it matches `benchmark_summary.json`, so its commonsense micro is inflated for runs with such plans.",
        "- **Failed model calls.** When a call to the model provider fails, `chinatravel/agent/llms.py` returns the text `{\"error\": \"Request failed, please try again.\"}` instead of raising. The round then has no token count, the repeat-request cache stores that text and serves it to later identical requests, and a strategy that always accepts (R0) can take it as its new plan, so a working plan is replaced by an error placeholder. Table 3 shows the share of rounds affected; per-run notes list the queries.",
        "- **Small groups:** 10 queries per group, so differences of a query or two are noise.",
        "",
        "## Per-run notes",
        "",
    ]
    for label, notes in run_notes:
        lines.append(f"### {label}")
        lines.extend(notes or ["- No flagged queries."])
        lines.append("")
    return "\n".join(lines)


def run_notes(label, root, manifest, rows):
    notes = [f"- Source run: `{root.as_posix()}` (run_id `{manifest['run_id']}`, split `{manifest.get('split_query_source')}`, "
             f"model `{manifest.get('model_identifier')}`, {len(rows)} queries, max {manifest.get('max_steps')} rounds)."]
    for r in rows:
        if r["initial_generation_failed"]:
            notes.append(f"- `{r['query_uid']}` ({r['group']}): initial plan generation failed (error placeholder, no activities); the query scores as a failure.")
        if r["error_reply_rounds"]:
            replaced = (r["final_plan_is_error_stub"] and not r["initial_generation_failed"])
            notes.append(f"- `{r['query_uid']}` ({r['group']}): {r['error_reply_rounds']} of {r['rounds']} rounds got the "
                         "failed-call text instead of a plan (provider error)"
                         + ("; the final plan is that error placeholder, which replaced a working plan, so the query "
                            "scores as a failure" if replaced else "") + ".")
        if r["stopped_early_while_failing"] and not r["initial_generation_failed"]:
            notes.append(f"- `{r['query_uid']}` ({r['group']}): stopped after {r['rounds']} rounds while still failing "
                         f"(saved stop reason `{r['stop_reason']}`), so its rounds, tokens and time are lower.")
    for path in sorted((root / "queries").glob("*/rerun_provenance.json")):
        provenance = load_json(path)
        uid = path.parent.name.rsplit("-", 1)[0]
        group = next((r["group"] for r in rows if r["query_uid"] == uid), "?")
        notes.append(f"- `{uid}` ({group}): checkpoint replaced by a single-query rerun "
                     f"(`{provenance['rerun_run_id']}`, commit `{(provenance.get('rerun_git_commit') or '?')[:7]}`) "
                     "because the original run's rounds got the failed-call text instead of a plan. The rerun "
                     "regenerated the initial plan, so it differs from the original run's "
                     f"(see `{path.relative_to(root).as_posix()}`).")
    missing = [r for r in rows if r["tokens_spent"] is None]
    if missing:
        notes.append(f"- Token data incomplete for {len(missing)} queries ({sum(r['rounds_missing_tokens'] for r in missing)} "
                     "rounds with no recorded token count): "
                     + ", ".join(f"`{r['query_uid']}`" for r in missing)
                     + ". Each of these rounds had at least one failed model request (the provider returned an error "
                       "and no token usage; the model wrapper then returned the text "
                       "'{\"error\": \"Request failed, please try again.\"}' instead of a plan). These queries are "
                       "left out of the complete-data token row; the lower-bound row counts every "
                       "request that did report usage and counts failed requests as 0.")
    return notes


## ---------- main ----------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="append", required=True, metavar="LABEL=DIR")
    parser.add_argument("--origin", type=Path, default=REPO / "chinatravel/evaluation/splits/subset_origin.json")
    parser.add_argument("--output-dir", type=Path, default=REPO / "test_result_analysis")
    args = parser.parse_args(argv)

    origin = load_json(args.origin)["origin"]
    all_notes, per_run = [], {}
    for label, root in parse_runs(args.run):
        strategy, manifest, rows, references = build_queries(root, origin)
        out = args.output_dir / label
        out.mkdir(parents=True, exist_ok=True)
        tables = {
            "table1_pc.csv": table_pc(rows),
            "table2_cs.csv": table_cs(rows),
            "table3_repair_process.csv": table_process(rows),
            "table4_eval_exp.csv": table_eval_exp(rows),
        }
        for name, records in tables.items():
            write_csv(out / name, records, TABLE_COLUMNS)
        kinds = table_pc_kinds(rows, references)
        write_csv(out / "table1b_pc_failure_by_kind.csv", kinds, ("kind", "failed", "total", "failure_rate_pct"))
        write_csv(out / "per_query.csv", rows, list(rows[0].keys()))
        per_run[label] = (tables, kinds)
        all_notes.append((label, run_notes(label, root, manifest, rows)))
        print(f"{label} ({strategy}): {len(rows)} queries -> {out}")
    if len(per_run) > 1:
        merged, kind_records = write_merged(args.output_dir / "merged", per_run)
        print(f"merged ({', '.join(per_run)}) -> {args.output_dir / 'merged'}")
        markdown_path = args.output_dir / "MERGED_TABLES.md"
        markdown_path.write_text(merged_markdown(list(per_run), merged, kind_records), encoding="utf-8")
        print(f"merged view -> {markdown_path}")
    (args.output_dir / "README.md").write_text(readme(all_notes) + "\n", encoding="utf-8")


def write_merged(out, per_run):
    """Side-by-side tables: columns Easy R2, Easy R3, ..., All R4 (group first, then method)."""
    out.mkdir(parents=True, exist_ok=True)
    labels = list(per_run)
    columns = [f"{group} {label}" for group in COLUMNS for label in labels]
    first = per_run[labels[0]][0]
    merged = {}
    for name in first:
        by_label = {label: {r["metric"]: r for r in per_run[label][0][name]} for label in labels}
        records = []
        for base in first[name]:
            metric = base["metric"]
            record = {"metric": metric}
            for group in COLUMNS:
                for label in labels:
                    record[f"{group} {label}"] = by_label[label].get(metric, {}).get(group, "")
            record["source"] = base["source"]
            records.append(record)
        write_csv(out / name, records, ("metric", *columns, "source"))
        merged[name] = records
    kinds = {label: {k["kind"]: k for k in per_run[label][1]} for label in labels}
    order = list(dict.fromkeys(k["kind"] for label in labels for k in per_run[label][1]))
    records = []
    for kind in order:
        record = {"kind": kind}
        for label in labels:
            k = kinds[label].get(kind, {})
            record[f"{label} failed"] = k.get("failed", "")
            record[f"{label} total"] = k.get("total", "")
            record[f"{label} failure_rate_pct"] = k.get("failure_rate_pct", "")
        records.append(record)
    write_csv(out / "table1b_pc_failure_by_kind.csv", records,
              ("kind", *[f"{label} {c}" for label in labels for c in ("failed", "total", "failure_rate_pct")]))
    return merged, records


MERGED_TITLES = {
    "table1_pc.csv": ("Table 1: Personal constraints (PC), benchmark",
                      "Initial = plan before any repair round; final = plan the benchmark scored. "
                      "Named-place names are translated to English for scoring (see README)."),
    "table2_cs.csv": ("Table 2: Commonsense (CS), number of failed checks, benchmark",
                      "Each plan is checked against the same 28 checks; fewer failed is better. "
                      "A plan the checker can't evaluate counts as failing all 28."),
    "table3_repair_process.csv": ("Table 3: Repair process",
                                  "[per query] rows are averaged over queries; [round-wise] rows are pooled over rounds. "
                                  "ΔPC / ΔCS use the repair loop's own verifier."),
    "table4_eval_exp.csv": ("Table 4: ChinaTravel's own metrics (eval_exp definitions), final plans",
                            "The All columns match each run's benchmark_eval/*/benchmark_summary.json. Commonsense micro "
                            "is inflated for runs with plans the checker couldn't evaluate."),
}


def md_cell(value):
    return str(value).replace("|", "\\|")


def merged_markdown(labels, merged, kind_records):
    """MERGED_TABLES.md: every merged table as Markdown; long text rows go in their own small table."""
    columns = [f"{group} {label}" for group in COLUMNS for label in labels]
    lines = [
        "# Merged result tables",
        "",
        f"Generated by `scripts/result_analysis/build_test_result_tables.py` from `merged/*.csv`. "
        f"Do not edit by hand; rerun the script.",
        "",
        f"Columns are grouped by difficulty, then by method ({', '.join(labels)}). "
        "Definitions, data sources and caveats are in [README.md](README.md); "
        "each CSV's `source` column names the source of every row.",
        "",
    ]
    for name, (title, note) in MERGED_TITLES.items():
        records = merged.get(name, [])
        numeric = [r for r in records if not r["metric"].startswith("Top 3")]
        text = [r for r in records if r["metric"].startswith("Top 3")]
        lines += [f"## {title}", "", note, ""]
        lines.append("| Metric | " + " | ".join(columns) + " |")
        lines.append("|---|" + "---|" * len(columns))
        for r in numeric:
            lines.append("| " + md_cell(r["metric"]) + " | " + " | ".join(md_cell(r[c]) for c in columns) + " |")
        lines.append("")
        for r in text:
            lines += [f"**{r['metric']}**", "", "| Group | " + " | ".join(labels) + " |",
                      "|---|" + "---|" * len(labels)]
            for group in COLUMNS:
                lines.append(f"| {group} | " + " | ".join(md_cell(r[f'{group} {label}']) for label in labels) + " |")
            lines.append("")
        if name == "table1_pc.csv":
            lines += ["## Table 1b: PC failure rate by kind, whole cohort", "",
                      "Failed / total constraints of each kind in the final plans.", "",
                      "| Kind | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
            for r in kind_records:
                cells = []
                for label in labels:
                    failed, total = r[f"{label} failed"], r[f"{label} total"]
                    cells.append(f"{failed}/{total} ({r[f'{label} failure_rate_pct']}%)" if total != "" else "")
                lines.append(f"| {md_cell(r['kind'])} | " + " | ".join(cells) + " |")
            lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
