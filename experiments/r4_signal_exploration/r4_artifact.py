"""(1) fix levers, (2) avoidable-damage estimate, (3) prototype R4 risk profile JSON."""
import json, random
from collections import Counter, defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
from extract import load_rounds, effects, cs_kind, SHORT, CS_KINDS, EDITS, R0, R3

r0, _ = load_rounds(R0, "R0"); r3, _ = load_rounds(R3, "R3")
pooled = r0 + r3
changed = [r for r in pooled if not r["unchanged"] and r["edits"]]

def failing(r):
    return {SHORT[r["fam"][i]] for i, s in enumerate(r["before"], 1) if s is False and i in r["fam"]}
def passing(r):
    fams = defaultdict(list)
    for i, f in r["fam"].items(): fams[SHORT[f]].append(i)
    return {f for f, idx in fams.items() if all(r["before"][i - 1] is True for i in idx)}

# ----------------------------------------------------------- (1) fix levers
print("## (1) Which edits go with fixing a failing constraint (pooled changed rounds where it was failing)\n")
print("| failing type | rounds | fixed | fix rate when edit present vs absent |\n|---|---|---|---|")
levers = {}
for fam in ("budget", "hotel", "trip", "dining", "attraction"):
    rs = [r for r in changed if fam in failing(r) and r["phase"] == "personal"]
    if not rs: continue
    fixed = [("fix", fam) in effects(r) for r in rs]
    parts = []
    for e in EDITS:
        with_e = [f for r, f in zip(rs, fixed) if e in r["edits"]]
        without = [f for r, f in zip(rs, fixed) if e not in r["edits"]]
        if len(with_e) >= 3 and len(without) >= 3:
            parts.append(f"{e.replace('edit_', '')} {np.mean(with_e):.0%} vs {np.mean(without):.0%} (n={len(with_e)})")
            levers.setdefault(fam, {})[e] = dict(with_edit=float(np.mean(with_e)), without=float(np.mean(without)), n=len(with_e))
    print(f"| {fam} | {len(rs)} | {sum(fixed)} | {'; '.join(parts) or 'too few rounds'} |")

# ----------------------------------------------------------- (2) avoidable damage
NEEDED_FOR_PERSONAL = {"hotel": {"edit_hotel"}, "budget": {"edit_hotel", "edit_intercity", "edit_restaurant", "edit_attraction", "edit_inner_transport"},
                       "trip": {"edit_structure", "edit_intercity", "edit_hotel"}, "dining": {"edit_restaurant"},
                       "attraction": {"edit_attraction"}, "transport": {"edit_inner_transport", "edit_intercity"},
                       "party": {"edit_hotel", "edit_intercity"}}
NEEDED_FOR_CS = {"cs_hotel": {"edit_hotel"}, "cs_intercity": {"edit_intercity"}, "cs_inner_transport": {"edit_inner_transport"},
                 "cs_dining": {"edit_restaurant"}, "cs_attraction": {"edit_attraction"}, "cs_time_order": set(), "cs_other": set()}
RISKY = {("break", "hotel"): {"edit_hotel"}, ("break", "trip"): {"edit_structure", "edit_intercity", "edit_hotel", "edit_attraction", "edit_restaurant"},
         ("break", "budget"): {"edit_attraction"}, ("new_cs", "cs_intercity"): {"edit_intercity"},
         ("new_cs", "cs_inner_transport"): {"edit_inner_transport"}, ("new_cs", "cs_dining"): {"edit_restaurant"},
         ("new_cs", "cs_hotel"): {"edit_hotel"}}
def needed_edits(r):
    need = {"edit_times"}
    if r["phase"] == "personal":
        for f in failing(r): need |= NEEDED_FOR_PERSONAL.get(f, set())
        if any(s is None for s in r["before"]): need |= {"edit_inner_transport"}   # unknowns usually = transport translation
    else:
        for k in {cs_kind(e) for e in r["before_cs"]}: need |= NEEDED_FOR_CS.get(k, set())
    return need
print("\n## (2) Damage that came with an edit the round did not need\n")
print("| damage | events | of which the round made an unneeded risky edit |\n|---|---|---|")
avoid = {}
for (kind, name), risky in RISKY.items():
    events = [r for r in changed if (kind, name) in effects(r) or (kind == "break" and ("lost", name) in effects(r))]
    unneeded = [r for r in events if (r["edits"] & risky) - needed_edits(r)]
    avoid[f"{kind}:{name}"] = dict(events=len(events), unneeded=len(unneeded))
    print(f"| {kind.replace('new_cs', 'new error').replace('break', 'breaks')} {name} | {len(events)} | {len(unneeded)} ({len(unneeded) / len(events):.0%}) |" if events else f"| {kind} {name} | 0 | – |")
