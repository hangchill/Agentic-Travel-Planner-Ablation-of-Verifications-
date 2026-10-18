"""Pure personal-constraint repair metrics; no verifier, database, or LLM calls."""

from statistics import mean

from chinatravel.evaluation.repair_attempt import RepairAttemptRecord, coerce_repair_attempt


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _all_pass(states):
    return all(value is True for value in states) if states else None


def _complete_sum(values):
    return sum(values) if all(value is not None for value in values) else None


def _defined_mean(values):
    known = [value for value in values if value is not None]
    return mean(known) if known else None


def compute_attempt_metrics(record: RepairAttemptRecord | dict) -> dict:
    """Return one flat metric row for a validated record or serialized record.

    Candidate metrics include rejected proposals. Accepted metrics compare the
    prior accepted state to the candidate only on acceptance, otherwise itself.
    Unknown states never count as passes, failures, fixes, or regressions.
    """
    record = coerce_repair_attempt(record)
    before = record.before_personal_constraints
    after = record.after_personal_constraints
    failed = sum(value is False for value in before)
    passed = sum(value is True for value in before)
    fixed, regressed = len(record.fixed), len(record.newly_violated)
    eligible_targets = [index - 1 for index in record.target_constraint_indices
                        if before[index - 1] is False]
    targeted_fixed = sum(after[index] is True for index in eligible_targets)
    accepted_fixed = fixed if record.accepted else 0
    accepted_regressed = regressed if record.accepted else 0
    return {
        "query_uid": record.query_uid,
        "repair_strategy": record.repair_strategy,
        "step": record.step,
        "failed_before_count": failed,
        "passed_before_count": passed,
        "fixed_count": fixed,
        "newly_violated_count": regressed,
        "repair_success_rate": _ratio(fixed, failed),
        "targeted_repair_success_rate": _ratio(targeted_fixed, len(eligible_targets)),
        "targeted_fixed_count": targeted_fixed,
        "targeted_failed_before_count": len(eligible_targets),
        "new_violation_rate": _ratio(regressed, passed),
        "net_repair_gain": fixed - regressed,
        "candidate_all_personal_constraints_pass": _all_pass(after),
        "accepted_fixed_count": accepted_fixed,
        "accepted_newly_violated_count": accepted_regressed,
        "accepted_net_repair_gain": accepted_fixed - accepted_regressed,
        "accepted_repair_success_rate": _ratio(accepted_fixed, failed),
        "accepted_new_violation_rate": _ratio(accepted_regressed, passed),
        "input_tokens_delta": record.input_tokens_delta,
        "output_tokens_delta": record.output_tokens_delta,
        "total_tokens_delta": (record.total_tokens_delta if record.total_tokens_delta is not None else
                               _complete_sum([record.input_tokens_delta, record.output_tokens_delta])),
        "repair_time_seconds": record.repair_time_seconds,
        "verification_time_seconds": record.verification_time_seconds,
        "attempt_time_seconds": record.attempt_time_seconds,
        "changed_slot_count": record.changed_slot_count,
        "total_comparable_slots": record.total_comparable_slots,
        "changed_slot_rate": record.changed_slot_rate,
        "accepted": int(record.accepted),
        "attempt_count": 1,
        "tool_call_count": record.tool_call_count,
        "tool_call_counts_by_type": record.tool_call_counts_by_type,
        "successful_tool_call_count": record.successful_tool_call_count,
        "failed_tool_call_count": record.failed_tool_call_count,
        "verification_count": record.verification_count,
        "model_calls": record.model_calls,
        "repair_model_calls": record.repair_model_calls,
        "verification_model_calls": record.verification_model_calls,
        "failed_model_calls": record.failed_model_calls,
    }


