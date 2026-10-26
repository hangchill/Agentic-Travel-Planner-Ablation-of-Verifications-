"""Try every approach for turning R0 subset_train results into R4 evidence.

Each approach yields cells {(row, col): (events, chances)}. For each we report
density (cells with support, cells with events) and a leave-one-query-out (LOQO)
check: predict each held-out query's outcomes from the other queries' cells and
compare the Brier score with a single global rate. Positive 'skill' = the
artifact carries signal that generalises across queries.
"""
import json, math, re, sys
from collections import Counter, defaultdict
from extract import (load_rounds, effects, cs_kind, SHORT, CS_KINDS, EDITS, R0, R3, PROJECT)

OUT = []
def emit(text=""):
    OUT.append(text); print(text)

def pct(x): return "–" if x is None else f"{x:.0%}"

# ----------------------------------------------------------------- helpers
def table(cells, rows, cols, title, min_support=1, fmt="ratio"):
    emit(f"\n**{title}**\n")
    emit("| | " + " | ".join(cols) + " |")
    emit("|---" * (len(cols) + 1) + "|")
    for r in rows:
        line = []
        for c in cols:
            ev, n = cells.get((r, c), (0, 0))
            if n < min_support or n == 0:
                line.append("–")
            elif fmt == "ratio":
                line.append(f"{ev:.3g}/{n:.3g}" if ev else f"0/{n:.3g}")
            else:
                line.append(f"{ev / n:.0%} ({n:.3g})")
        emit(f"| **{r}** | " + " | ".join(line) + " |")

