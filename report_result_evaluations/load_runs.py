"""Build the long tables that every report table reads (no JSON parsing downstream).

Reads only saved run outputs:
  experiments/<run>/attempts.jsonl                        one record per repair round
  experiments/<run>/queries/<uid>-*/R?-*.json             per-query checkpoint (R4: trials/R4-*.json)
  experiments/<run>/queries/<uid>-*/reference/query.json  the hard_logic_py list of the query
  experiments/<run>/benchmark_eval/<S>-*/{schema,logical_py,commonsense}.csv
                                                          benchmark scores of the final plans
  test_result_analysis/<S>/per_query.csv, train_result_analysis/<S>/per_query.csv
                                                          benchmark scores of the initial plans
  chinatravel/evaluation/splits/subset_origin.json        difficulty group per query

Writes report_result_evaluations/data/{rounds,queries,constraints}.csv.

Usage:  python report_result_evaluations/load_runs.py [--repo-root DIR] [--output-dir DIR]
"""
import argparse
import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parent

# (split, strategy, run folder, checkpoint glob relative to the query folder, per_query.csv)
RUNS = [
    ("test", "R0", "subset_test-r0", "R0-*.json", "test_result_analysis/R0/per_query.csv"),
    ("test", "R1", "subset_test-r1", "R1-*.json", "test_result_analysis/R1/per_query.csv"),
    ("test", "R2", "subset_test-r2", "R2-*.json", "test_result_analysis/R2/per_query.csv"),
    ("test", "R3", "subset_test-r3", "R3-*.json", "test_result_analysis/R3/per_query.csv"),
    ("test", "R4", "subset_test-r4", "trials/R4-*.json", "test_result_analysis/R4/per_query.csv"),
    ("train", "R0", "subset_train-r0", "R0-*.json", "train_result_analysis/R0/per_query.csv"),
    ("train", "R1", "subset_train-r1", None, None),  # reconstructed checkpoints: final scores only
    ("train", "R2", "subset_train-r2", "R2-*.json", "train_result_analysis/R2/per_query.csv"),
    ("train", "R3", "subset_train-r3-new", "R3-*.json", "train_result_analysis/R3/per_query.csv"),
]

# Kind -> family used for the "flagged family" rows (accommodation, monetary_budget).
KIND_TO_FAMILY = {
    "Total budget": "monetary_budget",
    "Food cost per person": "monetary_budget",
    "Rooms / room type": "accommodation",
    "Required attraction / restaurant / hotel type": "required_type",
    "Intercity transport mode": "transport_mode",
    "Inner-city transport mode": "transport_mode",
    "Ticket / taxi counts": "party_resources",
    "Days / people count": "trip_specification",
    "Departure / return times": "schedule_order",
    "Must include a named place": "named_place",
    "Other": "other",
}

CHRONO = "Does not follow Chronological Order"


def constraint_kind(code):
    """Same rules as scripts/result_analysis/build_test_result_tables.py::constraint_kind."""
    text = " ".join(str(code).split())
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


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def query_dir(run_dir, uid):
    hits = sorted(run_dir.glob(f"queries/{uid}-*"))
    if not hits:
        raise FileNotFoundError(f"no query folder for {uid} under {run_dir}")
    return hits[0]


def load_checkpoint(qdir, ckpt_glob):
    hits = sorted(qdir.glob(ckpt_glob))
    return read_json(hits[0]) if hits else None