tot_e = sum(v["events"] for v in avoid.values()); tot_u = sum(v["unneeded"] for v in avoid.values())
print(f"\nOverall: {tot_u}/{tot_e} damage events ({tot_u / tot_e:.0%}) co-occurred with an unneeded risky edit — an upper bound on what an R4 'leave X alone' rule could prevent.")
unneeded_rounds = sum(1 for r in changed if (r["edits"] - needed_edits(r)) & {"edit_hotel", "edit_intercity", "edit_restaurant", "edit_attraction", "edit_structure"})
print(f"Changed rounds that touched at least one major component they did not need: {unneeded_rounds}/{len(changed)} ({unneeded_rounds / len(changed):.0%}).")

# ----------------------------------------------------------- (3) prototype risk profile
def shrunk(e, n, prior_rate, k=5):
    return (e + k * prior_rate) / (n + k)
profile = {"version": "prototype-0.1", "source_runs": ["subset_train-r0 (new loop)", "subset_train-r3 (old loop)"],
           "notes": "Train split only. Rates shrunk toward the column average with a prior worth 5 rounds."}
# fixability
fx = defaultdict(lambda: [0.0, 0.0, 0.0])
for r in pooled:
    if r["phase"] != "personal": continue
    t = [i for i in r["targets"] if i in r["fam"]]
    for i in t:
        f = SHORT[r["fam"][i]]; w = 1 / len(r["targets"])
        fx[f][0] += w
        if r["unchanged"]: fx[f][1] += w
        elif ("fix", f) in effects(r): fx[f][2] += w
glob_fix = sum(v[2] for v in fx.values()) / max(1e-9, sum(v[0] - v[1] for v in fx.values()))
glob_stuck = sum(v[1] for v in fx.values()) / sum(v[0] for v in fx.values())
profile["fixability"] = {f: dict(rounds=round(v[0], 2), p_unchanged=round(shrunk(v[1], v[0], glob_stuck), 3),
                                 p_fixed_when_changed=round(shrunk(v[2], v[0] - v[1], glob_fix), 3))
                         for f, v in fx.items()}
# commonsense repair at-risk families
cr = defaultdict(lambda: [0, 0])
for r in changed:
    if r["phase"] != "commonsense": continue
    for f in passing(r):
        cr[f][1] += 1
        cr[f][0] += int(("break", f) in effects(r) or ("lost", f) in effects(r))
g = sum(v[0] for v in cr.values()) / sum(v[1] for v in cr.values())
profile["commonsense_repair_breaks_personal"] = {f: dict(chances=n, breaks=e, p=round(shrunk(e, n, g), 3)) for f, (e, n) in cr.items()}
# edit risk (multivariable)
X = np.array([[int(e in r["edits"]) for e in EDITS] + [int(r["phase"] == "commonsense"), int(r["run"] == "R3")] for r in changed])
outcomes = {"breaks hotel": ("break", "hotel"), "breaks trip": ("break", "trip"), "breaks budget": ("break", "budget"),
            "new cs_intercity": ("new_cs", "cs_intercity"), "new cs_inner_transport": ("new_cs", "cs_inner_transport"),
            "new cs_dining": ("new_cs", "cs_dining"), "new cs_hotel": ("new_cs", "cs_hotel")}
er = {}
for name, (kind, fam) in outcomes.items():
    y = np.array([int((kind, fam) in effects(r) or (kind == "break" and ("lost", fam) in effects(r))) for r in changed])
    m = LogisticRegression(C=1.0, max_iter=2000).fit(X, y)
    er[name] = dict(base_rate=round(float(y.mean()), 3),
                    odds_ratio_by_edit={e.replace("edit_", ""): round(float(np.exp(c)), 2) for e, c in zip(EDITS, m.coef_[0][:len(EDITS)])})
profile["edit_risk"] = er
profile["fix_levers"] = levers
profile["avoidable_damage"] = avoid
json.dump(profile, open("r4_risk_profile.json", "w"), indent=2)
print("\nWrote r4_risk_profile.json:", {k: (len(v) if isinstance(v, dict) else v) for k, v in profile.items()})
