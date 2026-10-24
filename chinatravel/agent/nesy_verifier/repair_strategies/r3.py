
## R3: Scheduled-scope repair.
##
## R3 is "R1 that gradually relaxes into R0": it always edits the current accepted
## itinerary, but starts with the least freedom (only the slots tied to failing
## constraints, exactly like R1) and widens on a fixed iteration schedule -
## slot -> day -> whole plan. By default it spends 2 repair iterations at each rung
## before climbing: iterations 1-2 edit slots (L1), iterations 3-4 edit whole days
## (L2), and from iteration 5 onwards the whole plan (L3). At its tightest rung it
## is R1; at its widest it is R0.
##
## The shared repair loop decides each iteration's phase (context["repair_phase"]):
## up to 5 "personal" iterations, then one "commonsense" iteration, the same 5+1
## schedule for every registered strategy. Every iteration, whatever its phase,
## advances the ladder, so the rung always follows the loop's step number
## (steps 1-2 slot, 3-4 day, 5-6 plan). A personal iteration shows only the
## personal failures; the commonsense iteration shows only the commonsense errors
## at the current rung and lists every passing personal constraint as "must
## remain satisfied". Direct calls without a phase show all failures. The
## editable region is the union of the
## slots (L1) / days (L2) the failures localize to, or the whole plan (L3).
## An L3 proposal with the wrong day count or an empty day is discarded and
## the current plan is kept (recorded as a no-op attempt).
##
## Bookings (the hotel, and the outbound / return train or flight) are frozen
## below the plan rung, with one exception, the "booking unlock": a failure that
## is about a booking opens that booking at any rung.
##
## Personal constraints come first - a failing personal constraint must be
## fixable from step 1, so it opens the bookings it is about:
##   - hotel / room constraints (accommodation_type, room_type, room_count ...)
##     open the hotel;
##   - intercity constraints (intercity_transport_type, activity_type in
##     ['train', 'airplane'], tickets on them) open the outbound and return
##     train or flight;
##   - a constraint quoting a booking's name opens that booking;
##   - inner-city leg constraints (innercity_transport_type, metro_tickets,
##     taxi_cars ...) open every activity's leg, including the leg fields of the
##     hotel (see "legs" below);
##   - a budget constraint (activity_cost ...) that cannot be pinned to slots
##     opens the bookings among the 3 most expensive activities, since a trip
##     over budget because of its flights or hotel can only be fixed there.
##
## Commonsense errors open the booking they point at:
##   - An accommodation error ("Incorrect cost information of accommodation",
##     "accommodation activity, X in day 2, ...") opens the hotel - only on the
##     named day if the message names one, every hotel slot otherwise.
##   - An intercity error ("... intercity transport from origin to destination
##     G79 ...", "(Go)" / "(Back)") opens the outbound or return train/flight.
##   - An inner-city transport error whose leg ends at the hotel ("from Zoo to
##     Atour Hotel") opens only that hotel activity's leg fields (transports,
##     start_time, end_time); the booking itself (hotel, room, price, cost)
##     stays as it is.
## Why: without it, none of these failures could be fixed before step 5 - e.g.
## a 3-person trip whose flights and hotel alone exceed the budget wasted steps
## 1-4. For commonsense errors it matters most when personal constraints
## already pass and the only (commonsense) step runs at step 1, at slot scope;
## it also stops an unlocated accommodation error from becoming "global", which
## opened many unrelated activities but never the hotel. Opened bookings are
## listed in the prompt and logged as "unlocked_bookings" in the repair metadata.
##
## This file implements the repair behaviour and emits the standardized repair
## output contract (see chinatravel/evaluation/REPAIR_ATTEMPTS.md): canonical intent
## keys (target_constraint_indices, editable_scope, scope_level, escalation_reason,
## target_provenance, feedback_personal_constraint_indices,
## feedback_commonsense_failure_count) plus per-step debug components. What the
## repair broke (newly_violated) is measured by the shared loop after verifying
## the candidate, on the same RepairAttemptRecord; this strategy never computes
## outcomes, repair timing or token usage. It does NOT build the interdependency
## matrix - that is a separate downstream task.

import json
import re
import time
from collections import Counter
from copy import deepcopy