def density(cells):
    supported = [k for k, (e, n) in cells.items() if n > 0]
    nonzero = [k for k, (e, n) in cells.items() if n > 0 and e > 0]
    supports = sorted(n for e, n in cells.values() if n > 0)
    med = supports[len(supports) // 2] if supports else 0
    return len(supported), len(nonzero), med

def loqo(observations):
    """observations: list of (uid, cell, outcome 0/1, weight). Brier skill vs global rate."""
    by_cell = defaultdict(lambda: [0.0, 0.0]); by_uid_cell = defaultdict(lambda: [0.0, 0.0])
    tot = [0.0, 0.0]
    for uid, cell, y, w in observations:
        by_cell[cell][0] += w * y; by_cell[cell][1] += w
        by_uid_cell[(uid, cell)][0] += w * y; by_uid_cell[(uid, cell)][1] += w
        tot[0] += w * y; tot[1] += w
    uid_tot = defaultdict(lambda: [0.0, 0.0])
    for uid, cell, y, w in observations:
        uid_tot[uid][0] += w * y; uid_tot[uid][1] += w
    b_model = b_base = wsum = 0.0
    for uid, cell, y, w in observations:
        e, n = by_cell[cell]; ue, un = by_uid_cell[(uid, cell)]
        ge, gn = tot[0] - uid_tot[uid][0], tot[1] - uid_tot[uid][1]
        base = ge / gn if gn else 0.5
        # shrink the held-out cell rate toward the held-out global rate (prior worth 5)
        p = ((e - ue) + 5 * base) / ((n - un) + 5)
        b_model += w * (y - p) ** 2; b_base += w * (y - base) ** 2; wsum += w
    if not wsum or not b_base:
        return None
    return 1 - b_model / b_base

def shrink(cells, prior_strength=5, by_row=True):
    """Hierarchical shrinkage: cell -> its row rate -> global rate."""
    ge = sum(e for e, n in cells.values()); gn = sum(n for e, n in cells.values())
    g = ge / gn if gn else 0
    row = defaultdict(lambda: [0.0, 0.0])
    for (r, c), (e, n) in cells.items():
        row[r][0] += e; row[r][1] += n
    out = {}
    for (r, c), (e, n) in cells.items():
        re_, rn = row[r]
        row_rate = (re_ + prior_strength * g) / (rn + prior_strength)
        out[(r, c)] = ((e + prior_strength * row_rate) / (n + prior_strength), n)
    return out, g

def summary_line(name, cells, skill, note=""):
    s, nz, med = density(cells)
    emit(f"\n> **{name}** — cells with data: {s}, non-zero: {nz} ({nz / s:.0%} of supported)"
         f" | median support {med:.3g} | LOQO Brier skill vs global rate: "
         f"{'n/a' if skill is None else f'{skill:+.2f}'} {note}")
    return dict(name=name, supported=s, nonzero=nz, median_support=med, skill=skill)

# ----------------------------------------------------------------- data
r0_rows, r0_states = load_rounds(R0, "R0")
r3_rows, r3_states = load_rounds(R3, "R3")
RESULTS = []

def source_weights(row):
    """Who 'caused' a round: personal target families (split credit) or commonsense repair."""
    if row["phase"] == "commonsense":
        return {"commonsense repair": 1.0}
    t = [i for i in row["targets"] if i in row["fam"]]
    if not t:
        return {}
    w = defaultdict(float)
    for i in t:
        w[SHORT[row["fam"][i]]] += 1 / len(row["targets"])
    return w

PERSONAL = ["trip", "party", "budget", "hotel", "dining", "attraction", "transport"]

def passing_families(row):
    fams = defaultdict(list)
    for i, f in row["fam"].items():
        fams[SHORT[f]].append(i)
    return {f: idx for f, idx in fams.items() if all(row["before"][i - 1] is True for i in idx)}

# ======================================================== A0 baseline (current)
def a0(rows):
    cells = defaultdict(lambda: [0.0, 0.0]); obs = []
    for r in rows:
        if r["phase"] != "personal" or len(r["targets"]) != 1 or r["targets"][0] not in r["fam"]:
            continue
        if r["before"][r["targets"][0] - 1] is not False:
            continue
        src = SHORT[r["fam"][r["targets"][0]]]
        for f, idx in passing_families(r).items():
            if f == src or any(r["after"][i - 1] is None for i in idx):
                continue
            y = int(any(r["after"][i - 1] is False for i in idx))
            cells[(src, f)][0] += y; cells[(src, f)][1] += 1; obs.append((r["uid"], (src, f), y, 1))
    return {k: tuple(v) for k, v in cells.items()}, obs

# ======================================================== A1 event matrix
def a1(rows, include_lost=True):
    """Changed rounds only; split credit; commonsense source row; destinations =
    personal break(/lost) per family and new commonsense error per kind."""
    cells = defaultdict(lambda: [0.0, 0.0]); obs = []
    for r in rows:
        if r["unchanged"]:
            continue
        src = source_weights(r)
        if not src:
            continue
        passing = passing_families(r)
        new_kinds = {cs_kind(e) for e in (Counter(r["after_cs"]) - Counter(r["before_cs"]))}
        dests = {}
        for f, idx in passing.items():
            after = [r["after"][i - 1] for i in idx]
            if not include_lost and any(a is None for a in after):
                continue
            dests["break:" + f] = int(any(a is False or (include_lost and a is None) for a in after))
        for k in CS_KINDS:
            dests["new " + k] = int(k in new_kinds)
        for s, w in src.items():
            for d, y in dests.items():
                if d == "break:" + s:
                    continue
                cells[(s, d)][0] += w * y; cells[(s, d)][1] += w; obs.append((r["uid"], (s, d), y, w))
    return {k: tuple(v) for k, v in cells.items()}, obs

# ======================================================== A2 edit-type -> effect
def a2(rows):
    cells = defaultdict(lambda: [0.0, 0.0]); obs = []
    for r in rows:
        if r["unchanged"] or not r["edits"]:
            continue
        ev = effects(r)
        passing = passing_families(r)
        before_kinds = {cs_kind(e) for e in r["before_cs"]}
        targets = {}
        for f in passing:
            targets["breaks " + f] = int(("break", f) in ev or ("lost", f) in ev)
        failing = {SHORT[r["fam"][i]] for i, s in enumerate(r["before"], 1) if s is False and i in r["fam"]}
        for f in failing:
            targets["fixes " + f] = int(("fix", f) in ev)
        for k in CS_KINDS:
            targets["new " + k] = int(("new_cs", k) in ev)
            if k in before_kinds:
                targets["clears " + k] = int(("fixed_cs", k) in ev)
        for e in r["edits"]:
            for d, y in targets.items():
                cells[(e, d)][0] += y; cells[(e, d)][1] += 1; obs.append((r["uid"], (e, d), y, 1))
    return {k: tuple(v) for k, v in cells.items()}, obs

# ======================================================== A3 co-failure lift
def a3(states):
    """Across every plan state seen: P(j failing | i failing) / P(j failing)."""
    feats = []
    for s in states:
        present = defaultdict(list)
        for i, f in s["fam"].items():
            present[SHORT[f]].append(s["personal"][i - 1] if i - 1 < len(s["personal"]) else None)
        f_fail = {f: any(v is False for v in vals) for f, vals in present.items()}
        kinds = {cs_kind(e) for e in s["cs"]}
        row = {("P:" + f): v for f, v in f_fail.items()}
        for k in CS_KINDS:
            row[k] = k in kinds
        feats.append((s["uid"], row))
    names = sorted({k for _, r in feats for k in r})
    cells = {}; obs = []
    for a in names:
        for b in names:
            if a == b: continue
            both = [r for _, r in feats if a in r and b in r]
            if not both: continue
            given = [r for r in both if r[a]]
            base = sum(r[b] for r in both) / len(both)
            cond = sum(r[b] for r in given) / len(given) if given else None
            cells[(a, b)] = (cond, base, len(given), len(both))
    return cells, feats

# ======================================================== A4 fixability profile
def a4(rows):
    prof = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["phase"] != "personal":
            continue
        for s, w in source_weights(r).items():
            p = prof[s]; p["rounds"] += w
            if r["unchanged"]:
                p["unchanged"] += w; continue
            p["changed"] += w
            fixed = {f for k, f in effects(r) if k == "fix"}
            p["fixed"] += w * (s in fixed)
    return prof

# ======================================================== A5 commonsense kind -> kind
def a5(rows):
    cells = defaultdict(lambda: [0.0, 0.0]); obs = []
    for r in rows:
        if r["phase"] != "commonsense" or r["unchanged"]:
            continue
        before = Counter(cs_kind(e) for e in r["before_cs"])
        if not before: continue
        new = {cs_kind(e) for e in (Counter(r["after_cs"]) - Counter(r["before_cs"]))}
        cleared = {cs_kind(e) for e in (Counter(r["before_cs"]) - Counter(r["after_cs"]))}
        w = {k: n / sum(before.values()) for k, n in before.items()}
        for k, wk in w.items():
            dests = {"clears " + k: int(k in cleared)}
            dests.update({"new " + d: int(d in new) for d in CS_KINDS})
            for d, y in dests.items():
                cells[(k, d)][0] += wk * y; cells[(k, d)][1] += wk; obs.append((r["uid"], (k, d), y, wk))
    return {k: tuple(v) for k, v in cells.items()}, obs

# ======================================================== A6 budget margin (continuous)
BUDGET_RE = re.compile(r"total_cost\s*<=\s*([0-9.]+)")
def plan_cost(plan):
    total = 0.0
    for day in plan or []:
        for act in day.get("activities") or []:
            c = act.get("cost")
            total += float(c) if isinstance(c, (int, float)) else 0.0
            for leg in act.get("transports") or [] if isinstance(act.get("transports"), list) else []:
                lc = leg.get("cost") if isinstance(leg, dict) else None
                total += float(lc) if isinstance(lc, (int, float)) else 0.0
    return total

def a6(pattern):
    import glob
    per_edit = defaultdict(list); over = []
    from extract import plan_edits
    for path in glob.glob(pattern):
        res = json.load(open(path, encoding="utf-8"))
        hist = res["repair_history"]
        if len(hist) < 2: continue
        hl = [d["hard_logic_py"] for d in hist[1]["repair_attempt"]["constraint_descriptors"]]
        limits = [float(m.group(1)) for h in hl for m in [BUDGET_RE.search(h)] if m]
        if not limits: continue
        limit = min(limits); cur = res["initial_raw_plan"]
        over.append(plan_cost(cur) / limit - 1)
        for e in hist[1:]:
            cand = e.get("candidate_plan")
            if cand is None: continue
            edits = plan_edits(cur, cand)
            if edits:
                delta = (plan_cost(cand) - plan_cost(cur)) / limit
                for ed in edits: per_edit[ed].append(delta)
            if e["repair_attempt"]["accepted"]: cur = cand
    return per_edit, over

# ================================================================== run all
def run(rows, states, label, pattern):
    emit(f"\n## {label}")
    c0, o0 = a0(rows)
    table(c0, PERSONAL, PERSONAL, "A0 — current matrix (single personal target, all rounds)")
    RESULTS.append({**summary_line(f"{label} A0 current", c0, loqo(o0)), "run": label})

    c1, o1 = a1(rows)
    srcs = ["commonsense repair"] + PERSONAL
    dests = ["break:" + f for f in PERSONAL] + ["new " + k for k in CS_KINDS]
    table(c1, srcs, dests, "A1 — event matrix (changed rounds, split credit, commonsense row, breaks incl. lost + new commonsense errors)", fmt="pct")
    RESULTS.append({**summary_line(f"{label} A1 event matrix", c1, loqo(o1)), "run": label})
    sh, g = shrink(c1)
    table({k: (p * n, n) if n else (0, 0) for k, (p, n) in sh.items()}, srcs, dests,
          f"A1 shrunk toward row → global rate (global {g:.0%}; prior worth 5 rounds)", fmt="pct")

    c2, o2 = a2(rows)
    d2 = (["breaks " + f for f in PERSONAL] + ["fixes " + f for f in PERSONAL]
          + ["new " + k for k in CS_KINDS] + ["clears " + k for k in CS_KINDS])
    d2 = [d for d in d2 if any(c2.get((e, d), (0, 0))[1] for e in EDITS)]
    table(c2, EDITS, d2, "A2 — what the LLM edited → what happened (changed rounds)", fmt="pct")
    RESULTS.append({**summary_line(f"{label} A2 edit→effect", c2, loqo(o2)), "run": label})

    c3, feats = a3(states)
    names = sorted({k for _, r in feats for k in r})
    emit(f"\n**A3 — co-failure lift across {len(states)} plan states: P(column fails | row fails) ÷ P(column fails); shown when row fails in ≥5 states**\n")
    emit("| row fails → | " + " | ".join(n.replace("P:", "") for n in names) + " |")
    emit("|---" * (len(names) + 1) + "|")
    lifts = {}
    for a in names:
        line = []
        for b in names:
            c = c3.get((a, b))
            if a == b or not c or c[0] is None or c[2] < 5 or not c[1]:
                line.append("–"); continue
            lift = c[0] / c[1]; lifts[(a, b)] = lift
            line.append(f"{lift:.1f}×")
        emit(f"| **{a.replace('P:', '')}** | " + " | ".join(line) + " |")
    strong = sum(1 for v in lifts.values() if v >= 1.5 or v <= 0.67)
    emit(f"\n> **{label} A3 co-failure** — pairs estimated: {len(lifts)}, clearly associated (lift ≥1.5× or ≤0.67×): {strong}")
    RESULTS.append(dict(name=f"{label} A3 co-failure", supported=len(lifts), nonzero=strong, median_support=None, skill=None, run=label))

    prof = a4(rows)
    emit("\n**A4 — fixability profile (personal rounds)**\n")
    emit("| type | rounds | plan unchanged | target fixed (of changed) |\n|---|---|---|---|")
    for f, p in sorted(prof.items(), key=lambda kv: -kv[1]["rounds"]):
        emit(f"| {f} | {p['rounds']:.3g} | {pct(p['unchanged'] / p['rounds'])} | "
             f"{pct(p['fixed'] / p['changed']) if p['changed'] else '–'} ({p['changed']:.3g} changed) |")

    c5, o5 = a5(rows)
    d5 = ["clears " + k for k in CS_KINDS] + ["new " + k for k in CS_KINDS]
    d5 = [d for d in d5 if any(c5.get((k, d), (0, 0))[1] for k in CS_KINDS)]
    table(c5, CS_KINDS, d5, "A5 — commonsense rounds: error kind being fixed → cleared it / new error kinds", fmt="pct")
    RESULTS.append({**summary_line(f"{label} A5 commonsense kind→kind", c5, loqo(o5)), "run": label})

    per_edit, over = a6(pattern)
    emit(f"\n**A6 — budget slack (continuous)**: {len(over)} budget queries; start {sum(o > 0 for o in over)} over budget "
         f"(median {sorted(over)[len(over) // 2]:+.0%} of limit). Cost change per edit, as % of the budget:\n")
    emit("| edit | rounds | mean Δcost | share that lowered cost |\n|---|---|---|---|")
    for ed in EDITS:
        v = per_edit.get(ed) or []
        if v:
            emit(f"| {ed} | {len(v)} | {sum(v) / len(v):+.1%} | {sum(x < 0 for x in v) / len(v):.0%} |")

emit("# Exploration output")
run(r0_rows, r0_states, "R0 subset_train", R0)
run(r3_rows, r3_states, "R3 subset_train (old loop)", R3)

# ======================================================== A7 pooling R0 + R3
pooled = r0_rows + r3_rows
c1p, o1p = a1(pooled)
emit("\n## A7 — pooled R0 + R3 subset_train (S2-style)")
RESULTS.append({**summary_line("Pooled A1 event matrix", c1p, loqo(o1p)), "run": "pooled"})
c2p, o2p = a2(pooled)
RESULTS.append({**summary_line("Pooled A2 edit→effect", c2p, loqo(o2p)), "run": "pooled"})
srcs = ["commonsense repair"] + PERSONAL
dests = ["break:" + f for f in PERSONAL] + ["new " + k for k in CS_KINDS]
table(c1p, srcs, dests, "Pooled A1 event matrix", fmt="pct")

emit("\n## Scoreboard")
emit("| artifact | cells with data | non-zero cells | median support | LOQO skill |\n|---|---|---|---|---|")
for r in RESULTS:
    emit(f"| {r['name']} | {r['supported']} | {r['nonzero']} | {r['median_support'] if r['median_support'] is not None else '–'} | "
         + ("–" if r["skill"] is None else f"{r['skill']:+.2f}") + " |")
json.dump(RESULTS, open("scoreboard.json", "w"), indent=1, default=str)
open("exploration_output.md", "w", encoding="utf-8").write("\n".join(OUT))
