"""Shared extraction: one row per repair round with everything later analyses need."""
import glob, json, re, sys
from collections import Counter
from pathlib import Path

PROJECT = Path(r"C:/NUS WORK/Y4S1/DSA4213 NLP/ProjectCode")
sys.path.insert(0, str(PROJECT))
from chinatravel.evaluation.constraint_families import classify_constraints

SHORT = {"trip_specification": "trip", "party_resources": "party", "monetary_budget": "budget",
         "accommodation": "hotel", "dining": "dining", "attraction": "attraction",
         "transport_mode": "transport", "travel_extent": "extent", "schedule_order": "schedule"}
CS_KINDS = ["cs_inner_transport", "cs_intercity", "cs_hotel", "cs_dining", "cs_attraction", "cs_time_order", "cs_other"]


def cs_kind(message):
    m = message.lower()
    if "innercity" in m or "inner-city" in m: return "cs_inner_transport"
    if "intercity" in m: return "cs_intercity"
    if "accommodation" in m or "hotel" in m: return "cs_hotel"
    if re.search(r"restaurant|restruant|breakfast|lunch|dinner|meal", m): return "cs_dining"
    if "attraction" in m: return "cs_attraction"
    if re.search(r"last activity|chronolog|time", m): return "cs_time_order"
    return "cs_other"


EDIT_GROUPS = {"accommodation": "edit_hotel", "train": "edit_intercity", "airplane": "edit_intercity",
               "breakfast": "edit_restaurant", "lunch": "edit_restaurant", "dinner": "edit_restaurant",
               "attraction": "edit_attraction"}
EDITS = ["edit_hotel", "edit_intercity", "edit_restaurant", "edit_attraction", "edit_inner_transport",
         "edit_times", "edit_structure"]


def _identity(act):
    t = act.get("type")
    if t in ("train", "airplane"):
        return (t, act.get("TrainID") or act.get("FlightID"), act.get("start"), act.get("end"))
    return (t, act.get("position"), act.get("room_type"), act.get("rooms"))


def plan_edits(before, after):
    """Which kinds of thing changed between two raw plans."""
    edits = set()
    try:
        b_days = {d["day"]: d.get("activities") or [] for d in before}
        a_days = {d["day"]: d.get("activities") or [] for d in after}
    except Exception:
        return {"edit_structure"}
    if set(b_days) != set(a_days):
        edits.add("edit_structure")
    for day in set(b_days) | set(a_days):
        b, a = b_days.get(day, []), a_days.get(day, [])
        for group in set(EDIT_GROUPS.values()):
            bi = Counter(_identity(x) for x in b if EDIT_GROUPS.get(x.get("type")) == group)
            ai = Counter(_identity(x) for x in a if EDIT_GROUPS.get(x.get("type")) == group)
            if bi != ai:
                edits.add(group)
        if len(b) != len(a):
            edits.add("edit_structure")
        bt = [(x.get("start_time"), x.get("end_time")) for x in b]
        at = [(x.get("start_time"), x.get("end_time")) for x in a]
        if bt != at:
            edits.add("edit_times")
        btr = [json.dumps(x.get("transports"), sort_keys=True, default=str) for x in b]
        atr = [json.dumps(x.get("transports"), sort_keys=True, default=str) for x in a]
        if btr != atr:
            edits.add("edit_inner_transport")
    return edits


def load_rounds(pattern, label):
    rows, states = [], []
    for path in sorted(glob.glob(pattern)):
        result = json.load(open(path, encoding="utf-8"))
        hist = result["repair_history"]
        if len(hist) < 2:
            continue
        descriptors = hist[1]["repair_attempt"]["constraint_descriptors"]
        fam = {c["constraint_index"]: c["family"] for c in classify_constraints(descriptors)
               if c["classification_status"] == "mapped"}
        uid = result["query_uid"]
        cur_plan = result["initial_raw_plan"]
        cur_ver = hist[0]["verification"]
        states.append(dict(uid=uid, fam=fam, personal=cur_ver["personal_constraints"],
                           cs=cur_ver.get("commonsense_errors") or [], kind="initial"))
        for entry in hist[1:]:
            a = entry["repair_attempt"]
            cand_plan = entry.get("candidate_plan")
            cand_ver = entry.get("verification") or {}
            before_cs = cur_ver.get("commonsense_errors") or []
            after_cs = cand_ver.get("commonsense_errors") or []
            unchanged = json.dumps(cand_plan, sort_keys=True, default=str) == json.dumps(cur_plan, sort_keys=True, default=str)
            rows.append(dict(
                run=label, uid=uid, step=a["step"], phase=a["repair_phase"], fam=fam,
                targets=list(a["target_constraint_indices"]), accepted=a["accepted"], unchanged=unchanged,
                before=a["before_personal_constraints"], after=a["after_personal_constraints"],
                before_cs=before_cs, after_cs=after_cs,
                edits=set() if unchanged or cand_plan is None else plan_edits(cur_plan, cand_plan),
                cache_hit=(a.get("repair_metadata") or {}).get("llm_cache_hits", 0) > 0,
            ))
            states.append(dict(uid=uid, fam=fam, personal=cand_ver.get("personal_constraints") or a["after_personal_constraints"],
                               cs=after_cs, kind="candidate", unchanged=unchanged))
            if a["accepted"]:
                cur_plan, cur_ver = cand_plan, cand_ver
    return rows, states


def effects(row):
    """Events a round produced, as (kind, name) pairs."""
    out = set()
    fam = row["fam"]
    for i, (x, y) in enumerate(zip(row["before"], row["after"]), 1):
        f = SHORT.get(fam.get(i), "unmapped")
        if x is True and y is False: out.add(("break", f))
        if x is True and y is None: out.add(("lost", f))
        if x is False and y is True: out.add(("fix", f))
    new = Counter(row["after_cs"]) - Counter(row["before_cs"])
    gone = Counter(row["before_cs"]) - Counter(row["after_cs"])
    for e in new: out.add(("new_cs", cs_kind(e)))
    for e in gone: out.add(("fixed_cs", cs_kind(e)))
    return out


SP = Path(r"C:/Users/JUNHAN~1/AppData/Local/Temp/claude/c--NUS-WORK-Y4S1-DSA4213-NLP-ProjectCode/4674b5b1-d63b-4c66-8478-654a33607a71/scratchpad")
R0 = str(SP / "main_r0/experiments/subset_train-r0/queries/*/R0-*.json")
R3 = str(PROJECT / "experiments/subset_train-r3/queries/*/R3-*.json")

if __name__ == "__main__":
    for label, pattern in (("R0", R0), ("R3", R3)):
        rows, states = load_rounds(pattern, label)
        changed = [r for r in rows if not r["unchanged"]]
        ev = Counter(k for r in changed for k, _ in effects(r))
        print(label, "rounds", len(rows), "changed", len(changed), "states", len(states), "event kinds in changed rounds:", dict(ev))
        print("  edits:", Counter(e for r in changed for e in r["edits"]))