from chinatravel.json_utils import repair_json
from chinatravel.evaluation.repair_attempt import failed_constraint_indices
from chinatravel.agent.nesy_verifier.prompts.llm_modulo import BACK_PROMPT
from chinatravel.agent.nesy_verifier.repair_strategies.base import (
    BaseRepairStrategy,
    RepairResult,
)


## The freedom ladder (ratchet - it only ever widens).
SLOT, DAY, PLAN = "slot", "day", "plan"
RUNGS = [SLOT, DAY, PLAN]

## Canonical 1-based scope level per rung (contract: 1=slot, 2=day, 3=plan).
SCOPE_LEVEL = {SLOT: 1, DAY: 2, PLAN: 3}

## Fixed widening schedule: how many repair iterations to spend at each rung
## before climbing to the next. The widest rung is kept for all later iterations.
## With the default (2): iters 1-2 -> slot, iters 3-4 -> day, iters 5+ -> plan.
DEFAULT_ROUNDS_PER_RUNG = 2

## Commonsense-phase header for the personal constraints that must stay
## satisfied (worded without "failed" so it is never counted as feedback).
PROTECT_HEADER = "These requirements are currently satisfied and MUST remain satisfied:"

## Trip-level anchors (bookings): never "day" slots; frozen until the whole-plan
## rung (L3) unless a commonsense error unlocks them (see the module header).
ANCHOR_TYPES = {"accommodation", "airplane", "train"}
INTERCITY_TYPES = {"airplane", "train"}

## Booking unlock levels: "all" lets the whole booking activity change; "legs"
## lets only LEG_FIELDS change (the inner-city trip into it and its times).
UNLOCK_ALL, UNLOCK_LEGS = "all", "legs"
LEG_FIELDS = ("transports", "start_time", "end_time")

## Meal activities are the restaurant slots in the itinerary.
MEAL_TYPES = {"breakfast", "lunch", "dinner"}

## How many highest-cost activities to offer a global constraint (e.g. budget) at L1.
GLOBAL_HEURISTIC_K = 3


## -------- small plan helpers --------

def _activities(day):
    acts = day.get("activities") if isinstance(day, dict) else None
    return acts if isinstance(acts, list) else []


def _total_slots(plan):
    return sum(len(_activities(day)) for day in plan)


def _act_type(plan, d, a):
    return _activities(plan[d])[a].get("type")


def _is_anchor(plan, d, a):
    return _act_type(plan, d, a) in ANCHOR_TYPES


def _index_plan(plan):
    """Build lookup tables for localization: position -> slots, type -> slots."""
    pos_to_slots = {}
    type_to_slots = {}
    for d, day in enumerate(plan):
        for a, act in enumerate(_activities(day)):
            if not isinstance(act, dict):
                continue
            pos = act.get("position")
            if isinstance(pos, str) and pos:
                pos_to_slots.setdefault(pos, []).append((d, a))
            t = act.get("type")
            if t is not None:
                type_to_slots.setdefault(t, []).append((d, a))
    return pos_to_slots, type_to_slots


def _global_heuristic_slots(plan, k=GLOBAL_HEURISTIC_K):
    """A fallback slot set for an unlocalizable (global) constraint such as budget:
    the k highest-cost non-anchor activities."""
    scored = []
    for d, day in enumerate(plan):
        for a, act in enumerate(_activities(day)):
            if _is_anchor(plan, d, a):
                continue
            cost = act.get("cost", 0) if isinstance(act, dict) else 0
            try:
                cost = float(cost)
            except (TypeError, ValueError):
                cost = 0.0
            scored.append((cost, d, a))
    scored.sort(reverse=True)
    return {(d, a) for _, d, a in scored[:k]}


def _structure_problem(current, proposal):
    """Why a whole-plan proposal is unusable, or None if it is structurally sound:
    it must keep the current day count and give every day a non-empty
    activities list of dicts."""
    if len(proposal) != len(current):
        return "day_count_mismatch"
    for day in proposal:
        acts = day.get("activities") if isinstance(day, dict) else None
        if not isinstance(acts, list) or not acts or not all(isinstance(a, dict) for a in acts):
            return "missing_activities"
    return None


## -------- localization: failing constraint -> slot set (or "global") --------

_DAY_RE = re.compile(r"day\s+(\d+)", re.IGNORECASE)
_ACT_RE = re.compile(r"activit(?:y|ies)\s+(\d+)", re.IGNORECASE)
_QUOTED_RE = re.compile(r"'([^']+)'|\"([^\"]+)\"")

