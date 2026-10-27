"""Are the edit->effect odds ratios stable? Query bootstrap + R0-vs-R3 agreement."""
import random
import numpy as np
from sklearn.linear_model import LogisticRegression
from extract import load_rounds, effects, EDITS, R0, R3

r0, _ = load_rounds(R0, "R0"); r3, _ = load_rounds(R3, "R3")
rows = [r for r in r0 + r3 if not r["unchanged"] and r["edits"]]
cols = EDITS + ["is_commonsense_round", "is_R3"]
def X_of(rs, with_run=True):
    return np.array([[int(e in r["edits"]) for e in EDITS] + [int(r["phase"] == "commonsense")]
                     + ([int(r["run"] == "R3")] if with_run else []) for r in rs])
def has(r, kind, name):
    ev = effects(r)
    return (kind, name) in ev or (kind == "break" and ("lost", name) in ev)
PAIRS = [  # (outcome label, test, edit column)
    ("breaks hotel", lambda r: has(r, "break", "hotel"), "edit_hotel"),
    ("breaks trip", lambda r: has(r, "break", "trip"), "edit_structure"),
    ("breaks budget", lambda r: has(r, "break", "budget"), "edit_attraction"),
    ("breaks any personal", lambda r: any(k in ("break", "lost") for k, _ in effects(r)), "is_commonsense_round"),
    ("new cs_intercity", lambda r: has(r, "new_cs", "cs_intercity"), "edit_intercity"),
    ("new cs_inner_transport", lambda r: has(r, "new_cs", "cs_inner_transport"), "edit_inner_transport"),
    ("new cs_dining", lambda r: has(r, "new_cs", "cs_dining"), "edit_restaurant"),
    ("new cs_hotel", lambda r: has(r, "new_cs", "cs_hotel"), "edit_hotel"),
]
def fit_or(rs, test, col, with_run=True):
    y = np.array([int(test(r)) for r in rs])
    if y.sum() < 2 or y.sum() > len(y) - 2:
        return None
    names = EDITS + ["is_commonsense_round"] + (["is_R3"] if with_run else [])
    m = LogisticRegression(C=1.0, max_iter=2000).fit(X_of(rs, with_run), y)
    return float(np.exp(m.coef_[0][names.index(col)]))

uids = sorted({(r["run"], r["uid"]) for r in rows})
by_uid = {}
for r in rows:
    by_uid.setdefault((r["run"], r["uid"]), []).append(r)
random.seed(0)
boots = []
for _ in range(300):
    sample = [x for u in random.choices(uids, k=len(uids)) for x in by_uid[u]]
    boots.append(sample)

print("| outcome | edit | pooled OR | 90% bootstrap range | share of resamples with OR>1 | R0 alone | R3 alone |")
print("|---|---|---|---|---|---|---|")
for label, test, col in PAIRS:
    full = fit_or(rows, test, col)
    bs = [v for v in (fit_or(s, test, col) for s in boots) if v is not None]
    lo, hi = np.percentile(bs, [5, 95])
    a = fit_or([r for r in rows if r["run"] == "R0"], test, col, with_run=False)
    b = fit_or([r for r in rows if r["run"] == "R3"], test, col, with_run=False)
    f = lambda v: "–" if v is None else f"{v:.1f}"
    print(f"| {label} | {col.replace('edit_', '')} | {full:.1f} | {lo:.1f}–{hi:.1f} | {np.mean([v > 1 for v in bs]):.0%} | {f(a)} | {f(b)} |")