def summarize_repair_history(history: list[dict]) -> dict:
    """Summarize a shared-loop history beginning with step-0 verification.

    Requires a repair_attempt on every later entry. Rejects mixed runs,
    out-of-order steps, and before states inconsistent with accepted history.
    An initial-only history has unknown identity, zero attempts/totals, and
    undefined means/acceptance rate. Legacy histories need explicit conversion.
    """
    if not history or history[0].get("step") != 0:
        raise ValueError("History must begin with step-0 verification")
    initial = history[0].get("verification", {}).get("personal_constraints")
    if not isinstance(initial, list) or any(
        value is not None and type(value) is not bool for value in initial
    ):
        raise ValueError("Step-0 personal_constraints must be a list of bool or None")
    current = list(initial)
    accepted_verification = history[0].get("verification", {})
    rows = []
    records = []
    attempts_until_success = 0 if history[0].get("verification", {}).get("passed") is True else None
    query_uid = repair_strategy = None
    previous_step = 0
    for entry in history[1:]:
        if "repair_attempt" not in entry:
            raise ValueError("Every proposal must contain a repair_attempt record")
        record = coerce_repair_attempt(entry["repair_attempt"])
        if record.step <= previous_step or entry.get("step") != record.step:
            raise ValueError("History steps must increase and match repair_attempt steps")
        if record.before_personal_constraints != current:
            raise ValueError("Attempt before state does not match the accepted trajectory")
        if record.query_uid is not None:
            if query_uid is not None and query_uid != record.query_uid:
                raise ValueError("History contains multiple query UIDs")
            query_uid = record.query_uid
        if repair_strategy is not None and repair_strategy != record.repair_strategy:
            raise ValueError("History contains multiple repair strategies")
        repair_strategy = record.repair_strategy
        rows.append(compute_attempt_metrics(record))
        records.append(record)
        if attempts_until_success is None and record.accepted and entry.get("verification", {}).get("passed") is True:
            attempts_until_success = len(rows)
        if record.accepted:
            current = list(record.after_personal_constraints)
            accepted_verification = entry.get("verification", {})
        previous_step = record.step

    def total(name):
        return sum(row[name] for row in rows)

    def complete_total(name):
        return _complete_sum([row[name] for row in rows])

    attempts = len(rows)
    accepted_attempts = total("accepted")
    input_total = complete_total("input_tokens_delta")
    output_total = complete_total("output_tokens_delta")
    time_total = complete_total("repair_time_seconds")
    final_passed = sum(value is True for value in current)
    final_failed = sum(value is False for value in current)
    scopes = [record.editable_scope for record in records]
    levels = [record.scope_level or {"slot": 1, "day": 2, "plan": 3}.get(record.editable_scope) for record in records]
    known_levels = [level for level in levels if level is not None]
    previous_level = None
    escalation_count = 0
    for record, level in zip(records, levels):
        if previous_level is not None and level is not None and level > previous_level:
            escalation_count += 1
        if level is not None:
            previous_level = level
    from collections import Counter
    tool_types = Counter()
    for record in records:
        tool_types.update(record.tool_call_counts_by_type or {})
    initial_count = history[0].get("system_metrics", {}).get("verification_count")
    repair_count = complete_total("verification_count")
    return {
        "total_execution_time_s": history[0].get("pipeline_system_metrics", {}).get("total_execution_time_s"),
        "repair_attempt_count": attempts,
        "tool_call_count": complete_total("tool_call_count"),
        "repair_tool_calls": complete_total("tool_call_count"),
        "tool_call_counts_by_type": dict(sorted(tool_types.items())) if all(record.tool_call_counts_by_type is not None for record in records) else None,
        "successful_tool_call_count": complete_total("successful_tool_call_count"),
        "failed_tool_call_count": complete_total("failed_tool_call_count"),
        "repair_verification_count": repair_count,
        "repair_verification_iterations": repair_count,
        "initial_verification_count": initial_count,
        "verification_count_total": initial_count + repair_count if initial_count is not None and repair_count is not None else None,
        "query_uid": query_uid,
        "repair_strategy": repair_strategy,
        "attempts": attempts,
        "accepted_attempts": accepted_attempts,
        "rejected_attempts": attempts - accepted_attempts,
        "acceptance_rate": _ratio(accepted_attempts, attempts),
        "rejection_rate": _ratio(attempts - accepted_attempts, attempts),
        "failed_attempts": sum(record.exception is not None for record in records),
        "decision_rejected_attempts": sum(not record.accepted and record.exception is None for record in records),
        "decision_rejection_rate": _ratio(
            sum(not record.accepted and record.exception is None for record in records),
            sum(record.exception is None for record in records)),
        "attempts_until_success": attempts_until_success,
        "repair_success": accepted_verification.get("passed"),
        "mean_targeted_repair_success_rate": _defined_mean([row["targeted_repair_success_rate"] for row in rows]),
        "targeted_repair_success_rate": _ratio(total("targeted_fixed_count"), total("targeted_failed_before_count")),
        "total_targeted_fixed": total("targeted_fixed_count"),
        "total_targeted_failed_before": total("targeted_failed_before_count"),
        "total_fixed": total("fixed_count"),
        "total_newly_violated": total("newly_violated_count"),
        "cumulative_net_repair_gain": total("net_repair_gain"),
        "mean_repair_success_rate": _defined_mean([row["repair_success_rate"] for row in rows]),
        "mean_new_violation_rate": _defined_mean([row["new_violation_rate"] for row in rows]),
        "accepted_total_fixed": total("accepted_fixed_count"),
        "accepted_total_newly_violated": total("accepted_newly_violated_count"),
        "accepted_cumulative_net_repair_gain": total("accepted_net_repair_gain"),
        "total_input_tokens_delta": input_total,
        "total_output_tokens_delta": output_total,
        "total_tokens_delta": complete_total("total_tokens_delta"),
        "total_token_data_complete": complete_total("total_tokens_delta") is not None,
        "token_data_complete": input_total is not None and output_total is not None,
        "total_repair_time_seconds": time_total,
        "timing_data_complete": time_total is not None,
        "model_calls": complete_total("model_calls"),
        "model_call_data_complete": complete_total("model_calls") is not None,
        "repair_model_calls": complete_total("repair_model_calls"),
        "verification_model_calls": complete_total("verification_model_calls"),
        "failed_model_calls": complete_total("failed_model_calls"),
        "total_verification_time_seconds": complete_total("verification_time_seconds"),
        "total_attempt_time_seconds": complete_total("attempt_time_seconds"),
        "changed_slot_count": complete_total("changed_slot_count"),
        "total_comparable_slots": complete_total("total_comparable_slots"),
        "changed_slot_rate": _ratio(complete_total("changed_slot_count"), complete_total("total_comparable_slots")) if all(row["changed_slot_count"] is not None for row in rows) else None,
        "mean_changed_slot_count": _defined_mean([row["changed_slot_count"] for row in rows]),
        "mean_changed_slot_rate": _defined_mean([row["changed_slot_rate"] for row in rows]),
        "footprint_measured_attempts": sum(row["changed_slot_count"] is not None for row in rows),
        "attempts_scope_slot": scopes.count("slot"), "attempts_scope_day": scopes.count("day"),
        "attempts_scope_plan": scopes.count("plan"), "attempts_scope_unavailable": scopes.count(None),
        "escalation_count": escalation_count if len(known_levels) == len(records) else None,
        "highest_scope_level": max(known_levels) if known_levels and len(known_levels) == len(records) else None,
        "scope_data_complete": len(known_levels) == len(records),
        "initial_failed_count": sum(value is False for value in initial),
        "final_failed_count": final_failed,
        "initial_unknown_count": sum(value is None for value in initial),
        "final_unknown_count": sum(value is None for value in current),
        "final_personal_constraint_satisfaction_rate": _ratio(final_passed, final_passed + final_failed),
        "final_all_personal_constraints_pass": _all_pass(current),
    }
