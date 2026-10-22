
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
## Each iteration repairs ALL currently failing constraints together in one LLM
## call: every failure is shown, and the editable region is the union of the
## slots (L1) / days (L2) the failures localize to, or the whole plan (L3).
## An L3 proposal with the wrong day count or an empty day is discarded and
## the current plan is kept (recorded as a no-op attempt).
##
## R3P (``phased=True``) is a variant for comparison against plain R3. It repairs
## personal constraints only for up to 5 iterations on the same ladder (commonsense
## errors are neither shown nor opened). As soon as every personal constraint
## passes, or once those iterations are used up, the next iteration repairs the
## commonsense errors at slot scope, with every passing personal constraint listed
## as "must remain satisfied". If that breaks a personal constraint and budget is
## left, it returns to personal repair on the same ladder. Run it with
## --refine-steps 6 (5 personal + 1 commonsense), one more model call than R0/R1/R3.
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

## R3P: personal-only iterations before the commonsense iteration is forced.
DEFAULT_PERSONAL_ITERATIONS = 5

## R3P commonsense-phase header for the personal constraints that must stay
## satisfied (worded without "failed" so it is never counted as feedback).
PROTECT_HEADER = "These requirements are currently satisfied and MUST remain satisfied:"

## Trip-level anchors: never "day" slots; frozen until the whole-plan rung (L3).
ANCHOR_TYPES = {"accommodation", "airplane", "train"}

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


def _localize_message(message, plan, pos_to_slots):
    """Localize a commonsense/schema error string to slots, or 'global'."""
    slots = set()

    ## Strongest signal: the verifier often names "Day d activity a".
    day_m = _DAY_RE.search(message)
    act_m = _ACT_RE.search(message)
    if day_m:
        d = int(day_m.group(1)) - 1
        if 0 <= d < len(plan):
            if act_m:
                a = int(act_m.group(1)) - 1
                if 0 <= a < len(_activities(plan[d])):
                    slots.add((d, a))
            else:
                ## Day known but not the activity -> all of that day's activities.
                for a in range(len(_activities(plan[d]))):
                    slots.add((d, a))

    ## Also match any POI name that appears verbatim in the message (skip very
    ## short names to avoid spurious substring hits).
    for pos, pos_slots in pos_to_slots.items():
        if len(pos) > 1 and pos in message:
            slots.update(pos_slots)

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
    if "accommodation" in lowered or "room_" in lowered:
        slots.update(type_to_slots.get("accommodation", []))

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

    ``phased=True`` gives the R3P variant (see the module header): a personal-only
    phase on the ladder, then a protected slot-scope commonsense phase."""

    def __init__(self, rounds_per_rung=DEFAULT_ROUNDS_PER_RUNG, phased=False,
                 personal_iterations=DEFAULT_PERSONAL_ITERATIONS):
        self._scope_idx = 0              ## index into RUNGS (current rung)
        self._iteration = 0              ## ladder iterations taken so far
        self._rounds_per_rung = rounds_per_rung
        self._phased = phased
        self._personal_iterations = personal_iterations
        self._step = 0                   ## all repair() calls (R3P debug)
        self._strategy_name = "R3P" if phased else "R3"

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

    ## ---- R3P: which kind of failure this step repairs (None for plain R3) ----
    def _choose_phase(self, verification):
        if not self._phased:
            return None
        personal = verification.get("personal_constraints", []) or []
        if any(s is False for s in personal) and self._iteration < self._personal_iterations:
            return "personal"
        return "commonsense"

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

    ## ---- compute the editable region at the current rung ----
    def _editable_region(self, scope, plan, localized):
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

        ## Trip-level anchors stay frozen until L3.
        editable = {(d, a) for (d, a) in editable if not _is_anchor(plan, d, a)}
        return editable, global_present

    ## ---- prompt building ----
    def _editable_instruction(self, editable, plan):
        lines = []
        for (d, a) in sorted(editable):
            act = _activities(plan[d])[a]
            label = act.get("position") or act.get("type") or "activity"
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

    def _build_prompt(self, scope, problem, context, raw_plan, feedback_lines, editable):
        error_info_nl = "\n".join(feedback_lines)
        if scope == PLAN:
            backprompt = error_info_nl
        else:
            backprompt = error_info_nl + "\n\n" + self._editable_instruction(editable, raw_plan)
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
    def _merge(current, proposal, editable):
        merged = deepcopy(current)
        changed = 0
        for (d, a) in editable:
            if d >= len(proposal) or not isinstance(proposal[d], dict):
                continue  ## shape mismatch -> lock wins, keep current
            prop_acts = _activities(proposal[d])
            if a >= len(prop_acts):
                continue
            new_val = prop_acts[a]
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
        phase = self._choose_phase(verification_results)
        if phase == "commonsense":
            ## R3P commonsense step: slot scope; the personal ladder does not move.
            scope, widened, previous_idx = SLOT, False, self._scope_idx
        else:
            ## Advance the fixed widening schedule (iteration -> rung), then act.
            previous_idx = self._advance_scope()
            scope = self._scope
            widened = self._scope_idx > previous_idx

        targets = self._collect_targets(problem, verification_results, phase)
        localized = self._localize_targets(targets, raw_plan)
        editable, global_present = self._editable_region(scope, raw_plan, localized)

        total = _total_slots(raw_plan)
        scope_fraction = (len(editable) / total) if total else 0.0

        ## Feedback actually supplied to the model, measured from the lines sent
        ## rather than assumed (plain R3: all of error_info at every rung).
        feedback_lines, protected = self._feedback_lines(
            problem, verification_results, phase
        )

        query_message = self._build_prompt(
            scope, problem, context, raw_plan, feedback_lines, editable
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
            merged, changed = self._merge(raw_plan, proposal, editable)

        per_target_edits = self._per_target_edits(
            targets, localized, editable, raw_plan, merged, raw_plan
        )

        ## Canonical intent (promoted onto the RepairAttemptRecord by the loop).
        ## target_constraint_indices are all current False personal constraints
        ## (never unknown None) as original 1-based hard_logic_py indices - R3
        ## repairs them together; an R3P commonsense step targets none. Scope is
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
            "iteration": self._iteration,
            "prompt": query_message,
            "raw_response": raw_response,
            "llm_inference_time": inference_time,
        }
        if self._phased:
            metadata["protected_constraint_indices"] = protected
            metadata["repair_phase"] = phase
            metadata["personal_iteration"] = self._iteration
            metadata["r3p_call"] = self._step   ## "step" is a reserved record field
        if widened:
            metadata["escalation_reason"] = (
                f"scheduled_widen_{RUNGS[previous_idx]}_to_{scope}_"
                f"at_iteration_{self._iteration}"
            )

        return RepairResult(repaired_plan=merged, metadata=metadata)
