"""Offline, attempt-level regression matrices from explicit single targets."""

from collections import defaultdict
from copy import deepcopy
import csv
import json
from pathlib import Path

from chinatravel.evaluation.constraint_families import (
    CONSTRAINT_FAMILIES, NORMALIZER_VERSION, classify_constraints,
)
from chinatravel.evaluation.repair_attempt import coerce_repair_attempt

TAXONOMY_VERSION = "1.0.0"
MATRIX_DEFINITION_VERSION = "1.0.0"
PERSPECTIVES = ("candidate", "accepted_trajectory")
CONTRIBUTION_COLUMNS = (
    "run_id", "query_uid", "step", "repair_strategy", "source_constraint_index",
    "source_family", "destination_family", "perspective", "eligible", "regression",
    "accepted", "exclusion_reason", "target_provenance", "target_mapping_status",
    "descriptor_exclusions", "taxonomy_version", "normalizer_version",
    "matrix_definition_version",
    "target_count", "concurrent_failed_count", "concurrent_commonsense_failure_count",
    "feedback_personal_constraint_count", "feedback_commonsense_failure_count",
    "editable_scope", "scope_level", "protected_constraint_count", "escalation_reason",
    "is_single_target", "is_isolated_personal_target", "has_concurrent_commonsense_failure",
)
AGGREGATE_COLUMNS = (
    "repair_strategy", "perspective", "source_family", "destination_family",
    "regression_count", "eligible_count", "support_count", "regression_rate", "support_attempts",
    "support_queries", "unknown_after_excluded_attempts", "taxonomy_version",
    "normalizer_version", "matrix_definition_version", "counting_unit", "target_policy",
)
SCOPE_AGGREGATE_COLUMNS = ("repair_strategy", "editable_scope", *AGGREGATE_COLUMNS[1:])
_VERSIONS = dict(taxonomy_version=TAXONOMY_VERSION,
                 normalizer_version=NORMALIZER_VERSION,
                 matrix_definition_version=MATRIX_DEFINITION_VERSION)


def _prepare(records, run_id):
    """Accept records or {run_id, repair_attempt} envelopes; deduplicate attempts."""
    unique = {}
    duplicates = 0
    for item in records:
        item_run = run_id
        if isinstance(item, dict) and "repair_attempt" in item:
            item_run = item.get("run_id", run_id)
            item = item["repair_attempt"]
        if not isinstance(item_run, str) or not item_run:
            raise ValueError("Every attempt needs a nonempty run_id")
        record = deepcopy(coerce_repair_attempt(item))
        payload = record.to_dict()
        key = (item_run, record.query_uid, record.step)
        if key in unique:
            if unique[key][1].to_dict() != payload:
                raise ValueError(f"Conflicting duplicate attempt identity: {key!r}")
            duplicates += 1
            continue
        unique[key] = (item_run, record)
    return list(unique.values()), duplicates


def _classifications(record):
    count = len(record.before_personal_constraints)
    mapping = {}
    exclusions = []
    for classification in classify_constraints(record.constraint_descriptors):
        index = classification["constraint_index"]
        if index > count:
            raise ValueError("Constraint descriptor index exceeds the verifier vector")
        mapping[index] = classification
        if classification["classification_status"] != "mapped":
            exclusions.append({"constraint_index": index,
                               "classification_status": classification["classification_status"],
                               "reason": classification["reason"]})
    for index in range(1, count + 1):
        if index not in mapping:
            exclusions.append({"constraint_index": index,
                               "classification_status": "missing_descriptor",
                               "reason": "missing_descriptor"})
    return mapping, exclusions


def _source(record, mapping):
    targets = record.target_constraint_indices
    if len(targets) != 1:
        return None, None, None, "zero_targets" if not targets else "multiple_targets"
    index = targets[0]
    classification = mapping.get(index)
    status = classification["classification_status"] if classification else "missing_descriptor"
    family = classification["family"] if classification else None
    if record.before_personal_constraints[index - 1] is not False:
        return index, family, status, "source_not_false"
    if status != "mapped":
        return index, family, status, "source_" + status
    return index, family, status, None