## Personal-failure feedback line written by shared_verifier.verify_plan.
_PERSONAL_FEEDBACK_RE = re.compile(r"^Personal constraint (\d+) failed")


def _is_personal_feedback(line):
    return isinstance(line, str) and _PERSONAL_FEEDBACK_RE.match(line) is not None


def _feedback_personal_indices(feedback_lines):
    """1-based personal constraint indices actually named in the feedback lines."""
    indices = set()
    for line in feedback_lines:
        m = _PERSONAL_FEEDBACK_RE.match(line) if isinstance(line, str) else None
        if m:
            indices.add(int(m.group(1)))
    return sorted(indices)


def _feedback_commonsense_count(commonsense_errors, feedback_lines):
    """Commonsense failure messages supplied in the feedback (duplicates kept),
    counted the same way as R0; None when commonsense errors are unavailable."""
    if not isinstance(commonsense_errors, list):
        return None
    return sum((Counter(commonsense_errors) & Counter(feedback_lines)).values())


def _booking_slots(message, plan):
    """Booking slots a commonsense error is about, found from its wording rather
    than a place name (booking unlock, see the module header):
      - accommodation errors -> every hotel slot (the caller narrows this to the
        named day, if any);
      - intercity errors -> the outbound train/flight (first activity of day 1)
        for "origin to destination" / "(Go)", the return one (last activity of
        the last day) for "destination to origin" / "(Back)".
    Covers the wording of both verifiers (verifier/commonsense_constraint_nl.py
    and symbol_verification/commonsense_constraint.py)."""
    lowered = message.lower()
    slots = set()
    if "intercity" in lowered:
        slots |= _intercity_slots(
            plan,
            go=any(k in lowered for k in ("origin to destination", "origin -> destination", "(go)")),
            back=any(k in lowered for k in ("destination to origin", "destination -> origin", "(back)")))
    if "accommodation" in lowered or "price * rooms" in lowered:
        slots |= _hotel_slots(plan)
    return slots


def _hotel_slots(plan):
    return {(d, a) for d, day in enumerate(plan) for a, act in enumerate(_activities(day))
            if isinstance(act, dict) and act.get("type") == "accommodation"}


def _intercity_slots(plan, go=True, back=True):
    """The outbound (first activity of day 1) and/or return (last activity of the
    last day) train/flight booking slots."""
    slots = set()
    if go and plan and _activities(plan[0]) and _act_type(plan, 0, 0) in INTERCITY_TYPES:
        slots.add((0, 0))
    if back and plan and _activities(plan[-1]):
        d, a = len(plan) - 1, len(_activities(plan[-1])) - 1
        if _act_type(plan, d, a) in INTERCITY_TYPES:
            slots.add((d, a))
    return slots


def _leg_slots(plan):
    """Activities that carry an inner-city leg (the trip into them)."""
    return {(d, a) for d, day in enumerate(plan) for a, act in enumerate(_activities(day))
            if isinstance(act, dict) and act.get("transports")}


## Personal-constraint (hard_logic_py) vocabulary used to find the bookings a
## constraint is about. Function names are the fixed ChinaTravel DSL names.
## Money: a budget-type constraint (usually the whole trip's cost).
_COST_FUNCS = ("activity_cost", "activity_price",
               "innercity_transport_cost", "innercity_transport_price")
## The outbound / return train or flight.
_INTERCITY_KEYS = ("intercity_transport_type", "'train'", "'airplane'", '"train"', '"airplane"')
## Inner-city legs (mode, timing, distance, tickets, taxis).
_LEG_KEYS = ("innercity_transport_type", "innercity_transport_time",
             "innercity_transport_distance", "innercity_transport_start_time",
             "innercity_transport_end_time", "metro_tickets", "taxi_cars")
## The hotel.
_HOTEL_KEYS = ("accommodation", "room_")


def _is_cost_dsl(dsl):
    return any(f in dsl for f in _COST_FUNCS)


