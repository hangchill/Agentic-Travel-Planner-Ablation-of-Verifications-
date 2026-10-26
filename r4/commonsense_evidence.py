"""Recover commonsense PASS-to-FAIL transitions from saved training histories."""

from collections import Counter
import hashlib
import json

from chinatravel.evaluation.constraint_families import CONSTRAINT_FAMILIES
from chinatravel.evaluation.regression_matrix import (
    _classifications, _is_unchanged_attempt, _source,
)
from chinatravel.evaluation.repair_attempt import coerce_repair_attempt
from r4.safety import train_uids

COMMONSENSE_FAMILY = "commonsense_repair"


def commonsense_state(verification):
    """Return PASS/FAIL, or None when a complete check is not recorded."""
    if not isinstance(verification, dict):
        return None
    errors = verification.get("commonsense_errors")
    if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
        return None
    if verification.get("verification_unavailable") or any(
        verification.get(key) for key in (
            "verifier_errors", "schema_errors", "translation_errors", "translation_failures",
        )
    ):
        return None
    return not errors


def history_evidence(matrix_root, strategy, attempt_ids, *, perspective):
    """Use the same source/no-op policy as the personal regression matrices.

    The before state follows accepted history only. Each history verification
    records the candidate, including rejected proposals. Accepted perspective
    keeps the candidate denominator and counts only accepted regressions, just
    like the existing personal matrices.
    """
    cells = {source: {"regression_count": 0, "support_count": 0, "query_uids": set()}
             for source in CONSTRAINT_FAMILIES}
    run_dir = matrix_root.parent if matrix_root.name == "regression_matrix" else matrix_root
    summary = {"status": "unavailable", "reason": "missing_repair_histories",
               "history_files": [], "eligible_attempts": [], "excluded_attempts": {}}
    paths = sorted((run_dir / "queries").glob(f"*/{strategy}-*.json"))
    if not paths:
        return None, summary

    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"{run_dir}: histories require a training run_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    allowed = train_uids(manifest.get("split_query_source", ""))
    expected_uids = set(manifest.get("query_uids", []))
    if not expected_uids or not expected_uids <= allowed:
        raise ValueError(f"{run_dir}: history provenance is outside the training split")
    summary["run_manifest"] = {"path": str(manifest_path),
                               "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    excluded = Counter()
    seen_uids, seen_attempts = set(), set()
    for path in paths:
        raw = path.read_bytes()
        data = json.loads(raw)
        uid = data.get("query_uid")
        if data.get("repair_strategy") != strategy or uid not in expected_uids or uid in seen_uids:
            raise ValueError(f"{path}: conflicting strategy or query identity")
        seen_uids.add(uid)
        summary["history_files"].append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
        current = data.get("initial_verification")
        previous_step = 0
        for entry in data.get("repair_history", []):
            step = entry.get("step")
            if step == 0:
                current = entry.get("verification")
                continue
            if not isinstance(step, int) or step != previous_step + 1:
                raise ValueError(f"{path}: repair history steps must be contiguous")
            previous_step = step
            identity = (data.get("matrix_run_id"), uid, step)
            if identity not in attempt_ids or identity in seen_attempts:
                raise ValueError(f"{path}: history attempt is missing or duplicated in matrix provenance: {identity}")
            seen_attempts.add(identity)
            after = entry.get("verification")
            reason = None
            payload = entry.get("repair_attempt")
            if not isinstance(payload, dict):
                reason = "missing_repair_attempt"
            else:
                record = coerce_repair_attempt(payload)
                if (record.query_uid != uid or record.step != step
                        or record.repair_strategy != strategy or record.accepted != entry.get("accepted")):
                    raise ValueError(f"{path}: inconsistent repair attempt identity")
                if (not isinstance(current, dict) or not isinstance(after, dict)
                        or record.before_personal_constraints != current.get("personal_constraints")
                        or record.after_personal_constraints != after.get("personal_constraints")):
                    raise ValueError(f"{path}: verification does not match repair attempt")
                mapping, _ = _classifications(record)
                _, source, _, reason = _source(record, mapping)
                if _is_unchanged_attempt(record):
                    reason = "unchanged_candidate"
                elif reason is None and source == COMMONSENSE_FAMILY:
                    reason = "structural_diagonal"
                elif reason is None and commonsense_state(current) is None:
                    reason = "commonsense_unknown_before"
                elif reason is None and commonsense_state(current) is False:
                    reason = "commonsense_not_pass_before"
                elif reason is None and commonsense_state(after) is None:
                    reason = "commonsense_unknown_after"
                if reason is None:
                    regressed = commonsense_state(after) is False and (
                        perspective == "candidate" or record.accepted)
                    cell = cells[source]
                    cell["support_count"] += 1
                    cell["regression_count"] += int(regressed)
                    cell["query_uids"].add(uid)
                    summary["eligible_attempts"].append({"query_uid": uid, "step": step,
                        "source_family": source, "regression": regressed, "accepted": record.accepted})
            if reason:
                excluded[reason] += 1
            if entry.get("accepted") is True:
                current = after

    missing_attempts = attempt_ids - seen_attempts
    missing_uids = expected_uids - seen_uids
    summary.update(status="partial" if missing_attempts or missing_uids else "available",
                   reason=None, history_query_count=len(seen_uids),
                   history_attempt_count=len(seen_attempts), missing_attempt_count=len(missing_attempts),
                   missing_query_uids=sorted(missing_uids), excluded_attempts=dict(sorted(excluded.items())))
    return cells, summary