def _coverage_summary(audits):
    """One coverage implementation for global, strategy and scope populations."""
    coverage = {
        "total_repair_attempts": 0,
        "zero_target_attempts": 0, "single_target_attempts": 0, "multi_target_attempts": 0,
        "target_mapping": {status: 0 for status in ("mapped", "unmapped", "ambiguous", "compound")},
        "target_missing_descriptor_instances": 0,
        "source_target_not_false_attempts": 0, "attempts_missing_descriptors": 0,
        "missing_descriptor_instances": 0, "missing_query_uid_attempts": 0,
        "destination_unknown_after_excluded_contributions": 0,
        "destination_unknown_after_excluded_attempts": 0,
        "candidate_eligible_contributions": 0, "accepted_eligible_contributions": 0,
        "isolated_single_target_attempts": 0, "single_target_with_other_personal_failures_attempts": 0,
        "concurrent_commonsense_failure_attempts": 0, "missing_target_provenance_attempts": 0,
        "missing_editable_scope_attempts": 0,
    }
    queries = set()
    for record, mapping, exclusions, eligible_count, unknown_count in audits:
        coverage["total_repair_attempts"] += 1
        targets = record.target_constraint_indices
        coverage[("zero_target_attempts" if not targets else "single_target_attempts"
                  if len(targets) == 1 else "multi_target_attempts")] += 1
        failed = len(record.concurrent_failed_constraint_indices)
        coverage["isolated_single_target_attempts"] += int(len(targets) == 1 and failed == 1)
        coverage["single_target_with_other_personal_failures_attempts"] += int(len(targets) == 1 and failed > 1)
        coverage["concurrent_commonsense_failure_attempts"] += int((record.concurrent_commonsense_failure_count or 0) > 0)
        coverage["missing_target_provenance_attempts"] += int(record.target_provenance is None)
        coverage["missing_editable_scope_attempts"] += int(record.editable_scope is None)
        if record.query_uid is None:
            coverage["missing_query_uid_attempts"] += 1
        else:
            queries.add(record.query_uid)
        missing = sum(row["classification_status"] == "missing_descriptor" for row in exclusions)
        coverage["attempts_missing_descriptors"] += int(missing > 0)
        coverage["missing_descriptor_instances"] += missing
        for index in targets:
            if index not in mapping:
                coverage["target_missing_descriptor_instances"] += 1
            else:
                coverage["target_mapping"][mapping[index]["classification_status"]] += 1
        if len(targets) == 1 and record.before_personal_constraints[targets[0] - 1] is not False:
            coverage["source_target_not_false_attempts"] += 1
        coverage["candidate_eligible_contributions"] += eligible_count
        coverage["accepted_eligible_contributions"] += eligible_count
        coverage["destination_unknown_after_excluded_contributions"] += unknown_count
        coverage["destination_unknown_after_excluded_attempts"] += int(unknown_count > 0)
    coverage["distinct_query_count"] = len(queries)
    return coverage