def _personal_booking_slots(dsl, plan):
    """Booking slots a personal constraint is about (booking unlock, see the
    module header): the hotel for hotel / room constraints, the outbound and
    return train or flight for intercity-mode or intercity-ticket constraints,
    and any booking whose name is quoted in the constraint."""
    lowered = dsl.lower()
    slots = set()
    if any(k in lowered for k in _HOTEL_KEYS):
        slots |= _hotel_slots(plan)
    if any(k in lowered for k in _INTERCITY_KEYS):
        slots |= _intercity_slots(plan)
    quoted = {q1 or q2 for q1, q2 in _QUOTED_RE.findall(dsl)}
    for d, day in enumerate(plan):
        for a, act in enumerate(_activities(day)):
            if _is_anchor(plan, d, a) and act.get("position") in quoted:
                slots.add((d, a))
    return slots


def _costliest_bookings(plan, k=GLOBAL_HEURISTIC_K):
    """Bookings among the k most expensive activities of the whole plan (bookings
    included). A budget constraint that is over the limit because of the flights
    or the hotel can only be fixed by changing them."""
    scored = []
    for d, day in enumerate(plan):
        for a, act in enumerate(_activities(day)):
            try:
                cost = float(act.get("cost", 0) if isinstance(act, dict) else 0)
            except (TypeError, ValueError):
                cost = 0.0
            scored.append((cost, d, a))
    scored.sort(reverse=True)
    return {(d, a) for _, d, a in scored[:k] if _is_anchor(plan, d, a)}


def _localize_message(message, plan, pos_to_slots):
    """Localize a commonsense/schema error string to slots, or 'global'.

    POI names that appear verbatim in the message are the main handle (very
    short names are skipped to avoid spurious substring hits), plus any booking
    the message is about (``_booking_slots``). When the message names a day
    ("in day 3"), only matches on that day count, plus the exact activity if one
    is named; the whole day is opened only when nothing on it matched and no
    activity is named. Booking slots are returned like any other slot; whether
    they are actually editable is decided in ``_editable_region``."""
    named = set(_booking_slots(message, plan))
    for pos, pos_slots in pos_to_slots.items():
        if len(pos) > 1 and pos in message:
            named.update(pos_slots)

    day_m = _DAY_RE.search(message)
    if not day_m:
        return named if named else "global"

    d = int(day_m.group(1)) - 1
    if not 0 <= d < len(plan):
        return named if named else "global"

    slots = {(nd, na) for (nd, na) in named if nd == d}
    act_m = _ACT_RE.search(message)
    if act_m:
        a = int(act_m.group(1)) - 1
        if 0 <= a < len(_activities(plan[d])):
            slots.add((d, a))
    elif not slots:
        ## Day known, but neither the activity nor a POI on it -> the whole day.
        slots = {(d, a) for a in range(len(_activities(plan[d])))}
    return slots if slots else "global"


def _localize_personal(dsl, plan, pos_to_slots, type_to_slots):
    """Localize a personal (hard_logic_py) constraint to slots, or 'global'."""
    slots = set()

    ## 1) Quoted POI names present in the plan are the cleanest handle.
    for q1, q2 in _QUOTED_RE.findall(dsl):
        name = q1 or q2
        if name in pos_to_slots:
            slots.update(pos_to_slots[name])
    if slots:
        return slots

    ## 2) Fall back to constraint "kind" keywords -> activities of that type.
    lowered = dsl.lower()
    if "restaurant" in lowered or any(m in lowered for m in MEAL_TYPES):
        for m in MEAL_TYPES:
            slots.update(type_to_slots.get(m, []))
    if "attraction" in lowered:
        slots.update(type_to_slots.get("attraction", []))
    if any(k in lowered for k in _HOTEL_KEYS):
        slots.update(type_to_slots.get("accommodation", []))
    ## Intercity mode / tickets -> the outbound and return train or flight.
    if any(k in lowered for k in _INTERCITY_KEYS):
        slots |= _intercity_slots(plan)
    ## Inner-city leg rules (mode, tickets, taxis...) -> every activity with a leg.
    ## Skipped for money constraints: a budget sums the legs' cost but is about
    ## the whole trip, so it stays "global".
    if not _is_cost_dsl(lowered) and any(k in lowered for k in _LEG_KEYS):
        slots |= _leg_slots(plan)

    ## 3) Nothing localizable (budget / day_count / people_count ...) -> global.
    return slots if slots else "global"


## -------- R3 strategy --------

