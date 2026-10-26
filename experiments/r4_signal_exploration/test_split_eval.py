"""Out-of-split check: train the candidate-risk score on subset_train (R0 + R3),
score R3 subset_test candidates it has never seen. This mirrors R4's S1/S2 design."""
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from extract import load_rounds, effects, R0, R3, PROJECT
import quality_eval as Q   # builds the training rows and the feature function

R3_TEST = str(PROJECT / "experiments/subset_test-r3/queries/*/R3-*.json")
test_rows, _ = load_rounds(R3_TEST, "R3")
test = [r for r in test_rows if not r["unchanged"] and r["edits"]]

def labels(rows):
    dmg = np.array([int(any(k in ("break", "lost", "new_cs") for k, _ in effects(r))) for r in rows])
    brk = np.array([int(any(k in ("break", "lost") for k, _ in effects(r))) for r in rows])
    d = np.array([Q.violations(r["after"], r["after_cs"]) - Q.violations(r["before"], r["before_cs"]) for r in rows])
    return dmg, brk, (d < 0).astype(int), d

tr_dmg, tr_brk, tr_good, _ = labels(Q.rows)
te_dmg, te_brk, te_good, te_delta = labels(test)
Xtr = np.array([Q.features(r, "full") for r in Q.rows]); Xte = np.array([Q.features(r, "full") for r in test])
print(f"\n## Out-of-split: trained on {len(Q.rows)} subset_train candidates, tested on {len(test)} R3 subset_test candidates")
print(f"test: damaged {te_dmg.mean():.0%}, broke personal {te_brk.sum()}, good {te_good.mean():.0%}\n")
preds = {}
for name, y_tr, y_te in (("any damage", tr_dmg, te_dmg), ("breaks a personal constraint", tr_brk, te_brk), ("good candidate", tr_good, te_good)):
    m = LogisticRegression(C=1.0, max_iter=3000).fit(Xtr, y_tr)
    p = m.predict_proba(Xte)[:, 1]; preds[name] = p
    auc = roc_auc_score(y_te, p) if len(set(y_te)) == 2 else float("nan")
    print(f"- {name}: AUC {auc:.2f}")

# threshold fixed on TRAIN (30% riskiest there), applied to test
m_d = LogisticRegression(C=1.0, max_iter=3000).fit(Xtr, tr_dmg)
m_g = LogisticRegression(C=1.0, max_iter=3000).fit(Xtr, tr_good)
risk_tr = m_d.predict_proba(Xtr)[:, 1] - m_g.predict_proba(Xtr)[:, 1]
cut = np.quantile(risk_tr, 0.7)
risk_te = preds["any damage"] - preds["good candidate"]
rej = risk_te > cut
print(f"\nTrain-set 30% cut-off applied to test: rejects {rej.sum()} of {len(test)} ({rej.mean():.0%}); "
      f"personal breaks avoided {te_brk[rej].sum()}/{te_brk.sum()}; good lost {te_good[rej].sum()}/{te_good.sum()}; "
      f"net violation change {te_delta[~rej].sum():+d} vs accept-all {te_delta.sum():+d}")
rng = np.random.default_rng(0)
rand = [te_delta[np.setdiff1d(np.arange(len(test)), rng.choice(len(test), rej.sum(), replace=False))].sum() for _ in range(500)]
print(f"Random rejection of the same number: mean {np.mean(rand):+.1f}")