def build_regression_matrix(records, run_id="default") -> dict:
    """Return contributions, aggregate rows, and coverage from validated records.

    Only explicit targets are used. Identity is (run_id, query_uid, step);
    identical repeats are deduplicated, conflicting repeats raise ValueError.
    No histories are inferred and no R0 targets are synthesized.
    """
    prepared, duplicates = _prepare(records, run_id)
    contributions = []
    audits = []
    for item_run, record in prepared:
        targets = record.target_constraint_indices
        mapping, exclusions = _classifications(record)
        source_index, source_family, source_status, source_reason = _source(record, mapping)
        destinations = defaultdict(list)
        for index, classification in mapping.items():
            if classification["classification_status"] == "mapped":
                destinations[classification["family"]].append(index - 1)
        unknown_count = eligible_count = 0
        for destination in CONSTRAINT_FAMILIES:
            indices = destinations[destination]
            reason = source_reason
            if reason is None:
                if source_family == destination:
                    reason = "structurally_ineligible_diagonal"
                elif not indices:
                    reason = "destination_family_absent"
                elif not all(record.before_personal_constraints[i] is True for i in indices):
                    reason = "destination_not_all_pass_before"
                elif any(record.after_personal_constraints[i] is None for i in indices):
                    reason = "destination_unknown_after"
                    unknown_count += 1
            eligible = reason is None
            eligible_count += int(eligible)
            regressed = eligible and any(record.after_personal_constraints[i] is False for i in indices)
            for perspective in PERSPECTIVES:
                contributions.append({
                    "run_id": item_run, "query_uid": record.query_uid, "step": record.step,
                    "repair_strategy": record.repair_strategy,
                    "source_constraint_index": source_index, "source_family": source_family,
                    "destination_family": destination, "perspective": perspective,
                    "eligible": eligible,
                    "regression": bool(regressed and (perspective == "candidate" or record.accepted)) if eligible else None,
                    "accepted": record.accepted, "exclusion_reason": reason,
                    "target_provenance": record.target_provenance,
                    "target_count": len(targets),
                    "concurrent_failed_count": len(record.concurrent_failed_constraint_indices),
                    "concurrent_commonsense_failure_count": record.concurrent_commonsense_failure_count,
                    "feedback_personal_constraint_count": (len(record.feedback_personal_constraint_indices)
                        if record.feedback_personal_constraint_indices is not None else None),
                    "feedback_commonsense_failure_count": record.feedback_commonsense_failure_count,
                    "editable_scope": record.editable_scope, "scope_level": record.scope_level,
                    "protected_constraint_count": len(record.protected_constraint_indices),
                    "escalation_reason": record.escalation_reason,
                    "is_single_target": len(targets) == 1,
                    "is_isolated_personal_target": len(targets) == 1 and len(record.concurrent_failed_constraint_indices) == 1,
                    "has_concurrent_commonsense_failure": (record.concurrent_commonsense_failure_count > 0
                        if record.concurrent_commonsense_failure_count is not None else None),
                    "target_mapping_status": source_status,
                    "descriptor_exclusions": json.dumps(exclusions, sort_keys=True), **_VERSIONS,
                })
        audits.append((record, mapping, exclusions, eligible_count, unknown_count))
    coverage = {**_coverage_summary(audits), "duplicate_records_ignored": duplicates, **_VERSIONS}
    by_strategy, by_scope = defaultdict(list), defaultdict(list)
    for audit in audits:
        record = audit[0]
        by_strategy[record.repair_strategy].append(audit)
        by_scope[(record.repair_strategy, record.editable_scope)].append(audit)
    coverage["by_strategy"] = [{"repair_strategy": strategy, **_coverage_summary(group)}
                               for strategy, group in sorted(by_strategy.items())]
    coverage["by_strategy_scope"] = [{"repair_strategy": strategy, "editable_scope": scope,
                                     **_coverage_summary(group)}
        for (strategy, scope), group in sorted(by_scope.items(), key=lambda pair: (pair[0][0], pair[0][1] or ""))]
    return {"contributions": contributions,
            "aggregate": aggregate_contributions(contributions),
            "aggregate_by_scope": aggregate_contributions(contributions, by_scope=True), "coverage": coverage}


def build_contribution_table(records, run_id="default") -> list[dict]:
    return build_regression_matrix(records, run_id)["contributions"]


def summarize_matrix_coverage(records, run_id="default") -> dict:
    return build_regression_matrix(records, run_id)["coverage"]


