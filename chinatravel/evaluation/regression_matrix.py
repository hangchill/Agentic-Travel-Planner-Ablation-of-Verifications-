"""Offline, attempt-level regression matrices from explicit single targets."""

from collections import defaultdict
import json

from chinatravel.evaluation.constraint_families import (
    CONSTRAINT_FAMILIES, NORMALIZER_VERSION, classify_constraints,
)
from chinatravel.evaluation.repair_attempt import RepairAttemptRecord

TAXONOMY_VERSION = "1.0.0"
MATRIX_DEFINITION_VERSION = "1.0.0"
PERSPECTIVES = ("candidate", "accepted_trajectory")
CONTRIBUTION_COLUMNS = (
    "run_id", "query_uid", "step", "repair_strategy", "source_constraint_index",
    "source_family", "destination_family", "perspective", "eligible", "regression",
    "accepted", "exclusion_reason", "target_provenance", "target_mapping_status",
    "descriptor_exclusions", "taxonomy_version", "normalizer_version",
    "matrix_definition_version",
)
AGGREGATE_COLUMNS = (
    "repair_strategy", "perspective", "source_family", "destination_family",
    "regression_count", "eligible_count", "regression_rate", "support_attempts",
    "support_queries", "unknown_after_excluded_attempts", "taxonomy_version",
    "normalizer_version", "matrix_definition_version", "counting_unit", "target_policy",
)
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
        if isinstance(item, RepairAttemptRecord):
            payload = item.to_dict()
        else:
            payload = RepairAttemptRecord.from_dict(item).to_dict()
        record = RepairAttemptRecord.from_dict(payload)
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


def _flat(value):
    return value if value is None or isinstance(value, (str, int, float, bool)) else json.dumps(value, sort_keys=True)


def build_regression_matrix(records, run_id="default") -> dict:
    """Return contributions, aggregate rows, and coverage from validated records.

    Only explicit targets are used. Identity is (run_id, query_uid, step);
    identical repeats are deduplicated, conflicting repeats raise ValueError.
    No histories are inferred and no R0 targets are synthesized.
    """
    prepared, duplicates = _prepare(records, run_id)
    contributions = []
    coverage = {
        "total_repair_attempts": len(prepared), "duplicate_records_ignored": duplicates,
        "zero_target_attempts": 0, "single_target_attempts": 0, "multi_target_attempts": 0,
        "target_mapping": {status: 0 for status in ("mapped", "unmapped", "ambiguous", "compound")},
        "target_missing_descriptor_instances": 0,
        "source_target_not_false_attempts": 0, "attempts_missing_descriptors": 0,
        "missing_descriptor_instances": 0, "missing_query_uid_attempts": 0,
        "destination_unknown_after_excluded_contributions": 0,
        "destination_unknown_after_excluded_attempts": 0,
        "candidate_eligible_contributions": 0, "accepted_eligible_contributions": 0,
        "distinct_query_count": len({r.query_uid for _, r in prepared if r.query_uid is not None}),
        **_VERSIONS,
    }
    for item_run, record in prepared:
        targets = record.target_constraint_indices
        coverage[("zero_target_attempts" if not targets else "single_target_attempts"
                  if len(targets) == 1 else "multi_target_attempts")] += 1
        if record.query_uid is None:
            coverage["missing_query_uid_attempts"] += 1
        mapping, exclusions = _classifications(record)
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
        source_index, source_family, source_status, source_reason = _source(record, mapping)
        destinations = defaultdict(list)
        for index, classification in mapping.items():
            if classification["classification_status"] == "mapped":
                destinations[classification["family"]].append(index - 1)
        unknown_excluded = False
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
                    unknown_excluded = True
                    coverage["destination_unknown_after_excluded_contributions"] += 1
            eligible = reason is None
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
                    "target_provenance": _flat(record.repair_metadata.get("target_provenance")),
                    "target_mapping_status": source_status,
                    "descriptor_exclusions": json.dumps(exclusions, sort_keys=True), **_VERSIONS,
                })
                if eligible:
                    coverage[("candidate_eligible_contributions" if perspective == "candidate"
                              else "accepted_eligible_contributions")] += 1
        coverage["destination_unknown_after_excluded_attempts"] += int(unknown_excluded)
    return {"contributions": contributions,
            "aggregate": aggregate_contributions(contributions), "coverage": coverage}


def build_contribution_table(records, run_id="default") -> list[dict]:
    return build_regression_matrix(records, run_id)["contributions"]


def summarize_matrix_coverage(records, run_id="default") -> dict:
    return build_regression_matrix(records, run_id)["coverage"]


def aggregate_contributions(contributions) -> list[dict]:
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
        strategies.add(row["repair_strategy"])
    cells = defaultdict(list)
    for row in unique.values():
        cells[(row["repair_strategy"], row["perspective"], row["source_family"],
               row["destination_family"])].append(row)
    result = []
    for strategy in sorted(strategies):
        for perspective in PERSPECTIVES:
            for source in CONSTRAINT_FAMILIES:
                for destination in CONSTRAINT_FAMILIES:
                    if source == destination:
                        continue
                    rows = cells[(strategy, perspective, source, destination)]
                    eligible = [row for row in rows if row["eligible"]]
                    attempts = {(row["run_id"], row["query_uid"], row["step"]) for row in eligible}
                    regressions = sum(row["regression"] is True for row in eligible)
                    result.append({
                        "repair_strategy": strategy, "perspective": perspective,
                        "source_family": source, "destination_family": destination,
                        "regression_count": regressions, "eligible_count": len(attempts),
                        "regression_rate": regressions / len(attempts) if attempts else None,
                        "support_attempts": len(attempts),
                        "support_queries": len({row["query_uid"] for row in eligible if row["query_uid"] is not None}),
                        "unknown_after_excluded_attempts": sum(
                            row["exclusion_reason"] == "destination_unknown_after" for row in rows),
                        **_VERSIONS, "counting_unit": "repair_attempt",
                        "target_policy": "single_explicit_failed_target",
                    })
    return result