class R3AdaptiveScopeRepair(BaseRepairStrategy):
    """Scheduled-scope repair. A fresh instance is created per query (per prompt),
    so its ladder state resets automatically between prompts.

    Rung-widening follows a fixed iteration schedule computed inside ``repair()``
    (``rounds_per_rung`` iterations per rung, the widest rung kept thereafter), so
    ``accept()`` stays the default (always accept). This keeps R3 distinct from R2
    (whose job is rollback).

    The repair phase comes from the shared loop (see the module header). Every
    ``repair()`` call advances the ladder, commonsense calls included; the loop
    calls ``repair()`` once per step, so the iteration count equals the step."""

    def __init__(self, rounds_per_rung=DEFAULT_ROUNDS_PER_RUNG):
        self._scope_idx = 0              ## index into RUNGS (current rung)
        self._iteration = 0              ## ladder iterations taken so far
        self._rounds_per_rung = rounds_per_rung
        self._step = 0                   ## all repair() calls, both phases (debug)
        self._strategy_name = "R3"

    @property
    def _scope(self):
        return RUNGS[self._scope_idx]

    ## ---- the fixed widening schedule (ratchet) ----
    def _advance_scope(self):
        """Advance the schedule by one repair iteration and set the current rung.
        The first ``rounds_per_rung`` iterations use rung 0 (slot), the next
        ``rounds_per_rung`` use rung 1 (day), and every iteration thereafter uses
        the widest rung (plan). Returns the previous rung index so the caller can
        report an escalation reason when the rung climbs."""
        previous_idx = self._scope_idx
        self._iteration += 1
        self._scope_idx = min(
            (self._iteration - 1) // self._rounds_per_rung, len(RUNGS) - 1
        )
        return previous_idx

    ## ---- feedback lines sent to the model, and the personal ones protected ----
    def _feedback_lines(self, problem, verification, phase):
        lines = list(verification.get("error_info", []) or [])
        if phase is None:
            return lines, []
        if phase == "personal":
            return [l for l in lines if _is_personal_feedback(l)], []
        lines = [l for l in lines if not _is_personal_feedback(l)]
        hard_logic = problem.get("hard_logic_py", []) or []
        personal = verification.get("personal_constraints", []) or []
        protected = [i for i, s in enumerate(personal, 1) if s is True]
        if protected:
            lines += ["", PROTECT_HEADER] + [
                f"  - Personal constraint {i} (satisfied): "
                f"{hard_logic[i - 1] if i - 1 < len(hard_logic) else ''}"
                for i in protected
            ]
        return lines, protected

    ## ---- collect the failing constraints this step aims at (raw identities) ----
    def _collect_targets(self, problem, verification, phase=None):
        targets = []
        personal = verification.get("personal_constraints", []) or []
        hard_logic = problem.get("hard_logic_py", []) or []
        for i, status in enumerate(personal):
            if status is False and phase != "commonsense":
                dsl = hard_logic[i] if i < len(hard_logic) else ""
                ## 1-based, matching target_constraint_indices.
                targets.append(
                    {"kind": "personal", "ref": f"personal:{i + 1}",
                     "constraint_index": i + 1, "dsl": dsl}
                )
        if phase == "personal":
            return targets
        for k, msg in enumerate(verification.get("commonsense_errors", []) or [], 1):
            targets.append(
                {"kind": "commonsense", "ref": f"commonsense:{k}", "message": msg}
            )
        for k, msg in enumerate(verification.get("schema_errors", []) or [], 1):
            targets.append({"kind": "schema", "ref": f"schema:{k}", "message": msg})
        return targets

    ## ---- map each target to a slot set (or "global") ----
    def _localize_targets(self, targets, plan):
        pos_to_slots, type_to_slots = _index_plan(plan)
        localized = []
        for t in targets:
            if t["kind"] == "personal":
                loc = _localize_personal(t.get("dsl", ""), plan, pos_to_slots, type_to_slots)
            else:
                loc = _localize_message(t.get("message", ""), plan, pos_to_slots)
            localized.append(loc)
        return localized

    ## ---- booking unlock: which frozen bookings a message opens, and how far ----
    @staticmethod
    def _booking_unlocks(targets, localized, plan):
        """{(day, activity): UNLOCK_ALL | UNLOCK_LEGS} for the bookings the
        current failures are about.

        Personal constraints (the priority):
          - a hotel / room, intercity mode or ticket constraint, or one quoting a
            booking's name, opens those bookings fully (``_personal_booking_slots``);
          - an inner-city leg constraint (mode, tickets, taxis) opens the hotel's
            leg fields;
          - a budget constraint that cannot be localized ("global") opens the
            bookings among the most expensive activities (``_costliest_bookings``).
        Commonsense / schema messages:
          - a booking the message is about (``_booking_slots``: accommodation /
            intercity errors) opens fully;
          - a booking only named as a place (e.g. the hotel at the end of an
            inner-city leg) opens just its LEG_FIELDS;
          - a booking in the localized set only because the whole named day was
            opened (no name matched on that day) stays frozen."""
        unlocked = {}
        for target, loc in zip(targets, localized):
            if target["kind"] == "personal":
                dsl = target.get("dsl", "") or ""
                if loc == "global":
                    if _is_cost_dsl(dsl):
                        for slot in _costliest_bookings(plan):
                            unlocked[slot] = UNLOCK_ALL
                    continue
                about = _personal_booking_slots(dsl, plan)
                for (d, a) in loc:
                    if not _is_anchor(plan, d, a):
                        continue
                    if (d, a) in about:
                        unlocked[(d, a)] = UNLOCK_ALL
                    else:
                        unlocked.setdefault((d, a), UNLOCK_LEGS)
                continue
            if loc == "global":
                continue
            message = target.get("message", "")
            about = _booking_slots(message, plan)
            for (d, a) in loc:
                if not _is_anchor(plan, d, a):
                    continue
                position = _activities(plan[d])[a].get("position")
                if (d, a) in about:
                    unlocked[(d, a)] = UNLOCK_ALL
                elif isinstance(position, str) and len(position) > 1 and position in message:
                    unlocked.setdefault((d, a), UNLOCK_LEGS)
        return unlocked

    ## ---- compute the editable region at the current rung ----
    def _editable_region(self, scope, plan, localized, unlocked=None):
        global_present = any(loc == "global" for loc in localized)
        base = set()
        for loc in localized:
            if loc != "global":
                base |= loc

        if scope == PLAN:
            ## Everything, anchors included.
            return (
                {
                    (d, a)
                    for d in range(len(plan))
                    for a in range(len(_activities(plan[d])))
                },
                global_present,
            )

        if scope == SLOT:
            editable = set(base)
            if global_present:
                editable |= _global_heuristic_slots(plan)
        else:  ## DAY
            days = {d for (d, _a) in base}
            if global_present:
                days = set(range(len(plan)))
            editable = {
                (d, a)
                for d in days
                for a in range(len(_activities(plan[d])))
            }

        ## Trip-level anchors stay frozen until L3, except bookings a commonsense
        ## error unlocked (booking unlock; see _booking_unlocks).
        editable = {(d, a) for (d, a) in editable if not _is_anchor(plan, d, a)}
        editable |= set(unlocked or ())
        return editable, global_present

    ## ---- prompt building ----
    def _editable_instruction(self, editable, plan, leg_only=frozenset()):
        lines = []
        for (d, a) in sorted(editable):
            act = _activities(plan[d])[a]
            label = act.get("position") or act.get("type") or "activity"
            if (d, a) in leg_only:
                ## Booking unlock (legs): the booking itself must not change.
                label += (" (only its transports, start_time and end_time; "
                          "keep the booking itself unchanged)")
            lines.append(f"  - Day {d + 1} activity {a + 1}: {label}")
        listing = "\n".join(lines) if lines else "  (none)"
        return (
            "IMPORTANT - LIMITED EDIT SCOPE:\n"
            "You may ONLY modify these activities:\n"
            f"{listing}\n"
            "Copy every other activity EXACTLY as given in the plan above, "
            "with identical fields and order. Do not add, remove or reorder any "
            "other activity."
        )

    def _build_prompt(self, scope, problem, context, raw_plan, feedback_lines, editable,
                      leg_only=frozenset()):
        error_info_nl = "\n".join(feedback_lines)
        if scope == PLAN:
            backprompt = error_info_nl
        else:
            backprompt = error_info_nl + "\n\n" + self._editable_instruction(
                editable, raw_plan, leg_only)
        return BACK_PROMPT.format(
            go_train_info=context["go_train_info"],
            go_flight_info=context["go_flight_info"],
            back_train_info=context["back_train_info"],
            back_flight_info=context["back_flight_info"],
            attraction_info=context["attraction_info"],
            restaurant_info=context["restaurant_info"],
            accommodation_info=context["accommodation_info"],
            innercity_transport_info=context["innercity_transport_info"],
            query=problem["nature_language"],
            plan=json.dumps(raw_plan, ensure_ascii=False),
            backprompt=backprompt,
        )

    ## ---- parse the LLM proposal (mirrors R0's formatting contract) ----
    @staticmethod
    def _parse_response(response):
        primed = """[{"day": 1,""" + response
        try:
            parsed = json.loads(repair_json(primed))
            if isinstance(parsed, list):
                return parsed, primed
        except Exception:
            pass
        return None, primed

    ## ---- merge: keep frozen slots verbatim, take only editable slots ----
    @staticmethod
    def _merge(current, proposal, editable, leg_only=frozenset()):
        """``leg_only`` slots (booking unlock "legs") take only LEG_FIELDS from
        the proposal; the rest of that booking is kept from the current plan."""
        merged = deepcopy(current)
        changed = 0
        for (d, a) in editable:
            if d >= len(proposal) or not isinstance(proposal[d], dict):
                continue  ## shape mismatch -> lock wins, keep current
            prop_acts = _activities(proposal[d])
            if a >= len(prop_acts):
                continue
            new_val = prop_acts[a]
            if (d, a) in leg_only:
                if not isinstance(new_val, dict):
                    continue
                new_val = {**merged[d]["activities"][a],
                           **{f: new_val[f] for f in LEG_FIELDS if f in new_val}}
            if merged[d]["activities"][a] != new_val:
                merged[d]["activities"][a] = deepcopy(new_val)
                changed += 1
        return merged, changed

    @staticmethod
    def _count_changed_all(current, proposal):
        changed = 0
        for d, day in enumerate(current):
            cur_acts = _activities(day)
            prop_acts = (
                _activities(proposal[d])
                if d < len(proposal) and isinstance(proposal[d], dict)
                else []
            )
            for a, act in enumerate(cur_acts):
                if a >= len(prop_acts) or act != prop_acts[a]:
                    changed += 1
        return changed

    ## ---- per-target edits (new slot values), for later replay attribution ----
    @staticmethod
    def _per_target_edits(targets, localized, editable, current, merged, plan):
        result = {}
        for t, loc in zip(targets, localized):
            slots = loc if loc != "global" else _global_heuristic_slots(plan)
            edits = []
            for (d, a) in slots:
                if (d, a) not in editable:
                    continue
                if d >= len(merged) or a >= len(_activities(merged[d])):
                    continue
                if current[d]["activities"][a] != merged[d]["activities"][a]:
                    edits.append(
                        {
                            "day": d,
                            "activity_index": a,
                            "new_value": merged[d]["activities"][a],
                        }
                    )
            result[t["ref"]] = edits
        return result

    @staticmethod
    def _slot_descriptors(editable, plan):
        out = []
        for (d, a) in sorted(editable):
            act = _activities(plan[d])[a]
            out.append(
                {
                    "day": d,
                    "activity_index": a,
                    "type": act.get("type"),
                    "position": act.get("position"),
                }
            )
        return out

    ## ---- the strategy entry point ----
    def repair(self, problem, raw_plan, verification_results, context, llm):
        self._step += 1
        ## None only for direct calls outside the shared loop (all failures shown).
        phase = context.get("repair_phase")
        if phase not in (None, "personal", "commonsense"):
            raise ValueError("Unknown shared repair_phase")
        ## Advance the fixed widening schedule (iteration -> rung) in both phases:
        ## the commonsense step uses the same rung a personal step would get.
        previous_idx = self._advance_scope()
        scope = self._scope
        widened = self._scope_idx > previous_idx

        # Scheduled commonsense repairs have a strict objective. Preserve full
        # verification for logging; historical direct calls keep schema targeting.
        objective_verification = verification_results
        if context.get("repair_phase") == "commonsense":
            objective_verification = {
                **verification_results,
                "schema_errors": [],
                "error_info": list(verification_results.get("commonsense_errors") or []),
            }
        targets = self._collect_targets(problem, objective_verification, phase)
        localized = self._localize_targets(targets, raw_plan)
        ## Booking unlock: below the plan rung, bookings that a commonsense error
        ## points at become editable (fully, or only their legs).
        unlocked = {} if scope == PLAN else self._booking_unlocks(targets, localized, raw_plan)
        leg_only = frozenset(s for s, level in unlocked.items() if level == UNLOCK_LEGS)
        editable, global_present = self._editable_region(scope, raw_plan, localized, unlocked)

        total = _total_slots(raw_plan)
        scope_fraction = (len(editable) / total) if total else 0.0

        ## Feedback actually supplied to the model, measured from the lines sent
        ## rather than assumed (plain R3: all of error_info at every rung).
        feedback_lines, protected = self._feedback_lines(
            problem, objective_verification, phase
        )

        if context.get("repair_phase") == "personal":
            hard_logic = problem.get("hard_logic_py", [])
            feedback_lines.extend(
                f"Personal constraint {i} is UNKNOWN; make it evaluable: {hard_logic[i - 1]}"
                for i, state in enumerate(verification_results.get("personal_constraints", []), 1)
                if state is None and i <= len(hard_logic)
            )

        query_message = self._build_prompt(
            scope, problem, context, raw_plan, feedback_lines, editable, leg_only
        )

        start_time = time.time()
        response = llm([{"role": "user", "content": query_message}], one_line=False)
        inference_time = time.time() - start_time

        proposal, raw_response = self._parse_response(response)

        structure_problem = None
        if proposal is None:
            ## Parse failure -> no-op repair: the current plan is proposed unchanged
            ## (the fixed schedule still advances on the next iteration).
            merged, changed = deepcopy(raw_plan), 0
        elif scope == PLAN:
            structure_problem = _structure_problem(raw_plan, proposal)
            if structure_problem is None:
                merged, changed = proposal, self._count_changed_all(raw_plan, proposal)
            else:
                ## Unusable proposal (e.g. a truncated reply repaired into a
                ## shorter plan) -> keep the current plan (no-op attempt).
                merged, changed = deepcopy(raw_plan), 0
        else:
            merged, changed = self._merge(raw_plan, proposal, editable, leg_only)

        per_target_edits = self._per_target_edits(
            targets, localized, editable, raw_plan, merged, raw_plan
        )

        ## Canonical intent (promoted onto the RepairAttemptRecord by the loop).
        ## target_constraint_indices are all current False personal constraints
        ## (never unknown None) as original 1-based hard_logic_py indices - R3
        ## repairs them together; a commonsense step targets none. Scope is
        ## reported as both the string rung (editable_scope) and the agreeing
        ## 1-based level (scope_level).
        metadata = {
            "strategy": self._strategy_name,
            "target_constraint_indices": [] if phase == "commonsense" else failed_constraint_indices(
                verification_results.get("personal_constraints", []) or []
            ),
            "editable_scope": scope,
            "scope_level": SCOPE_LEVEL[scope],
            "target_provenance": "r3_adaptive_scope",
            "feedback_personal_constraint_indices": _feedback_personal_indices(
                feedback_lines
            ),
            "feedback_commonsense_failure_count": _feedback_commonsense_count(
                verification_results.get("commonsense_errors"), feedback_lines
            ),
            ## Debug / audit components (kept in repair_metadata; non-canonical).
            "parse_failed": proposal is None,
            "proposal_rejected_reason": structure_problem,
            "scope_fraction": round(scope_fraction, 4),
            "changed_slots": changed,
            "editable_slots": self._slot_descriptors(editable, raw_plan),
            "targeted_constraints": targets,
            "per_target_edits": per_target_edits,
            "global_targets": global_present,
            ## Bookings opened below the plan rung by the booking unlock.
            "unlocked_bookings": [
                {"day": d, "activity_index": a, "type": _act_type(raw_plan, d, a),
                 "position": _activities(raw_plan[d])[a].get("position"),
                 "fields": level}
                for (d, a), level in sorted(unlocked.items())
            ],
            "iteration": self._iteration,
            "prompt": query_message,
            "raw_response": raw_response,
            "llm_inference_time": inference_time,
        }
        if phase is not None:
            metadata["protected_constraint_indices"] = protected
            metadata["repair_phase"] = phase
            metadata["target_commonsense_errors"] = (
                list(objective_verification.get("commonsense_errors") or [])
                if phase == "commonsense" else []
            )
            metadata["repair_call"] = self._step   ## "step" is a reserved record field
        if widened:
            metadata["escalation_reason"] = (
                f"scheduled_widen_{RUNGS[previous_idx]}_to_{scope}_"
                f"at_iteration_{self._iteration}"
            )

        return RepairResult(repaired_plan=merged, metadata=metadata)
