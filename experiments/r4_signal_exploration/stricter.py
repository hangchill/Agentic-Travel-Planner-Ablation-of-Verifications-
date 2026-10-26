"""Stricter checks:
 S1. LOQO skill against each COLUMN's own rate (does the row add information?).
 S2. Multivariable model: separate the effect of each edit type when several co-occur.
"""
import json
from collections import Counter, defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
from extract import load_rounds, effects, cs_kind, CS_KINDS, EDITS, R0, R3
import approaches as A   # reuses a0..a5 builders (module runs its report on import; output already saved)

def loqo_column(obs, prior=5):
    """Brier skill of shrunk cell rate vs the destination column's rate, both from other queries."""
    cell, col, ucell, ucol = (defaultdict(lambda: [0.0, 0.0]) for _ in range(4))
    for uid, (r, c), y, w in obs:
        for d, k in ((cell, (r, c)), (col, c), (ucell, (uid, r, c)), (ucol, (uid, c))):
            d[k][0] += w * y; d[k][1] += w
    bm = bb = 0.0
    for uid, (r, c), y, w in obs:
        ce, cn = col[c][0] - ucol[(uid, c)][0], col[c][1] - ucol[(uid, c)][1]
        base = ce / cn if cn else 0.5
        e, n = cell[(r, c)][0] - ucell[(uid, r, c)][0], cell[(r, c)][1] - ucell[(uid, r, c)][1]
        p = (e + prior * base) / (n + prior)
        bm += w * (y - p) ** 2; bb += w * (y - base) ** 2
    return 1 - bm / bb if bb else None

out = []
for label, rows in (("R0", A.r0_rows), ("R3", A.r3_rows), ("Pooled", A.r0_rows + A.r3_rows)):
    res = {}
    for name, fn in (("A0 current", A.a0), ("A1 event matrix", A.a1), ("A2 edit→effect", A.a2), ("A5 commonsense kind→kind", A.a5)):
        _, obs = fn(rows)
        res[name] = loqo_column(obs)
    out.append((label, res))

print("\n## S1 — LOQO skill vs each column's own rate (does the row add information?)\n")
print("| artifact | R0 | R3 | pooled |\n|---|---|---|---|")
for name in out[0][1]:
    vals = [r[name] for _, r in out]
    print(f"| {name} | " + " | ".join("–" if v is None else f"{v:+.2f}" for v in vals) + " |")

# ------------------------------------------------ S2 multivariable edit model
print("\n## S2 — edit effects separated (logistic regression, pooled R0+R3 changed rounds)\n")
rows = [r for r in A.r0_rows + A.r3_rows if not r["unchanged"] and r["edits"]]
X = np.array([[int(e in r["edits"]) for e in EDITS] + [int(r["phase"] == "commonsense"), int(r["run"] == "R3")] for r in rows])
cols = EDITS + ["is_commonsense_round", "is_R3"]
outcomes = {}
for r in rows:
    pass
def outcome_vector(test):
    return np.array([int(test(r)) for r in rows])
targets = {
    "breaks any personal": lambda r: any(k in ("break", "lost") for k, _ in effects(r)),
    "breaks hotel": lambda r: ("break", "hotel") in effects(r) or ("lost", "hotel") in effects(r),
    "breaks budget": lambda r: ("break", "budget") in effects(r) or ("lost", "budget") in effects(r),
    "breaks trip": lambda r: ("break", "trip") in effects(r) or ("lost", "trip") in effects(r),
    "new cs_inner_transport": lambda r: ("new_cs", "cs_inner_transport") in effects(r),
    "new cs_intercity": lambda r: ("new_cs", "cs_intercity") in effects(r),
    "new cs_dining": lambda r: ("new_cs", "cs_dining") in effects(r),
    "new cs_hotel": lambda r: ("new_cs", "cs_hotel") in effects(r),
}
print(f"{len(rows)} changed rounds. Cells: odds ratio of the outcome when that edit is present, holding the other edits fixed (>1 raises risk). Bold = |log OR| > 0.7.\n")
print("| outcome (base rate) | " + " | ".join(c.replace("edit_", "") for c in cols) + " |")
print("|---" * (len(cols) + 1) + "|")
for name, test in targets.items():
    y = outcome_vector(test)
    if y.sum() < 5 or y.sum() > len(y) - 5:
        continue
    m = LogisticRegression(C=1.0, max_iter=2000).fit(X, y)
    ors = np.exp(m.coef_[0])
    cells = [f"**{o:.1f}**" if abs(np.log(o)) > 0.7 else f"{o:.1f}" for o in ors]
    print(f"| {name} ({y.mean():.0%}) | " + " | ".join(cells) + " |")

# ------------------------------------------------ S3 how often edits co-occur
co = Counter(len(r["edits"]) for r in rows)
print(f"\nEdits per changed round: {dict(sorted(co.items()))} (most rounds change several things at once)")
