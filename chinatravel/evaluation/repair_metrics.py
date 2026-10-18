"""Pure personal-constraint repair metrics; no verifier, database, or LLM calls."""

from statistics import mean

from chinatravel.evaluation.repair_attempt import RepairAttemptRecord


def _as_record(record: RepairAttemptRecord | dict) -> RepairAttemptRecord:
    if isinstance(record, RepairAttemptRecord):
        record.validate()
        return record
    return RepairAttemptRecord.from_dict(record)


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
    record = _as_record(record)
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
        "total_tokens_delta": _complete_sum(
            [record.input_tokens_delta, record.output_tokens_delta]
        ),
        "repair_time_seconds": record.repair_time_seconds,
        "accepted": int(record.accepted),
        "attempt_count": 1,
        "model_calls": None,
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
    rows = []
    query_uid = repair_strategy = None
    previous_step = 0
    for entry in history[1:]:
        if "repair_attempt" not in entry:
            raise ValueError("Every proposal must contain a repair_attempt record")
        record = _as_record(entry["repair_attempt"])
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
        if record.accepted:
            current = list(record.after_personal_constraints)
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
    return {
        "query_uid": query_uid,
        "repair_strategy": repair_strategy,
        "attempts": attempts,
        "accepted_attempts": accepted_attempts,
        "rejected_attempts": attempts - accepted_attempts,
        "acceptance_rate": _ratio(accepted_attempts, attempts),
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
        "total_tokens_delta": _complete_sum([input_total, output_total]),
        "token_data_complete": input_total is not None and output_total is not None,
        "total_repair_time_seconds": time_total,
        "timing_data_complete": time_total is not None,
        "model_calls": None,
        "initial_failed_count": sum(value is False for value in initial),
        "final_failed_count": final_failed,
        "initial_unknown_count": sum(value is None for value in initial),
        "final_unknown_count": sum(value is None for value in current),
        "final_personal_constraint_satisfaction_rate": _ratio(final_passed, final_passed + final_failed),
        "final_all_personal_constraints_pass": _all_pass(current),
    }