def benchmark_final(run_dir, strategy):
    """Final-plan benchmark scores per query; a plan the checker crashed on fails every check."""
    bdir = sorted((run_dir / "benchmark_eval").glob(f"{strategy}-*"))[0]
    schema = pd.read_csv(bdir / "schema.csv").set_index("data_id")["schema"]
    lp = pd.read_csv(bdir / "logical_py.csv").set_index("data_id")
    cs = pd.read_csv(bdir / "commonsense.csv").set_index("data_id")
    exc_cols = [c for c in cs.columns if "Exception" in c]
    checks = [c for c in cs.columns if c not in exc_cols]
    rows, pcs = {}, {}
    for uid in schema.index:
        pc = lp.loc[uid].dropna().astype(int)
        crashed = bool(exc_cols) and float(cs.loc[uid, exc_cols].fillna(0).sum()) > 0
        failed = len(checks) if crashed else int((cs.loc[uid, checks].astype(float) > 0).sum())
        chrono = None
        if CHRONO in cs.columns and not crashed:
            chrono = int(float(cs.loc[uid, CHRONO]) > 0)
        rows[uid] = dict(schema_final=int(schema[uid]), pc_passed_final=int(pc.sum()), pc_total=len(pc),
                         cs_failed_final=failed, cs_total=len(checks), cs_crashed_final=int(crashed),
                         chrono_failed_final=chrono)
        pcs[uid] = {int(c.split("_")[-1]) + 1: int(v) for c, v in pc.items()}  # 1-based index
    return rows, pcs, bdir.name


def cs_set(verification):
    return set(verification.get("commonsense_errors") or [])


