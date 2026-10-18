"""Deterministic explicit-provenance grouping and validated split manifests."""
import hashlib
import json
import math
from pathlib import Path

GROUPING_FIELDS = ("semantic_case_id", "case_id", "base_case_id", "parent_case_id", "source_plan_uid")


def query_group(record):
    uid = record.get("uid")
    if not isinstance(uid, str) or not uid:
        raise ValueError("Every query requires a nonempty string uid")
    for field in GROUPING_FIELDS:
        value = record.get(field)
        if value is not None:
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field} must be a nonempty string")
            return value, field
    return uid, "query_uid"


def build_split(records, train_fraction=0.7, seed=42):
    if type(seed) is not int or type(train_fraction) not in (int, float) or not math.isfinite(train_fraction) or not 0 < train_fraction < 1:
        raise ValueError("Require integer seed and 0 < train_fraction < 1")
    groups, provenance, seen = {}, {}, set()
    for record in records:
        group, field = query_group(record)
        uid = record["uid"]
        if uid in seen:
            raise ValueError(f"Duplicate query UID: {uid}")
        seen.add(uid)
        groups.setdefault(group, []).append(uid)
        provenance[uid] = {"group_id": group, "grouping_field": field}
    if len(groups) < 2:
        raise ValueError("Need at least two groups for nonempty train and test")
    # Stable hash ranking avoids input-order and RNG-version dependencies.
    ranked = sorted(groups, key=lambda group: (hashlib.sha256(json.dumps([seed, group], ensure_ascii=False).encode()).hexdigest(), group))
    train_size = max(1, min(len(groups) - 1, math.floor(len(groups) * train_fraction)))
    train_groups = set(ranked[:train_size])
    manifest = {"format_version": 1, "algorithm": "sha256-seed-group-ranking-v1", "seed": seed,
                "train_fraction": train_fraction, "grouping_priority": list(GROUPING_FIELDS) + ["query_uid"],
                "train": [], "test": [], "groups": {}, "queries": provenance}
    for group in sorted(groups):
        partition = "train" if group in train_groups else "test"
        uids = sorted(groups[group])
        manifest[partition].extend(uids)
        manifest["groups"][group] = {"split": partition, "query_uids": uids}
    manifest["train"].sort()
    manifest["test"].sort()
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("format_version") != 1:
        raise ValueError("Unsupported split manifest")
    partitions = {}
    for name in ("train", "test"):
        uids = manifest.get(name)
        if not isinstance(uids, list) or any(not isinstance(uid, str) or not uid for uid in uids) or len(uids) != len(set(uids)):
            raise ValueError(f"Invalid/duplicate {name} query UIDs")
        partitions[name] = set(uids)
    if partitions["train"] & partitions["test"]:
        raise ValueError("Query leakage across train/test")
    groups, queries = manifest.get("groups"), manifest.get("queries")
    if not isinstance(groups, dict) or not isinstance(queries, dict):
        raise ValueError("Missing grouping audit data")
    observed = set()
    for group, item in groups.items():
        if not isinstance(group, str) or not group or not isinstance(item, dict) or item.get("split") not in partitions:
            raise ValueError("Invalid group")
        uids = item.get("query_uids")
        if not isinstance(uids, list) or not uids:
            raise ValueError("Group must have query UIDs")
        for uid in uids:
            if not isinstance(uid, str) or uid in observed or uid not in partitions[item["split"]]:
                raise ValueError("Duplicate query or group leakage across train/test")
            if not isinstance(queries.get(uid), dict) or queries[uid].get("group_id") != group or queries[uid].get("grouping_field") not in (*GROUPING_FIELDS, "query_uid"):
                raise ValueError("Query/group audit mismatch")
            observed.add(uid)
    if observed != partitions["train"] | partitions["test"] or observed != set(queries):
        raise ValueError("Manifest membership is incomplete/inconsistent")
    return manifest


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path):
    return validate_manifest(json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object))


def partition_uids(manifest, partition):
    validate_manifest(manifest)
    if partition not in ("train", "test"):
        raise ValueError("Partition must be train or test")
    return set(manifest[partition])


def select_queries(queries, manifest, partition):
    selected = partition_uids(manifest, partition)
    missing = selected - set(queries)
    if missing:
        raise ValueError(f"Selected partition queries unavailable: {sorted(missing)}")
    for uid in selected:
        record = queries[uid]
        if record.get("uid") != uid:
            raise ValueError("Query UID mismatch")
        group, field = query_group(record)
        if manifest["queries"][uid] != {"group_id": group, "grouping_field": field}:
            raise ValueError("Query grouping differs from manifest")
    return {uid: queries[uid] for uid in sorted(selected)}


def filter_attempts(records, manifest, partition):
    selected = partition_uids(manifest, partition)
    known = set(manifest["queries"])
    result = []
    for record in records:
        uid = record.get("repair_attempt", record).get("query_uid")
        if uid not in known:
            raise ValueError(f"Attempt query UID missing or absent from split manifest: {uid!r}")
        if uid in selected:
            result.append(record)
    return result