def aggregate_contributions(contributions, *, by_scope=False) -> list[dict]:
    """Aggregate once per stable contribution key; reject conflicting duplicates."""
    unique = {}
    strategies = set()
    for row in contributions:
        if any(row.get(name) != version for name, version in _VERSIONS.items()):
            raise ValueError("Cannot aggregate mixed or unsupported definition versions")
        if row["perspective"] not in PERSPECTIVES:
            raise ValueError("Unknown perspective")
        key = tuple(row[name] for name in ("run_id", "query_uid", "step", "perspective",
                                         "source_family", "destination_family"))
        if key in unique and unique[key] != row:
            raise ValueError(f"Conflicting duplicate contribution: {key!r}")
        unique[key] = row
        strategies.add((row["repair_strategy"], row.get("editable_scope") if by_scope else None))
    cells = defaultdict(list)
    for row in unique.values():
        cells[(row["repair_strategy"], row.get("editable_scope") if by_scope else None, row["perspective"], row["source_family"],
               row["destination_family"])].append(row)
    result = []
    for strategy, scope in sorted(strategies, key=lambda pair: (pair[0], pair[1] or "")):
        for perspective in PERSPECTIVES:
            for source in CONSTRAINT_FAMILIES:
                for destination in CONSTRAINT_FAMILIES:
                    if source == destination:
                        continue
                    rows = cells[(strategy, scope, perspective, source, destination)]
                    eligible = [row for row in rows if row["eligible"]]
                    attempts = {(row["run_id"], row["query_uid"], row["step"]) for row in eligible}
                    regressions = sum(row["regression"] is True for row in eligible)
                    result.append({
                        "repair_strategy": strategy, "perspective": perspective,
                        **({"editable_scope": scope} if by_scope else {}),
                        "source_family": source, "destination_family": destination,
                        "regression_count": regressions, "eligible_count": len(attempts),
                        "support_count": len(attempts),
                        "regression_rate": regressions / len(attempts) if attempts else None,
                        "support_attempts": len(attempts),
                        "support_queries": len({row["query_uid"] for row in eligible if row["query_uid"] is not None}),
                        "unknown_after_excluded_attempts": sum(
                            row["exclusion_reason"] == "destination_unknown_after" for row in rows),
                        **_VERSIONS, "counting_unit": "repair_attempt",
                        "target_policy": "single_explicit_failed_target",
                    })
    return result


def load_regression_matrix(directory, perspective="candidate") -> dict:
    """Load {source: {destination: {rate, support_count, regression_count}}}.

    Accepts the output root or a by_scope/<scope> directory. Missing rates are
    None. No strategy risk policy is applied. accepted_trajectory aliases accepted.
    """
    if perspective == "accepted_trajectory":
        perspective = "accepted"
    if perspective not in ("candidate", "accepted"):
        raise ValueError("Unknown perspective")
    matrices = {}
    for metric in ("rate", "support", "count"):
        path = Path(directory) / f"{perspective}_regression_{metric}.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["source_family", *CONSTRAINT_FAMILIES]:
                raise ValueError(f"Unexpected matrix columns: {path}")
            rows = list(reader)
        if [row["source_family"] for row in rows] != list(CONSTRAINT_FAMILIES):
            raise ValueError(f"Unexpected matrix rows: {path}")
        matrices[metric] = rows
    result = {}
    for index, source in enumerate(CONSTRAINT_FAMILIES):
        result[source] = {}
        for destination in CONSTRAINT_FAMILIES:
            raw_rate = matrices["rate"][index][destination]
            rate = float(raw_rate) if raw_rate else None
            support = int(matrices["support"][index][destination])
            count = int(matrices["count"][index][destination])
            if not 0 <= count <= support or (support == 0 and (rate is not None or count != 0)):
                raise ValueError("Inconsistent matrix counts/rate")
            if support and (rate is None or not abs(rate - count / support) <= 1e-12):
                raise ValueError("Inconsistent matrix counts/rate")
            result[source][destination] = dict(rate=rate, support_count=support, regression_count=count)
    return result