def pc_state(values):
    return "|".join("T" if v is True else "F" if v is False else "N" for v in (values or []))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO)
    ap.add_argument("--output-dir", type=Path, default=HERE / "data")
    args = ap.parse_args()
    repo = args.repo_root
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    origin = read_json(repo / "chinatravel/evaluation/splits/subset_origin.json")["origin"]

    rounds, queries, constraints = [], [], []
    for split, strategy, run_name, ckpt_glob, pq_rel in RUNS:
        run_dir = repo / "experiments" / run_name
        attempts = read_jsonl(run_dir / "attempts.jsonl")
        bench, bench_pcs, bench_dir = benchmark_final(run_dir, strategy)
        per_query = pd.read_csv(repo / pq_rel).set_index("query_uid") if pq_rel else None
        by_uid = {}
        for a in attempts:
            by_uid.setdefault(a["query_uid"], []).append(a)
        n_rounds_run = 0
        for uid in sorted(bench):
            qdir = query_dir(run_dir, uid)
            ref = read_json(qdir / "reference" / "query.json")
            dsl = ref.get("hard_logic_py") or []
            kinds = {i + 1: constraint_kind(code) for i, code in enumerate(dsl)}
            ckpt = load_checkpoint(qdir, ckpt_glob) if ckpt_glob else None
            group = origin.get(uid, "unknown")
            init_v = ckpt["initial_verification"] if ckpt else None
            hist = {h["step"]: h for h in ckpt["repair_history"]} if ckpt else {}
            cs_before = cs_set(init_v) if init_v else set()
            pcs_before = list(init_v["personal_constraints"]) if init_v else None
            last_noop_phase = None
            prev_phase = None
            q_attempts = sorted(by_uid.get(uid, []), key=lambda a: a["step"])
            n_changed = 0
            for a in q_attempts:
                step = a["step"]
                h = hist.get(step)
                cand = h["verification"] if h else None
                cs_cand = cs_set(cand) if cand else None
                md = a.get("repair_metadata") or {}
                changed = a.get("decision_reason") != "no_progress_unchanged"
                n_changed += int(changed)
                cache_hit = int(md.get("llm_cache_hits") or 0) > 0
                noop_kind = "changed" if changed else ("cached" if cache_hit else "other")
                phase = a.get("repair_phase")
                before = a.get("before_personal_constraints") or pcs_before or []
                failing = [i + 1 for i, v in enumerate(before) if v is False]
                unknown = [i + 1 for i, v in enumerate(before) if v is None]
                failing_kinds = {kinds.get(i, "Other") for i in failing}
                rec = md.get("recommended_risk_target")
                rec = rec if isinstance(rec, dict) else None
                rec_idx = rec.get("constraint_index") if rec else None
                targets = a.get("target_constraint_indices") or []
                fixed = a.get("fixed") or []
                broken = a.get("newly_violated") or []
                saved = (md.get("llm_cache_saved_input_tokens") or 0) + (md.get("llm_cache_saved_output_tokens") or 0)
                rounds.append(dict(
                    split=split, strategy=strategy, query_uid=uid, group=group, step=step,
                    phase=phase, accepted=bool(a.get("accepted")), decision_reason=a.get("decision_reason"),
                    changed=changed, cache_hit=cache_hit, noop_kind=noop_kind,
                    prev_round_noop_same_phase=(last_noop_phase == phase),
                    phase_switch=(prev_phase is not None and prev_phase != phase),
                    tokens=a.get("total_tokens_delta"), input_tokens=a.get("input_tokens_delta"),
                    output_tokens=a.get("output_tokens_delta"), tokens_saved_by_cache=saved,
                    cache_saved_unknown=md.get("llm_cache_saved_unknown") or 0,
                    repair_s=a.get("repair_time_seconds"), attempt_s=a.get("attempt_time_seconds"),
                    model_calls=a.get("model_calls"),
                    changed_slot_count=a.get("changed_slot_count"),
                    total_comparable_slots=a.get("total_comparable_slots"),
                    changed_slot_rate=a.get("changed_slot_rate"),
                    editable_scope=a.get("editable_scope"), scope_level=a.get("scope_level"),
                    escalation_reason=a.get("escalation_reason"),
                    pc_fixed_n=len(fixed), pc_broken_n=len(broken),
                    pc_fixed_idx=" ".join(map(str, fixed)), pc_broken_idx=" ".join(map(str, broken)),
                    pc_fixed_kinds="; ".join(kinds.get(i, "Other") for i in fixed),
                    pc_broken_kinds="; ".join(kinds.get(i, "Other") for i in broken),
                    pc_before=pc_state(before), pc_after=pc_state(a.get("after_personal_constraints")),
                    n_failing_before=len(failing), n_unknown_before=len(unknown),
                    only_named_place_left=bool(failing) and failing_kinds == {"Must include a named place"},
                    only_unknown_left=(not failing) and bool(unknown),
                    cs_before_n=len(cs_before) if ckpt else None,
                    cs_after_n=len(cs_cand) if cs_cand is not None else None,
                    cs_new_n=len(cs_cand - cs_before) if cs_cand is not None else None,
                    cs_fixed_n=len(cs_before - cs_cand) if cs_cand is not None else None,
                    target_idx=" ".join(map(str, targets)),
                    target_kinds="; ".join(kinds.get(i, "Other") for i in targets),
                    rec_target_idx=rec_idx, rec_target_family=rec.get("family") if rec else None,
                    rec_in_targets=(rec_idx in targets) if rec_idx else None,
                    rec_fixed=(rec_idx in fixed) if rec_idx else None,
                    other_fixed=bool([i for i in fixed if i != rec_idx]) if rec_idx else None,
                    rolled_back_idx=" ".join(map(str, md.get("rolled_back_constraint_indices") or [])),
                    failure_reason=md.get("failure_reason"),
                    # R4 personal rounds: how many failing constraints the advice ranked, and their risk scores
                    rec_candidates_n=len(md.get("risk_target_ranking") or []) if rec else None,
                    rec_ranking_idx=" ".join(str(x.get("constraint_index")) for x in md.get("risk_target_ranking") or []
                                             if isinstance(x, dict)) if rec else None,
                    rec_ranking_risks=" ".join(f"{x.get('expected_regressed_families', 0):.3f}"
                                               for x in md.get("risk_target_ranking") or [] if isinstance(x, dict)) if rec else None,
                    # R4 commonsense rounds: the families (and train risk) its advisory block named
                    cs_risk_families="; ".join(sorted({f"{c['family']} {c['regression_probability']:.3f}"
                                                       for c in md.get("commonsense_source_risks") or []
                                                       if isinstance(c, dict) and c.get("family")})),
                ))
                if a.get("accepted") and cand is not None:
                    cs_before = cs_cand
                    pcs_before = list(cand.get("personal_constraints") or pcs_before or [])
                elif a.get("accepted") and a.get("after_personal_constraints"):
                    pcs_before = list(a["after_personal_constraints"])
                last_noop_phase = None if changed else phase
                prev_phase = phase
            n_rounds_run += len(q_attempts)
            b = bench[uid]
            q = dict(split=split, strategy=strategy, query_uid=uid, group=group, run=run_name,
                     benchmark_dir=bench_dir, n_rounds=len(q_attempts), n_changed=n_changed,
                     tokens=sum((a.get("total_tokens_delta") or 0) for a in q_attempts),
                     tokens_saved_by_cache=sum(r["tokens_saved_by_cache"] for r in rounds[-len(q_attempts):]) if q_attempts else 0,
                     repair_s=sum((a.get("repair_time_seconds") or 0) for a in q_attempts),
                     model_calls=sum((a.get("model_calls") or 0) for a in q_attempts),
                     stop_reason=ckpt.get("stop_reason") if ckpt else None,
                     loop_passed_final=bool(ckpt["final_verification"].get("passed")) if ckpt else None,
                     loop_cs_errors_initial=len(cs_set(init_v)) if init_v else None,
                     loop_cs_errors_final=len(cs_set(ckpt["final_verification"])) if ckpt else None,
                     **b)
            if per_query is not None and uid in per_query.index:
                p = per_query.loc[uid]
                q.update(pc_passed_initial=int(p["pc_passed_initial"]),
                         cs_failed_initial=int(p["cs_total"]) - int(p["cs_passed_initial"]),
                         schema_initial=int(bool(p["schema_initial"])),
                         cs_crashed_initial=int(bool(p.get("cs_evaluator_exception_initial", False))),
                         stopped_early_while_failing=bool(p.get("stopped_early_while_failing", False)))
            else:
                q.update(pc_passed_initial=None, cs_failed_initial=None, schema_initial=None,
                         cs_crashed_initial=None, stopped_early_while_failing=None)
            q["all_pc_pass_final"] = int(q["pc_passed_final"] == q["pc_total"])
            q["all_pass_final"] = int(q["schema_final"] == 1 and q["cs_failed_final"] == 0 and q["all_pc_pass_final"] == 1)
            q["pc_share_final"] = q["pc_passed_final"] / q["pc_total"] if q["pc_total"] else None
            q["cs_share_final"] = 1 - q["cs_failed_final"] / q["cs_total"]
            if q["pc_passed_initial"] is not None:
                q["all_pc_pass_initial"] = int(q["pc_passed_initial"] == q["pc_total"])
                q["pc_share_initial"] = q["pc_passed_initial"] / q["pc_total"] if q["pc_total"] else None
                q["cs_share_initial"] = 1 - q["cs_failed_initial"] / q["cs_total"]
                q["all_pass_initial"] = int(q["schema_initial"] == 1 and q["cs_failed_initial"] == 0 and q["all_pc_pass_initial"] == 1)
                q["final_all_pc_equals_initial"] = int(q["all_pc_pass_final"] == q["all_pc_pass_initial"])
            else:
                q.update(all_pc_pass_initial=None, pc_share_initial=None, cs_share_initial=None,
                         all_pass_initial=None, final_all_pc_equals_initial=None)
            queries.append(q)
            loop_init = init_v["personal_constraints"] if init_v else [None] * len(dsl)
            loop_final = ckpt["final_verification"]["personal_constraints"] if ckpt else [None] * len(dsl)
            for i, code in enumerate(dsl, start=1):
                constraints.append(dict(split=split, strategy=strategy, query_uid=uid, group=group,
                                        constraint_index=i, kind=kinds[i],
                                        family=KIND_TO_FAMILY.get(kinds[i], "other"),
                                        loop_initial=loop_init[i - 1] if i - 1 < len(loop_init) else None,
                                        loop_final=loop_final[i - 1] if i - 1 < len(loop_final) else None,
                                        benchmark_final=bench_pcs[uid].get(i),
                                        hard_logic_py=" ".join(code.split())))
        print(f"{split} {strategy}: {len(bench)} queries, {n_rounds_run} rounds (attempts.jsonl has {len(attempts)})")
        assert n_rounds_run == len(attempts), "every attempt must belong to a benchmark-scored query"

    pd.DataFrame(rounds).to_csv(out / "rounds.csv", index=False)
    pd.DataFrame(queries).to_csv(out / "queries.csv", index=False)
    pd.DataFrame(constraints).to_csv(out / "constraints.csv", index=False)
    for name in ("rounds", "queries", "constraints"):
        print("wrote", out / f"{name}.csv")


if __name__ == "__main__":
    main()
