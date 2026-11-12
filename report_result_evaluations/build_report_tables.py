"""Build the tables behind docs/report/overleaf/evaluation_and_results.tex from data/*.csv.

Only tables that the .tex shows, or whose numbers its text quotes, are built:
  T1   t1_headline                 final-plan benchmark metrics (the "key test results" table; all-pass,
                                   macro and micro rates in the text)
  T3   t3_regression               regression during repair (Ablation 1: 11 accepted regressions)
  T3c  t3c_regression_queries      R0's regressed queries and R2's rollback queries (Ablation 1)
  T4   t4_budget_use               rounds, changed and cached rounds (Efficiency, Ablations 1 to 3)
  T5   t5_efficiency               repair tokens and time (the "key test results" table, Efficiency)
  T6   t6_difficulty_effectiveness effectiveness by difficulty (Performance by query difficulty, Ablations 1 and 3)
  T6b  t6b_difficulty_what_fails   most frequent final-plan failures by group and strategy (named places)
  T7b  t7b_train_headline          train-split rates and cost: the data of fig3
  T11  t11_query_outcome_map       which queries pass every personal constraint, per strategy (Ablation 3)
  T16  t16_r0_regressions_in_r4    R0's regressions and the same items in R4 (table "r0-regressions-r4");
                                   reads tables/t14_failure_repair.csv from failure_repair.py
  T16b t16b_r0_r4_case_trace       every test query in which R0 broke a personal constraint, traced in
                                   R0 and R4 (table "r0-r4-case-trace")

Inputs (read-only): data/{rounds,queries,constraints}.csv (from load_runs.py),
tables/t14_failure_repair.csv (from failure_repair.py), experiments/subset_test-r*/benchmark_eval/*/commonsense.csv
(T6b), experiments/subset_test-r0 and subset_test-r4 attempts.jsonl and checkpoints (hotel bookings, T16b).

Outputs: tables/t*.csv (the data tables), tables/REPORT_TABLES.md, tables/manifest_tables.csv, and
report_tables/{key_test_results,r0_regressions_r4,r0_r4_case_trace}.csv: the three tables of the .tex in its
layout, built from T1, T5, T16 and T16b.

Statistics policy: descriptive values everywhere. A percentile bootstrap 95 % CI over queries
(5,000 resamples, seed 4213) appears only in T1 (headline pass rates) and T3 (new commonsense errors
per edited activity).

Usage:  python report_result_evaluations/build_report_tables.py [--repo-root DIR] [--output-dir DIR]
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STRATS = ["R0", "R1", "R2", "R3", "R4"]
GROUPS = ["easy", "medium", "human"]
REPS, SEED = 5000, 4213
FLAGGED = {"accommodation", "monetary_budget"}


# ---------------------------------------------------------------- helpers
def bootstrap_ci(values, func=np.mean, reps=REPS, seed=SEED):
    """Percentile 95 % CI of func over resampled queries."""
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(reps, len(arr)))
    stats = func(arr[idx], axis=1)
    return (float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5)))


def pct(x, d=1):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(100 * x, d)


def kn(k, n):
    return f"{int(k)}/{int(n)}" if n else "0/0"


def to_markdown(df, floatfmt=".2f"):
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                cells.append("" if np.isnan(v) else (f"{v:{floatfmt}}" if abs(v - round(v)) > 1e-9 else f"{int(round(v))}"))
            else:
                cells.append("" if v is None else str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def parse_state(s):
    return [] if not isinstance(s, str) else list(s.split("|"))


def idx_list(s):
    return [] if not isinstance(s, str) or not s.strip() else [int(x) for x in s.split()]



# ---------------------------------------------------------------- tables
def t1_headline(Q):
    rows = []
    for s in STRATS:
        q = Q[(Q.split == "test") & (Q.strategy == s)]
        lpr_macro_ci = bootstrap_ci(q.all_pc_pass_final)
        epr_micro_ci = bootstrap_ci(q.cs_share_final)
        rows.append(dict(
            strategy=s, n=len(q),
            schema_pass_pct=pct(q.schema_final.mean()),
            epr_micro_pct=pct(q.cs_share_final.mean()), epr_micro_ci_lo=pct(epr_micro_ci[0]), epr_micro_ci_hi=pct(epr_micro_ci[1]),
            epr_macro_pct=pct((q.cs_failed_final == 0).mean()),
            lpr_micro_pct=pct(q.pc_passed_final.sum() / q.pc_total.sum()),
            lpr_macro_pct=pct(q.all_pc_pass_final.mean()), lpr_macro_ci_lo=pct(lpr_macro_ci[0]), lpr_macro_ci_hi=pct(lpr_macro_ci[1]),
            all_pass_pct=pct(q.all_pass_final.mean()),
            lpr_macro_initial_pct=pct(q.all_pc_pass_initial.mean()),
            epr_micro_initial_pct=pct(q.cs_share_initial.mean()),
            epr_macro_initial_pct=pct((q.cs_failed_initial == 0).mean()),
            avg_pc_pass_pct=pct(q.pc_share_final.mean()),
            avg_pc_pass_initial_pct=pct(q.pc_share_initial.mean()),
            queries_gained_all_pc=int(((q.all_pc_pass_initial == 0) & (q.all_pc_pass_final == 1)).sum()),
            queries_lost_all_pc=int(((q.all_pc_pass_initial == 1) & (q.all_pc_pass_final == 0)).sum()),
            final_all_pc_equals_initial_pct=pct(q.final_all_pc_equals_initial.mean()),
            source="data/queries.csv (benchmark_eval final plans; per_query.csv initial plans)",
        ))
    return pd.DataFrame(rows)


def flagged_counts(R, C, split="test"):
    """Per strategy: flagged-family (accommodation, budget) constraints broken / at risk in changed CS rounds."""
    fam = {(r.strategy, r.query_uid, r.constraint_index): r.family for r in C[C.split == split].itertuples()}
    out = {}
    for s in STRATS:
        g = R[(R.split == split) & (R.strategy == s) & R.changed & (R.phase == "commonsense")]
        at_risk = broken = 0
        for r in g.itertuples():
            before = parse_state(r.pc_before)
            for i, st in enumerate(before, start=1):
                if st == "T" and fam.get((s, r.query_uid, i)) in FLAGGED:
                    at_risk += 1
            broken += sum(1 for i in idx_list(r.pc_broken_idx) if fam.get((s, r.query_uid, i)) in FLAGGED)
        out[s] = (broken, at_risk, len(g))
    return out


def t3_regression(R, Q, C):
    flagged = flagged_counts(R, C)
    rows = []
    for s in STRATS:
        g = R[(R.split == "test") & (R.strategy == s)]
        ch = g[g.changed]
        q = Q[(Q.split == "test") & (Q.strategy == s)]
        pe = ch[ch.changed_slot_count > 0]
        rate = (pe.cs_new_n / pe.changed_slot_count)
        lo, hi = bootstrap_ci(rate) if s in ("R0", "R1") else (np.nan, np.nan)
        pers = ch[ch.phase == "personal"]
        csr = ch[ch.phase == "commonsense"]
        b, a, n_cs = flagged[s]
        rows.append(dict(
            strategy=s, rounds=len(g), changed_rounds=len(ch),
            candidates_with_new_pc_violation=int((g.pc_broken_n > 0).sum()),
            accepted_with_new_pc_violation=int(((g.pc_broken_n > 0) & g.accepted).sum()),
            queries_with_accepted_pc_regression=int(g[(g.pc_broken_n > 0) & g.accepted].query_uid.nunique()),
            rejected_candidates=int((~g.accepted).sum()), queries_with_rejection=int(g[~g.accepted].query_uid.nunique()),
            queries_final_pc_below_initial=int((q.pc_passed_final < q.pc_passed_initial).sum()),
            pc_fixed_events=int(g[g.accepted].pc_fixed_n.sum()), pc_broken_events_accepted=int(g[g.accepted].pc_broken_n.sum()),
            cs_fixed_per_changed_round=round(ch.cs_fixed_n.mean(), 2), cs_new_per_changed_round=round(ch.cs_new_n.mean(), 2),
            new_cs_per_edited_activity=round(rate.mean(), 2), npe_ci_lo=None if np.isnan(lo) else round(lo, 2),
            npe_ci_hi=None if np.isnan(hi) else round(hi, 2), npe_rounds=len(pe),
            personal_changed_rounds_adding_cs_error=kn((pers.cs_new_n > 0).sum(), len(pers)),
            pcs_broken_in_cs_rounds=int(csr.pc_broken_n.sum()), pcs_fixed_in_personal_rounds=int(pers.pc_fixed_n.sum()),
            flagged_family_regressions_per_changed_cs_round=kn(b, a), changed_cs_rounds=n_cs,
            source="data/rounds.csv (loop verifier, candidate vs accepted plan); data/queries.csv (benchmark)",
        ))
    return pd.DataFrame(rows)


def t4_budget_use(R, Q):
    rows = []
    for s in STRATS:
        g = R[(R.split == "test") & (R.strategy == s)]
        q = Q[(Q.split == "test") & (Q.strategy == s)]
        ch = g[g.changed]
        locked_k = int(((~g.changed) & g.prev_round_noop_same_phase).sum())
        locked_n = int(g.prev_round_noop_same_phase.sum())
        first_p = g[(g.phase == "personal")].sort_values("step").groupby("query_uid").head(1)
        first_c = g[(g.phase == "commonsense")].sort_values("step").groupby("query_uid").head(1)
        slot = ch[ch.changed_slot_rate.notna()]
        rows.append(dict(
            strategy=s, rounds=len(g), rounds_per_query=round(len(g) / 30, 2),
            changed_pct=pct(g.changed.mean()), cached_noop_pct=pct((g.noop_kind == "cached").mean()),
            other_noop_pct=pct((g.noop_kind == "other").mean()),
            noop_after_noop_same_phase=kn(locked_k, locked_n), locked_rounds_pct=pct(locked_k / len(g)),
            first_personal_round_changed=kn(first_p.changed.sum(), len(first_p)),
            first_cs_round_changed=kn(first_c.changed.sum(), len(first_c)),
            mean_changed_slot_rate=round(slot.changed_slot_rate.mean(), 2), median_changed_slot_rate=round(slot.changed_slot_rate.median(), 2),
            rounds_with_slot_rate=len(slot),
            queries_stopped_verification_passed=int((q.stop_reason == "verification_passed").sum()),
            queries_with_a_changed_round=int((q.n_changed > 0).sum()),
            source="data/rounds.csv, data/queries.csv",
        ))
    df = pd.DataFrame(rows)
    r3 = R[(R.split == "test") & (R.strategy == "R3")]
    extra = []
    for scope in ["slot", "day", "plan"]:
        g = r3[r3.editable_scope == scope]
        extra.append(dict(strategy=f"R3 {scope} rounds", rounds=len(g), rounds_per_query=None, changed_pct=pct(g.changed.mean()),
                          cached_noop_pct=pct((g.noop_kind == "cached").mean()), other_noop_pct=pct((g.noop_kind == "other").mean()),
                          noop_after_noop_same_phase=None, locked_rounds_pct=None, first_personal_round_changed=None,
                          first_cs_round_changed=None, mean_changed_slot_rate=round(g[g.changed_slot_rate.notna() & g.changed].changed_slot_rate.mean(), 2),
                          median_changed_slot_rate=None, rounds_with_slot_rate=int((g.changed_slot_rate.notna() & g.changed).sum()),
                          queries_stopped_verification_passed=None, queries_with_a_changed_round=None, source="data/rounds.csv (editable_scope)"))
    return pd.concat([df, pd.DataFrame(extra)], ignore_index=True)


def t5_efficiency(R, Q):
    rows = []
    for s in STRATS:
        g = R[(R.split == "test") & (R.strategy == s)]
        q = Q[(Q.split == "test") & (Q.strategy == s)]
        spent = q.tokens.sum()
        saved = q.tokens_saved_by_cache.sum()
        ch = g[g.changed]
        rows.append(dict(
            strategy=s, tokens_per_query=int(round(q.tokens.mean())), tokens_per_query_median=int(round(q.tokens.median())),
            tokens_if_nothing_cached_per_query=int(round((q.tokens + q.tokens_saved_by_cache).mean())),
            cache_saved_pct=pct(saved / (spent + saved)),
            model_calls_per_query=round(q.model_calls.mean(), 2),
            tokens_per_changed_round=int(round(spent / len(ch))) if len(ch) else None,
            repair_time_s_per_query=round(q.repair_s.mean(), 1), repair_time_s_median=round(q.repair_s.median(), 1),
            seconds_per_changed_round=round(q.repair_s.sum() / len(ch), 1) if len(ch) else None,
            locked_rounds_pct=pct(((~g.changed) & g.prev_round_noop_same_phase).sum() / len(g)),
            source="data/queries.csv, data/rounds.csv (repair rounds only; initial plan generation excluded)",
        ))
    return pd.DataFrame(rows)


def t6_difficulty(Q):
    rows = []
    for grp in GROUPS + ["all"]:
        for s in STRATS:
            q = Q[(Q.split == "test") & (Q.strategy == s)]
            if grp != "all":
                q = q[q.group == grp]
            rows.append(dict(
                group=grp, strategy=s, n=len(q), pc_per_query=round(q.pc_total.mean(), 1),
                all_pc_pass_initial_pct=pct(q.all_pc_pass_initial.mean(), 0), all_pc_pass_final_pct=pct(q.all_pc_pass_final.mean(), 0),
                queries_gained=int(((q.all_pc_pass_initial == 0) & (q.all_pc_pass_final == 1)).sum()),
                queries_lost=int(((q.all_pc_pass_initial == 1) & (q.all_pc_pass_final == 0)).sum()),
                pc_share_change_pp=pct((q.pc_share_final - q.pc_share_initial).mean()),
                cs_share_initial_pct=pct(q.cs_share_initial.mean()), cs_share_final_pct=pct(q.cs_share_final.mean()),
                cs_share_change_pp=pct((q.cs_share_final - q.cs_share_initial).mean()),
                cs_improved=int((q.cs_failed_final < q.cs_failed_initial).sum()), cs_same=int((q.cs_failed_final == q.cs_failed_initial).sum()),
                cs_worse=int((q.cs_failed_final > q.cs_failed_initial).sum()),
                lpr_micro_pct=pct(q.pc_passed_final.sum() / q.pc_total.sum()),
                plans_le4_failed_cs=int((q.cs_failed_final <= 4).sum()), all_pass=int(q.all_pass_final.sum()),
                source="data/queries.csv; group from subset_origin.json",
            ))
    return pd.DataFrame(rows)


def t6b_what_fails(C, repo):
    rows = []
    for grp in GROUPS:
        for s in STRATS:
            c = C[(C.split == "test") & (C.strategy == s) & (C.group == grp)]
            failed = c[c.benchmark_final == 0].kind.value_counts()
            top = "; ".join(f"{k} ({v})" for k, v in failed.head(3).items())
            rows.append(dict(group=grp, strategy=s, item="personal constraint kinds failing in the final plan (count)", top3=top,
                             constraints=len(c), failed=int((c.benchmark_final == 0).sum()), source="data/constraints.csv (benchmark final)"))
    origin = pd.read_json(repo / "chinatravel/evaluation/splits/subset_origin.json")["origin"]
    for s, run in zip(STRATS, ["subset_test-r0", "subset_test-r1", "subset_test-r2", "subset_test-r3", "subset_test-r4"]):
        bdir = sorted((repo / "experiments" / run / "benchmark_eval").glob(f"{s}-*"))[0]
        cs = pd.read_csv(bdir / "commonsense.csv").set_index("data_id")
        checks = [c for c in cs.columns if "Exception" not in c]
        cs["group"] = [origin.get(u) for u in cs.index]
        for grp in GROUPS:
            sub = cs[cs.group == grp][checks]
            counts = (sub.astype(float) > 0).sum().sort_values(ascending=False)
            top = "; ".join(f"{k} ({int(v)})" for k, v in counts.head(3).items() if v > 0)
            rows.append(dict(group=grp, strategy=s, item="commonsense checks failing in the final plan (plans)", top3=top,
                             constraints=len(sub) * len(checks), failed=int((sub.astype(float) > 0).sum().sum()),
                             source=f"experiments/{run}/benchmark_eval/{bdir.name}/commonsense.csv"))
    return pd.DataFrame(rows)


def t7b_train_headline(Q):
    """Train split, R0 to R3: the four F1 rates and the two costs (initial values where the run saved them)."""
    rows = []
    for s in ["R0", "R1", "R2", "R3"]:
        q = Q[(Q.split == "train") & (Q.strategy == s)]
        has_initial = q.pc_share_initial.notna().all()
        init = (lambda v: pct(v)) if has_initial else (lambda v: None)
        rows.append(dict(
            strategy=s, n=len(q),
            lpr_macro_pct=pct(q.all_pc_pass_final.mean()), lpr_macro_initial_pct=init(q.all_pc_pass_initial.mean()),
            epr_macro_pct=pct((q.cs_failed_final == 0).mean()), epr_macro_initial_pct=init((q.cs_failed_initial == 0).mean()),
            avg_pc_pass_pct=pct(q.pc_share_final.mean()), avg_pc_pass_initial_pct=init(q.pc_share_initial.mean()),
            epr_micro_pct=pct(q.cs_share_final.mean()), epr_micro_initial_pct=init(q.cs_share_initial.mean()),
            all_pass_pct=pct(q.all_pass_final.mean()),
            tokens_per_query=int(round(q.tokens.mean())), repair_time_s_per_query=round(q.repair_s.mean(), 1),
            cs_unscoreable_final=int(q.cs_crashed_final.fillna(False).astype(bool).sum()),
            source="data/queries.csv (train; benchmark_eval final plans; train_result_analysis per_query.csv initial plans; "
                   "R1 train has no saved initial plans)"))
    return pd.DataFrame(rows)


def t3c_regression_queries(R, Q):
    """R0's queries with an accepted personal regression, and R2's queries where rollback fired."""
    r, q = R[R.split == "test"], Q[Q.split == "test"].set_index(["strategy", "query_uid"])
    rows = []

    def outcome(s, uid):
        qq = q.loc[(s, uid)]
        a, b = int(qq.pc_passed_initial), int(qq.pc_passed_final)
        return dict(pc_passed_initial_to_final=f"{a} -> {b} / {int(qq.pc_total)}",
                    personal_outcome="worse" if b < a else ("better" if b > a else "same"),
                    cs_failed_initial_to_final=f"{int(qq.cs_failed_initial)} -> {int(qq.cs_failed_final)}",
                    all_pass_final=bool(qq.all_pass_final))

    reg = r[(r.strategy == "R0") & r.accepted & (r.pc_broken_n > 0)]
    for uid, g in reg.groupby("query_uid"):
        rows.append(dict(strategy="R0", query_uid=uid, group=g.group.iloc[0],
                         candidates=f"{len(g)} accepted with a new personal violation "
                                    f"({(g.phase == 'personal').sum()} personal, {(g.phase == 'commonsense').sum()} commonsense rounds)",
                         fixed_in_those=int(g.pc_fixed_n.sum()), broken_in_those=int(g.pc_broken_n.sum()), **outcome("R0", uid)))
    rej = r[(r.strategy == "R2") & ~r.accepted]
    for uid, g in rej.groupby("query_uid"):
        acc = r[(r.strategy == "R2") & (r.query_uid == uid) & r.accepted & r.changed]
        rows.append(dict(strategy="R2", query_uid=uid, group=g.group.iloc[0],
                         candidates=f"{len(g)} rejected ({(g.phase == 'personal').sum()} personal, "
                                    f"{(g.phase == 'commonsense').sum()} commonsense); {len(acc)} changed rounds accepted",
                         fixed_in_those=int(g.pc_fixed_n.sum()), broken_in_those=int(g.pc_broken_n.sum()),
                         net_per_rejected_candidate=", ".join(f"{int(x.pc_fixed_n - x.pc_broken_n):+d}" for x in g.itertuples()),
                         **outcome("R2", uid)))
    df = pd.DataFrame(rows)
    df["source"] = "data/rounds.csv (loop verifier: fixed / newly_violated per candidate) + data/queries.csv (benchmark initial / final)"
    return df


def _hotels(plan):
    out = []
    for day in plan or []:
        for a in day.get("activities", []):
            if a.get("type") == "accommodation":
                out.append(str((day.get("day"), a.get("position"), a.get("room_type"), a.get("rooms"))))
    return tuple(sorted(out))


def t11_outcome_map(Q):
    q = Q[Q.split == "test"]
    piv = q.pivot(index="query_uid", columns="strategy", values=["all_pc_pass_initial", "all_pc_pass_final", "all_pass_final"])
    grp = q.groupby("query_uid").group.first()
    pct_total = q.groupby("query_uid").pc_total.first()
    rows = []
    for uid in piv.index:
        row = dict(query_uid=uid, group=grp[uid], pc_total=int(pct_total[uid]))
        for s in STRATS:
            row[f"{s}_init"] = int(piv.loc[uid, ("all_pc_pass_initial", s)])
            row[f"{s}_final"] = int(piv.loc[uid, ("all_pc_pass_final", s)])
            row[f"{s}_allpass"] = int(piv.loc[uid, ("all_pass_final", s)])
        fin = [row[f"{s}_final"] for s in STRATS]
        ini = [row[f"{s}_init"] for s in STRATS]
        row["strategies_passing_all_pc_final"] = sum(fin)
        row["strategies_passing_all_pc_initial"] = sum(ini)
        row["source"] = "data/queries.csv"
        rows.append(row)
    df = pd.DataFrame(rows).sort_values(["group", "strategies_passing_all_pc_final", "query_uid"], ascending=[True, False, True])
    summary = pd.DataFrame([
        dict(query_uid="SUMMARY: queries passing all PC under no strategy (final)", group="", pc_total=int((df.strategies_passing_all_pc_final == 0).sum())),
        dict(query_uid="SUMMARY: under every strategy (final)", group="", pc_total=int((df.strategies_passing_all_pc_final == 5).sum())),
        dict(query_uid="SUMMARY: under some strategies (final)", group="", pc_total=int(df.strategies_passing_all_pc_final.between(1, 4).sum())),
        dict(query_uid="SUMMARY: under no strategy (initial)", group="", pc_total=int((df.strategies_passing_all_pc_initial == 0).sum())),
        dict(query_uid="SUMMARY: under every strategy (initial)", group="", pc_total=int((df.strategies_passing_all_pc_initial == 5).sum())),
    ])
    summary["source"] = "data/queries.csv"
    return pd.concat([df, summary], ignore_index=True)


def t16_r0_regressions_in_r4(R, Q, C):
    """R0's regressions (an item that passed and then fails) and the same items in R4.

    During repair: personal constraints passing before a changed round and failing after it (loop verifier),
    counted per constraint-round, as in T12. Initial to final plan: items passing in the initial plan and
    failing in the final plan (benchmark, from tables/t14_failure_repair.csv)."""
    pair = ("R0", "R4")
    c_test = C[C.split == "test"]
    kind_of = {(r.strategy, r.query_uid, r.constraint_index): r.kind for r in c_test.itertuples()}
    family = c_test.drop_duplicates("kind").set_index("kind").family.to_dict()

    def make_row(level, item, fam, counts, source):
        """counts: {strategy: (broken, at_risk, queries with a break or None)}."""
        out = dict(level=level, item=item, family=fam or "", flagged_by_matrix=("yes" if fam in FLAGGED else "no") if fam else "")
        rate = {}
        for s in pair:
            b, n, q = counts[s]
            rate[s] = b / n if n else None
            out[f"{s}_broken_over_at_risk"] = kn(b, n)
            out[f"{s}_rate_pct"] = pct(rate[s]) if n else None
            out[f"{s}_queries"] = q
        r0, r4 = rate["R0"], rate["R4"]
        out["lower_in_R4"] = None if r0 is None or r4 is None else "yes" if r4 < r0 else "no" if r4 > r0 else "same"
        out["source"] = source
        return out

    rows = []
    # During repair (loop verifier, every changed round).
    acc = {}
    for s in pair:
        for r in R[(R.split == "test") & (R.strategy == s) & R.changed].itertuples():
            broken = set(idx_list(r.pc_broken_idx))
            for i, st in enumerate(parse_state(r.pc_before), start=1):
                if st == "T":
                    a = acc.setdefault((s, kind_of.get((s, r.query_uid, i), "Other")), [0, 0, set()])
                    a[1] += 1
                    if i in broken:
                        a[0] += 1
                        a[2].add(r.query_uid)
    get = lambda s, k: acc.get((s, k), [0, 0, set()])
    kinds = sorted({k for (_, k), a in acc.items() if a[0]}, key=lambda k: (-get("R0", k)[0], -get("R4", k)[0], k))
    src = "data/rounds.csv (changed rounds; loop verifier before/after), data/constraints.csv"
    for k in kinds:
        rows.append(make_row("during repair", k, family.get(k), {s: (get(s, k)[0], get(s, k)[1], len(get(s, k)[2])) for s in pair}, src))
    total = {}
    for s in pair:
        mine = [a for (s2, _), a in acc.items() if s2 == s]
        total[s] = (sum(a[0] for a in mine), sum(a[1] for a in mine), len(set().union(*(a[2] for a in mine))))
    rows.append(make_row("during repair", "All personal constraints", None, total, src))

    # Initial to final plan (benchmark).
    t14 = pd.read_csv(HERE / "tables" / "t14_failure_repair.csv")
    src = "tables/t14_failure_repair.csv (benchmark, initial vs final plan)"
    for typ in ("personal", "commonsense"):
        t = t14[t14.type == typ]
        sub = t[t.strategy.isin(pair)]
        items = sub[sub.newly_failing > 0].item.unique()

        def counts(item):
            out = {}
            for s in pair:
                r = sub[(sub.item == item) & (sub.strategy == s)]
                fi, new = (int(r.failing_initial.iloc[0]), int(r.newly_failing.iloc[0])) if len(r) else (0, 0)
                n = int(t[t.item == item]["items"].max()) if typ == "personal" else int(((Q.split == "test") & (Q.strategy == s)).sum())
                out[s] = (new, n - fi, None)
            return out

        level = f"initial to final plan ({typ})"
        for item in sorted(items, key=lambda i: (-counts(i)["R0"][0], -counts(i)["R4"][0], i)):
            rows.append(make_row(level, item, family.get(item) if typ == "personal" else None, counts(item), src))
        total = {}
        for s in pair:
            ts = t[t.strategy == s]
            q = Q[(Q.split == "test") & (Q.strategy == s)]
            items_total = len(c_test[c_test.strategy == s]) if typ == "personal" else int(q.cs_total.sum())
            total[s] = (int(ts.newly_failing.sum()), items_total - int(ts.failing_initial.sum()), None)
        rows.append(make_row(level, f"All {typ} {'constraints' if typ == 'personal' else 'checks'}", None, total, src))
    df = pd.DataFrame(rows)
    for s in pair:
        df[f"{s}_queries"] = df[f"{s}_queries"].astype("Int64")
    return df


TRACE_RUNS = {"R0": "subset_test-r0", "R4": "subset_test-r4"}


def _hotel_change_steps(repo, strategy):
    """Per query: steps of changed rounds whose candidate plan books different hotels or rooms than the plan before."""
    root = repo / "experiments" / TRACE_RUNS[strategy]
    pattern = "queries/*/trials/R4-*.json" if strategy == "R4" else f"queries/*/{strategy}-*.json"
    initial = {}
    for path in root.glob(pattern):
        d = json.loads(path.read_text(encoding="utf-8"))
        initial[d["query_uid"]] = d.get("initial_raw_plan")
    attempts = sorted((json.loads(line) for line in (root / "attempts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()),
                      key=lambda a: (a["query_uid"], a["step"]))
    current, steps = {}, {}
    for a in attempts:
        uid = a["query_uid"]
        before = current.get(uid, initial.get(uid))
        if a.get("decision_reason") != "no_progress_unchanged" and _hotels(a.get("candidate_plan")) != _hotels(before):
            steps.setdefault(uid, []).append(a["step"])
        if a.get("accepted"):
            plan = a.get("accepted_plan_after") if a.get("accepted_plan_after") is not None else a.get("candidate_plan")
            if plan is not None:
                current[uid] = plan
    return steps


def t16b_r0_r4_case_trace(R, Q, C, repo):
    """Every test query in which R0 broke a personal constraint during repair, and R4 on the same query.

    Breaks: loop verifier, every round. Scores: benchmark, initial -> final plan. Cost: repair rounds only (as T5).
    R4_matrix_advice: the families and train risks that R4's prompt named in each round (commonsense rounds), and
    the constraint its advice recommended (personal rounds)."""
    R, Q, C = R[R.split == "test"], Q[Q.split == "test"], C[C.split == "test"]
    kind = {(r.strategy, r.query_uid, r.constraint_index): r.kind for r in C.itertuples()}
    hotel = {s: _hotel_change_steps(repo, s) for s in TRACE_RUNS}

    def breaks(s, uid):
        g = R[(R.strategy == s) & (R.query_uid == uid)].sort_values("step")
        return [f"step {r.step} {r.phase}: {kind.get((s, uid, i), 'Other')} #{i}" + ("" if r.accepted else " (rejected)")
                for r in g.itertuples() for i in idx_list(r.pc_broken_idx)]

    def advice(uid):
        g = R[(R.strategy == "R4") & (R.query_uid == uid)].sort_values("step")
        out = []
        for r in g.itertuples():
            if isinstance(r.cs_risk_families, str) and r.cs_risk_families:
                out.append(f"step {r.step} commonsense warning: {r.cs_risk_families}")
            if isinstance(r.rec_target_family, str) and r.rec_target_family:
                out.append(f"step {r.step} personal recommendation: #{int(r.rec_target_idx)} {r.rec_target_family} "
                           f"(fixed: {r.rec_fixed})")
        return "; ".join(out) or "none"

    uids = sorted((u for u in R[R.strategy == "R0"].query_uid.unique() if breaks("R0", u)),
                  key=lambda u: (-len(breaks("R0", u)), u))
    source = ("data/rounds.csv, data/queries.csv, data/constraints.csv; experiments/subset_test-r0 and "
              "subset_test-r4 (attempts.jsonl and checkpoints: hotel bookings)")
    rows = []
    for uid in uids:
        row = dict(query_uid=uid, group=Q[Q.query_uid == uid].group.iloc[0])
        for s in TRACE_RUNS:
            q = Q[(Q.strategy == s) & (Q.query_uid == uid)].iloc[0]
            b = breaks(s, uid)
            row.update({
                f"{s}_breaks": "; ".join(b) or "none", f"{s}_break_count": len(b),
                f"{s}_pc_passed": f"{int(q.pc_passed_initial)} -> {int(q.pc_passed_final)} / {int(q.pc_total)}",
                f"{s}_cs_failed": f"{int(q.cs_failed_initial)} -> {int(q.cs_failed_final)}",
                f"{s}_all_pass_final": int(q.all_pass_final),
                f"{s}_repair_tokens": int(q.tokens), f"{s}_repair_s": round(float(q.repair_s), 1),
                f"{s}_rounds": int(q.n_rounds), f"{s}_stop_reason": q.stop_reason,
                f"{s}_hotel_changed_steps": " ".join(map(str, hotel[s].get(uid, []))) or "none",
            })
        row["R4_matrix_advice"] = advice(uid)
        row["source"] = source
        rows.append(row)
    total = dict(query_uid="TOTAL (these queries)", group="", source=source)
    for s in TRACE_RUNS:
        q = Q[(Q.strategy == s) & Q.query_uid.isin(uids)]
        total[f"{s}_break_count"] = sum(r[f"{s}_break_count"] for r in rows)
        total[f"{s}_repair_tokens"] = int(q.tokens.sum())
        total[f"{s}_repair_s"] = round(float(q.repair_s.sum()), 1)
    df = pd.DataFrame(rows + [total])
    for c in df.columns:
        if c.endswith(("_rounds", "_all_pass_final")):
            df[c] = df[c].astype("Int64")
    return df


# ---------------------------------------------------------------- the tables as the .tex shows them
# report_tables/<label>.csv holds each table of docs/report/overleaf/evaluation_and_results.tex in its .tex layout,
# built from the tables above (tables/ keeps the full data tables).
KEY_TEST_ROWS = [  # (row label in the .tex, data table, column, divisor)
    ("All-pass ratio (%)", "t1_headline", "all_pass_pct", 1),
    ("LPR macro (%)", "t1_headline", "lpr_macro_pct", 1),
    ("EPR macro (%)", "t1_headline", "epr_macro_pct", 1),
    ("LPR micro (%)", "t1_headline", "lpr_micro_pct", 1),
    ("EPR micro (%)", "t1_headline", "epr_micro_pct", 1),
    ("Avg. Final PC-only rate (%)", "t1_headline", "avg_pc_pass_pct", 1),
    ("Avg. Final CS-only rate (%)", "t1_headline", "epr_micro_pct", 1),
    ("Avg. repair time (s)", "t5_efficiency", "repair_time_s_per_query", 1),
    ("Avg. tokens per query (k)", "t5_efficiency", "tokens_per_query", 1000),
]

# The three descriptive columns of the case-trace table, as written in the .tex from T16b's columns
# R*_breaks, R*_hotel_changed_steps, R4_stop_reason and R4_matrix_advice. Rows in the .tex order.
CASE_TRACE_TEXT = {
    "e20241028160914767827": ("Round 6 (commonsense): changed the hotel from 1 room of type 2 to 2 rooms of type 1, "
                              "and broke both room constraints",
                              "No break; hotel unchanged",
                              "accommodation 34.3% (the highest warning)"),
    "e20241028161037866126": ('Round 6 (commonsense): room type 2 -> 1; broke "room type 2"',
                              "No break; hotel unchanged; all-pass; loop stopped after 1 round (its verifier passed)",
                              "accommodation 34.3%"),
    "h20241029143921648851": ("Round 6 (commonsense): broke days / people count",
                              "No break",
                              "trip_specification 2.2% (weak)"),
    "e20241028161207342223": ("Round 1 (commonsense): days / people count, fixed again later",
                              "No break; loop stopped after 1 round (its verifier passed)",
                              "trip_specification 2.2%"),
    "h20241029143908194169": ("Round 2 (commonsense): days / people count, fixed again later",
                              "No break",
                              "trip_specification 2.2%"),
    "e20241028161340383778": ("12 breaks over rounds 1-6: budget, food cost, tickets, rooms",
                              "9 breaks, including rooms in rounds 2 and 5",
                              "Rooms ranked safest; R4 fixed them, then broke them again"),
}


def report_key_test_results(built):
    """Table tab:key_test_results: one row per metric, one column per strategy."""
    rows = []
    for label, table, col, divisor in KEY_TEST_ROWS:
        t = built[table].set_index("strategy")
        row = {"Metric": label}
        row.update({s: round(float(t.loc[s, col]) / divisor, 1) for s in STRATS})
        row["source"] = f"tables/{table}.csv, column {col}" + (f" / {divisor}" if divisor != 1 else "")
        rows.append(row)
    return pd.DataFrame(rows)


def report_r0_regressions_r4(built):
    """Table tab:r0-regressions-r4: T16 without the family column, with the .tex part names."""
    d = built["t16_r0_regressions_in_r4"]
    parts = {"during repair": "During repair: personal constraints",
             "initial to final plan (personal)": "Initial to final plan (benchmark): personal constraints",
             "initial to final plan (commonsense)": "Initial to final plan (benchmark): commonsense checks"}
    dash = lambda col: d[col].astype(object).where(d[col].notna() & (d[col].astype(str) != ""), "--")
    out = pd.DataFrame({"Part": d.level.map(parts), "Item": d["item"], "Flagged by matrix": dash("flagged_by_matrix")})
    for s in ("R0", "R4"):
        out[f"{s} broken / at risk"] = d[f"{s}_broken_over_at_risk"]
        out[f"{s} rate (%)"] = d[f"{s}_rate_pct"]
        out[f"{s} queries"] = dash(f"{s}_queries")
    out["Lower in R4?"] = d.lower_in_R4
    out["source"] = "tables/t16_r0_regressions_in_r4.csv"
    return out


def report_r0_r4_case_trace(built):
    """Table tab:r0-r4-case-trace: the numbers from T16b and the descriptive text of the .tex."""
    d = built["t16b_r0_r4_case_trace"].set_index("query_uid")
    traced = set(d.index) - {"TOTAL (these queries)"}
    assert traced == set(CASE_TRACE_TEXT), f"T16b queries changed: {sorted(traced ^ set(CASE_TRACE_TEXT))}"
    for uid, (_, r4_text, _) in CASE_TRACE_TEXT.items():  # the text must still agree with the trace
        assert r4_text.startswith("No break") == (d.loc[uid, "R4_break_count"] == 0), uid
        if "stopped after 1 round" in r4_text:
            assert d.loc[uid, "R4_rounds"] == 1, uid
    half_up = lambda x: int(float(x) + 0.5)
    rows = []
    for uid, (r0_text, r4_text, warning) in CASE_TRACE_TEXT.items():
        r = d.loc[uid]
        row = {"Query (group)": f"...{uid[-9:]} ({r.group})", "What R0 broke": r0_text}
        for s, text in (("R0", None), ("R4", r4_text)):
            if text is not None:
                row["R4 on the same query"] = text
            row[f"{s} PC passed (initial -> final / total)"] = r[f"{s}_pc_passed"]
            row[f"{s} CS failed (initial -> final)"] = r[f"{s}_cs_failed"]
            row[f"{s} tokens (k)"] = half_up(r[f"{s}_repair_tokens"] / 1000)
            row[f"{s} time (s)"] = half_up(r[f"{s}_repair_s"])
        row["R4's warning in that round"] = warning
        row["query_uid"] = uid
        row["source"] = "tables/t16b_r0_r4_case_trace.csv"
        rows.append(row)
    return pd.DataFrame(rows)


REPORT_TABLES = [  # (file name, .tex label, caption, builder)
    ("key_test_results", "tab:key_test_results", "Key held-out TEST results across repair strategies.",
     report_key_test_results),
    ("r0_regressions_r4", "tab:r0-regressions-r4", "R0's regressions and the same items in R4 (test, 30 queries).",
     report_r0_regressions_r4),
    ("r0_r4_case_trace", "tab:r0-r4-case-trace", "The six test queries in which R0 broke a personal constraint during "
     "repair, and R4 on the same queries.", report_r0_r4_case_trace),
]


# ---------------------------------------------------------------- main
TABLES = [
    ("t1_headline", "T1. Final-plan benchmark metrics per strategy (test, n = 30), with the initial-plan value beside each. The 95 % CI is a percentile bootstrap over queries (5,000 resamples).", t1_headline),
    ("t3_regression", "T3. Regression during repair (test). Round-level values use the loop verifier; the final-vs-initial column uses the benchmark.", t3_regression),
    ("t3c_regression_queries", "T3c. R0's queries with an accepted personal-constraint regression, and R2's queries where rollback rejected candidates: what the candidates fixed and broke (loop verifier) and how each query ended (benchmark).", t3c_regression_queries),
    ("t4_budget_use", "T4. How the six-round budget was used (test). A locked round is a no-op that follows a no-op in the same phase.", t4_budget_use),
    ("t5_efficiency", "T5. Repair cost per query (test). Nominal tokens add back the tokens the repeat-request cache saved.", t5_efficiency),
    ("t6_difficulty_effectiveness", "T6. Effectiveness by query difficulty (test, 10 queries per group).", t6_difficulty),
    ("t6b_difficulty_what_fails", "T6b. The three most frequent failures in the final plans, by difficulty group and strategy.", t6b_what_fails),
    ("t7b_train_headline", "T7b. Train split (n = 60), R0 to R3: the rates of Figure F1 and the repair cost per query. R1 train has no saved initial plans.", t7b_train_headline),
    ("t11_query_outcome_map", "T11. Analysis D: which queries pass every personal constraint, per strategy (1 = pass), at the start (init) and at the end (final); allpass = schema + commonsense + personal.", t11_outcome_map),
    ("t16_r0_regressions_in_r4", "T16. R0's regressions and the same items in R4: broken / at risk. During repair: personal constraints that passed before a changed round and failed after it (loop verifier; at risk counts constraint-rounds; queries = queries with a break). Initial to final plan: items that passed in the initial plan and fail in the final plan (benchmark). lower_in_R4 compares the rates.", t16_r0_regressions_in_r4),
    ("t16b_r0_r4_case_trace", "T16b. Every test query in which R0 broke a personal constraint during repair, traced in R0 and R4: the breaks (loop verifier), personal constraints passed and failed commonsense checks from the initial to the final plan (benchmark), repair tokens and time (repair rounds only), the steps that changed a hotel booking, and the advice R4's prompt gave in each round. The last row sums the cost.", t16b_r0_r4_case_trace),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", type=Path, default=HERE.parent)
    ap.add_argument("--data-dir", type=Path, default=HERE / "data")
    ap.add_argument("--output-dir", type=Path, default=HERE / "tables")
    ap.add_argument("--report-dir", type=Path, default=HERE / "report_tables")
    args = ap.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    built = {}
    R = pd.read_csv(args.data_dir / "rounds.csv")
    Q = pd.read_csv(args.data_dir / "queries.csv")
    C = pd.read_csv(args.data_dir / "constraints.csv")
    for col in ("loop_initial", "loop_final"):
        C[col] = C[col].map({True: True, False: False, "True": True, "False": False}).astype(object)
    ctx = dict(R=R, Q=Q, C=C, repo=args.repo_root)
    md = ["# Report tables", "",
          "Generated by `report_result_evaluations/build_report_tables.py` from `data/*.csv`. Do not edit by hand.",
          "", "Test split: 30 queries, 10 per difficulty group; one query is 3.3 points of a whole-split rate and 10 points of a group rate. "
          "Each strategy generated its own initial plan, so final levels mix the start with the repair; the change from the initial plan is shown beside every level. "
          "Round-level values come from the loop verifier (what the strategies saw); initial and final plan values come from the benchmark scorer.", ""]
    manifest = []
    for name, caption, fn in TABLES:
        import inspect
        params = inspect.signature(fn).parameters
        df = fn(**{k: ctx[k] for k in params})
        built[name] = df
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        show = df.drop(columns=["source"]) if "source" in df.columns else df
        md += [f"## {name.split('_')[0].upper()}: {caption}", "", to_markdown(show), "",
               f"Source: {'; '.join(sorted(set(map(str, df['source'])))) if 'source' in df.columns else name}", ""]
        has_ci = name in ("t1_headline", "t3_regression")
        manifest.append(dict(report_id=name.split("_")[0].upper(), kind="table", path=f"tables/{name}.csv",
                             source_script="report_result_evaluations/build_report_tables.py",
                             regenerate_cmd="python report_result_evaluations/run_all.py", has_ci=has_ci, caption=caption))
        print("wrote", path)
    report = args.report_dir
    report.mkdir(parents=True, exist_ok=True)
    md += ["# The tables of the .tex (report_tables/)", ""]
    for name, label, caption, fn in REPORT_TABLES:
        df = fn(built)
        path = report / f"{name}.csv"
        df.to_csv(path, index=False)
        md += [f"## {label}: {caption}", "", to_markdown(df.drop(columns=["source"])), "",
               f"Source: {'; '.join(sorted(set(map(str, df['source']))))}", ""]
        manifest.append(dict(report_id=label, kind="report table", path=f"report_tables/{name}.csv",
                             source_script="report_result_evaluations/build_report_tables.py",
                             regenerate_cmd="python report_result_evaluations/run_all.py", has_ci=False, caption=caption))
        print("wrote", path)
    (out / "REPORT_TABLES.md").write_text("\n".join(md), encoding="utf-8")
    pd.DataFrame(manifest).to_csv(out / "manifest_tables.csv", index=False)
    print("wrote", out / "REPORT_TABLES.md")



if __name__ == "__main__":
    main()
