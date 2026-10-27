"""Can the risk profile tell good repair candidates from bad ones, and what would using it achieve?

Every changed candidate plan (pooled R0+R3 subset_train) gets a score from a model
trained only on OTHER queries (5-fold, grouped by query). We measure:
  - AUC for 'did damage' (any personal break/lost or new commonsense error)
  - AUC for 'was a good candidate' (net violations went down)
and simulate R4 rejecting the riskiest x% (plan kept as before, like R2's rollback).
"""
import random
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from extract import load_rounds, effects, cs_kind, SHORT, EDITS, R0, R3
from r4_artifact import needed_edits, failing, passing

r0, _ = load_rounds(R0, "R0"); r3, _ = load_rounds(R3, "R3")
rows = [r for r in r0 + r3 if not r["unchanged"] and r["edits"]]

def violations(personal, cs):
    return sum(s is not True for s in personal) + len(cs)
def features(r, kind):
    base = [int(r["phase"] == "commonsense"), int(r["run"] == "R3")]
    if kind == "phase_only":
        return base
    f = base + [int(e in r["edits"]) for e in EDITS]
    if kind == "edits":
        return f
    unneeded = r["edits"] - needed_edits(r)
    return f + [len(unneeded & {"edit_hotel", "edit_intercity", "edit_restaurant", "edit_attraction", "edit_structure"}),
                len(passing(r)), len(failing(r)), violations(r["before"], r["before_cs"])]

damage = np.array([int(any(k in ("break", "lost", "new_cs") for k, _ in effects(r))) for r in rows])
delta = np.array([violations(r["after"], r["after_cs"]) - violations(r["before"], r["before_cs"]) for r in rows])
good = (delta < 0).astype(int)
pers_break = np.array([int(any(k in ("break", "lost") for k, _ in effects(r))) for r in rows])
groups = np.array([f"{r['run']}:{r['uid']}" for r in rows])
print(f"{len(rows)} changed candidates | damaged {damage.mean():.0%} | good (net fewer violations) {good.mean():.0%} | broke a personal constraint {pers_break.mean():.0%}\n")

def oof(kind, y):
    X = np.array([features(r, kind) for r in rows]); p = np.zeros(len(rows))
    for tr, te in GroupKFold(5).split(X, y, groups):
        m = LogisticRegression(C=1.0, max_iter=3000).fit(X[tr], y[tr]); p[te] = m.predict_proba(X[te])[:, 1]
    return p

print("## How well the score separates candidates (AUC on held-out queries; 0.5 = no better than chance)\n")
print("| score built from | damage (any) | broke a personal constraint | good candidate |\n|---|---|---|---|")
scores = {}
for kind, label in (("phase_only", "round type only (baseline)"), ("edits", "+ which parts were edited"),
                    ("full", "+ unneeded edits, constraint context")):
    pd_, pb, pg = oof(kind, damage), oof(kind, pers_break), oof(kind, good)
    scores[kind] = (pd_, pb, pg)
    print(f"| {label} | {roc_auc_score(damage, pd_):.2f} | {roc_auc_score(pers_break, pb):.2f} | {roc_auc_score(good, pg):.2f} |")

# bootstrap CI for the full model's AUCs (resample queries)
random.seed(1)
ug = sorted(set(groups)); idx_by = {g: np.where(groups == g)[0] for g in ug}
pd_, pb, pg = scores["full"]
def boot(y, p):
    vals = []
    for _ in range(500):
        idx = np.concatenate([idx_by[g] for g in random.choices(ug, k=len(ug))])
        if len(set(y[idx])) == 2: vals.append(roc_auc_score(y[idx], p[idx]))
    return np.percentile(vals, [5, 95])
print("\nFull model, 90% range over query resamples: "
      f"damage {boot(damage, pd_)[0]:.2f}–{boot(damage, pd_)[1]:.2f}, broke personal {boot(pers_break, pb)[0]:.2f}–{boot(pers_break, pb)[1]:.2f}, "
      f"good {boot(good, pg)[0]:.2f}–{boot(good, pg)[1]:.2f}")

print("\n## Effect if R4 rejected the riskiest candidates (kept the previous plan instead)\n")
print("Net change = total violations across all candidates (negative = better). Accept-all net change: "
      f"{delta.sum():+d} over {len(rows)} candidates.\n")
print("| reject riskiest | candidates rejected | personal breaks avoided | net-improving candidates lost | net violation change | vs random rejection (mean of 200) |")
print("|---|---|---|---|---|---|")
risk = scores["full"][0] - scores["full"][2]       # high damage risk, low chance of being good
order = np.argsort(-risk)
for frac in (0.1, 0.2, 0.3, 0.5):
    k = int(round(frac * len(rows))); rej = order[:k]
    keep = np.ones(len(rows), bool); keep[rej] = False
    net = delta[keep].sum()
    rand = []
    for _ in range(200):
        rr = np.random.default_rng(_).choice(len(rows), k, replace=False)
        kk = np.ones(len(rows), bool); kk[rr] = False; rand.append(delta[kk].sum())
    print(f"| {frac:.0%} | {k} | {pers_break[rej].sum()}/{pers_break.sum()} | {good[rej].sum()}/{good.sum()} | {net:+d} | {np.mean(rand):+.1f} |")

print("\n## Same, split by round type (where the score helps most)\n")
for phase in ("personal", "commonsense"):
    m = np.array([r["phase"] == phase for r in rows])
    if len(set(damage[m])) == 2 and len(set(good[m])) == 2:
        print(f"- {phase} rounds (n={m.sum()}): AUC damage {roc_auc_score(damage[m], pd_[m]):.2f}, "
              f"broke personal {roc_auc_score(pers_break[m], pb[m]) if len(set(pers_break[m])) == 2 else float('nan'):.2f}, good {roc_auc_score(good[m], pg[m]):.2f}")
