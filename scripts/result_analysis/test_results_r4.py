"""Analyze R4 TEST performance, R0/R4 differences and matrix-guidance coverage.

Run from any directory (full analysis uses the project's offline evaluator):
    python path/to/r4/r4-analysis/test_results_r4.py
    python test_results_r4.py --run PATH --output-dir PATH
    python test_results_r4.py --analysis all
    python test_results_r4.py --analysis r4
    python test_results_r4.py --analysis r0-vs-r4
    python test_results_r4.py --analysis guidance
    python test_results_r4.py --analysis coverage  # standard library only

The table counts unique queries, not attempts. Its four guidance categories are
mutually exclusive: supported only, unsupported only, both, or no logged
relationship. They cover the entire query trajectory and sum to total queries.
"Both" can span different attempts; it does not require both types in one prompt.
A relationship is supported when its logged support count is positive; zero or
missing support means unsupported/fallback guidance. Observed zero regression
probability still counts as supported evidence.

Relationships include ALL personal-target ranking entries (they all appear in
the R4 prompt) and commonsense_source_risks. recommended_risk_target is a copy
of one ranking entry, so it is not counted again. "No logged relationship" means
none anywhere in the query, including queries with zero repair attempts. This
describes the saved metadata; it does not prove no matrix was loaded or used.

A structural-guard failure is a nonempty proposal_rejected_reason. Parse
failures and ordinary verifier regressions are separate diagnostics. The guard
can replace a malformed proposal with the previous plan even if accepted=True.
Final selection uses selected_source and selected_step, not plan equality:
selecting an unchanged repaired outcome still counts as a repaired selection.

Outputs beside this script by default:
    test_results_r4.csv              Guidance partition, total, guard, selection.
    test_results_r4_queries.csv      Per-query categories, counts, and selection.
    test_results_r4_attempts.csv     Per-attempt evidence and guard diagnostics.
    test_results_r4_definitions.csv  Counting rules for the table.
    r4/, r0_vs_r4/, guidance/       Detailed results for the selected modes.
    ANALYSIS.md, README.md          Findings, methods and usage.
    figures/                       SVG charts for the Markdown report.

Locally scores saved plans; no model requests, new experiments or Excel edits.
"""

import argparse
import csv
import json
import contextlib
import hashlib
import io
import math
import os
import statistics
import sys
from html import escape
from collections import Counter, defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
GROUPS = {"Easy": "easy", "Med": "medium", "Hum": "human", "All": None}
TABLE_COLUMNS = ["Repair Strategy", "Metric", *GROUPS]
GUIDANCE_CATEGORIES = {
    "supported_only": "Supported only",
    "unsupported_only": "Unsupported only",
    "both": "Both supported and unsupported",
    "none": "No logged relationship",
}
METRICS = [
    (GUIDANCE_CATEGORIES["supported_only"], "supported_only",
     "At least one supported relationship and no unsupported relationship across "
     "the entire query. Positive support includes observed zero regression risk."),
    (GUIDANCE_CATEGORIES["unsupported_only"], "unsupported_only",
     "At least one unsupported relationship and no supported relationship across "
     "the entire query. Unsupported means zero or missing support_count."),
    (GUIDANCE_CATEGORIES["both"], "both",
     "At least one supported and at least one unsupported relationship across "
     "the entire query. They may appear in different attempts. Includes all "
     "personal ranking entries and commonsense guidance."),
    (GUIDANCE_CATEGORIES["none"], "none",
     "Zero logged relationship entries across the entire query. Includes queries "
     "with no repair attempts; does not mean the matrix was not loaded."),
    ("Total queries", "total_queries",
     "All completed manifest queries. The four guidance categories are mutually "
     "exclusive and sum to this total within each difficulty and overall."),
    ("# queries with structural-guard failure", "has_structural_guard_failure",
     "At least one attempt has a nonempty repair_metadata.proposal_rejected_reason. "
     "Excludes parse failures and ordinary constraint-verifier failures."),
    ("Final selection: initial plan / repaired outcome", "selection",
     "Count selected_source=initial and selected_step=0 versus non-initial source "
     "and positive selected_step. Uses saved final_state selection provenance, "
     "not whether the selected itinerary differs from the initial itinerary."),
]


def read_json(path):
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def logged_relationships(metadata):
    """Yield the entries supplied in the prompt without duplicating recommendation."""
    ranking = metadata.get("risk_target_ranking") or []
    # Support older artifacts that saved only the recommendation.
    if "risk_target_ranking" not in metadata and metadata.get("recommended_risk_target"):
        ranking = [metadata["recommended_risk_target"]]
    for target in ranking:
        yield from target.get("destination_risks") or []
    yield from metadata.get("commonsense_source_risks") or []


def is_supported(relationship):
    support = relationship.get("support_count")
    if support is None:
        return False
    if isinstance(support, bool) or not isinstance(support, (int, float)) or support < 0:
        raise ValueError(f"Invalid logged support_count: {support!r}")
    return support > 0


def guidance_category(supported_count, unsupported_count):
    """Assign exactly one category using evidence from the full trajectory."""
    if supported_count > 0 and unsupported_count > 0:
        return "both"
    if supported_count > 0:
        return "supported_only"
    if unsupported_count > 0:
        return "unsupported_only"
    return "none"


def load_queries(run_dir):
    """Use all manifest queries, including queries with no attempt records."""
    manifest = read_json(run_dir / "run_manifest.json")
    expected = manifest["query_uids"]
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("run_manifest.json must contain unique, nonempty query_uids")
    queries = {}
    for state_path in sorted((run_dir / "queries").glob("*/final_state.json")):
        state = read_json(state_path)
        uid = state["query_uid"]
        if uid in queries:
            raise ValueError(f"Duplicate final_state.json for {uid}")
        if state.get("execution_status") != "completed":
            raise ValueError(f"Query {uid} is not completed; refusing an incomplete table")
        reference_path = Path(state.get("reference_query") or "reference/query.json")
        if not reference_path.is_absolute():
            reference_path = state_path.parent / reference_path
        reference = read_json(reference_path)
        if reference.get("uid") != uid:
            raise ValueError(f"Reference query UID does not match final state: {uid}")
        group = str(reference.get("tag", "")).strip().lower()
        if group not in {"easy", "medium", "human"}:
            raise ValueError(f"Unknown difficulty tag for {uid}: {group!r}")
        source, step = state.get("selected_source"), state.get("selected_step")
        if source == "initial" and step == 0:
            selection = "initial"
        elif source and source != "initial" and isinstance(step, int) and step > 0:
            selection = "repaired"
        else:
            raise ValueError(f"Missing or inconsistent final selection for {uid}: {source}, {step}")
        queries[uid] = {
            "query_uid": uid, "difficulty": group, "selection": selection,
            "selected_source": source, "selected_step": step,
            "selected_matrix_used": state.get("selected_matrix_used"),
            "execution_status": state["execution_status"],
            "expected_attempt_count": state.get("repair_attempt_count_all_trials"),
            "final_state_path": str(state_path.relative_to(run_dir)),
        }
    if set(queries) != set(expected):
        raise ValueError(
            f"Manifest/final-state query mismatch: missing={sorted(set(expected)-set(queries))}, "
            f"unexpected={sorted(set(queries)-set(expected))}"
        )
    return queries


def load_attempts(run_dir, queries):
    attempts, seen = [], set()
    with (run_dir / "attempts.jsonl").open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            uid = record["query_uid"]
            if uid not in queries:
                raise ValueError(f"Unknown query at attempts.jsonl line {line_number}: {uid}")
            strategy = record.get("repair_strategy", "")
            if not strategy.startswith("R4"):
                raise ValueError(f"Unexpected non-R4 strategy at line {line_number}: {strategy}")
            identity = (uid, strategy, record["step"])
            if identity in seen:
                raise ValueError(f"Duplicate attempt at line {line_number}: {identity}")
            seen.add(identity)
            metadata = record.get("repair_metadata") or {}
            relationships = list(logged_relationships(metadata))
            supported = sum(is_supported(cell) for cell in relationships)
            reason = metadata.get("proposal_rejected_reason")
            attempts.append({
                "query_uid": uid, "difficulty": queries[uid]["difficulty"],
                "repair_strategy": strategy, "step": record["step"],
                "repair_phase": record.get("repair_phase"),
                "relationship_count": len(relationships),
                "supported_relationship_count": supported,
                "unsupported_relationship_count": len(relationships) - supported,
                "no_logged_relationship": not relationships,
                "structural_guard_failure": bool(reason),
                "structural_guard_reason": reason,
                "structural_guard_field_logged": "proposal_rejected_reason" in metadata,
                "parse_failed": metadata.get("parse_failed"),
                "accepted": record.get("accepted"),
                "matrix_guidance_policy": metadata.get("matrix_guidance_policy"),
                "matrix_path": metadata.get("risk_matrix_path"),
            })
    return attempts


def summarize_queries(queries, attempts):
    by_query = defaultdict(list)
    for attempt in attempts:
        by_query[attempt["query_uid"]].append(attempt)
    rows = []
    for uid, query in sorted(queries.items()):
        records = by_query[uid]
        expected = query["expected_attempt_count"]
        if expected is not None and expected != len(records):
            raise ValueError(f"{uid}: final state reports {expected} attempts, log has {len(records)}")
        if any(not row["structural_guard_field_logged"] for row in records):
            raise ValueError(f"{uid}: missing structural-guard metadata; cannot report zero safely")
        supported = sum(row["supported_relationship_count"] for row in records)
        unsupported = sum(row["unsupported_relationship_count"] for row in records)
        reasons = Counter(row["structural_guard_reason"] for row in records
                          if row["structural_guard_failure"])
        rows.append({
            "query_uid": uid, "difficulty": query["difficulty"],
            "attempt_count": len(records), "no_repair_attempts": not records,
            "guidance_category": guidance_category(supported, unsupported),
            "supported_relationship_count": supported,
            "unsupported_relationship_count": unsupported,
            "has_supported_guidance": supported > 0,
            "has_unsupported_guidance": unsupported > 0,
            "no_logged_relationship": supported + unsupported == 0,
            "attempts_without_logged_relationship": sum(row["no_logged_relationship"] for row in records),
            "supported_guidance_attempts": sum(row["supported_relationship_count"] > 0 for row in records),
            "unsupported_guidance_attempts": sum(row["unsupported_relationship_count"] > 0 for row in records),
            "has_structural_guard_failure": bool(reasons),
            "structural_guard_failure_attempts": sum(reasons.values()),
            "structural_guard_reasons": json.dumps(dict(sorted(reasons.items()))),
            "parse_failed_attempts": sum(row["parse_failed"] is True for row in records),
            "selection": query["selection"],
            "selected_source": query["selected_source"], "selected_step": query["selected_step"],
            "selected_matrix_used": query["selected_matrix_used"],
            "final_state_path": query["final_state_path"],
        })
    return rows


def build_table(query_rows):
    rows = []
    for metric, flag, _definition in METRICS:
        row = {"Repair Strategy": "R4", "Metric": metric}
        for label, group in GROUPS.items():
            cohort = [q for q in query_rows if group is None or q["difficulty"] == group]
            if flag == "selection":
                initial = sum(q["selection"] == "initial" for q in cohort)
                repaired = sum(q["selection"] == "repaired" for q in cohort)
                row[label] = f"{initial} / {repaired}"
            elif flag == "total_queries":
                row[label] = len(cohort)
            elif flag in GUIDANCE_CATEGORIES:
                row[label] = sum(q["guidance_category"] == flag for q in cohort)
            else:
                row[label] = sum(q[flag] for q in cohort)
        rows.append(row)
    for label in GROUPS:
        category_total = sum(row[label] for row in rows
                             if row["Metric"] in GUIDANCE_CATEGORIES.values())
        expected = next(row[label] for row in rows if row["Metric"] == "Total queries")
        if category_total != expected:
            raise ValueError(f"{label}: guidance categories sum to {category_total}, expected {expected}")
    return rows


def write_csv(path, rows, columns=None):
    # BOM makes the files convenient to open directly in Windows Excel.
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


# The following analysis modes share one loader and one set of metric definitions.
# Imports of the project's offline evaluator are deliberately lazy: coverage mode
# remains usable with the Python standard library alone.
ANALYSIS_VERSION = "2.0"
CORE_DEFINITIONS = [
    ("pc_pass_pct", "%", "Mean per-query benchmark PCs passed / requested PCs; each query has equal weight."),
    ("logical_micro_pct", "%", "Sum of benchmark PCs passed / sum of requested PCs; constraint-weighted."),
    ("logical_macro_pct", "%", "Queries satisfying every benchmark PC / all queries."),
    ("cs_failed", "checks/query", "Failed categories out of the 28 standard benchmark CS checks, not raw messages."),
    ("all_pass_pct", "%", "Queries passing schema, every PC and every CS check / all queries."),
    ("pc_fixed", "events", "Loop False -> True; repeated fixes of the same constraint count repeatedly."),
    ("pc_regressed", "events", "Loop True -> False; excludes Unknown -> False and True -> Unknown."),
    ("fix_rate_pct", "%", "False -> True / before-False opportunities with a known candidate result."),
    ("regression_rate_pct", "%", "True -> False / before-True opportunities with a known candidate result."),
    ("target_fix_rate_pct", "%", "False -> True on logged feedback targets / evaluable before-False target opportunities; advisory ranking is not inferred model intent."),
    ("unknown_recovered", "events", "Unknown -> known. Reported separately from confirmed fixes."),
    ("repair_tokens", "tokens/query", "Sum total_tokens_delta across all retained repair attempts; initialization excluded; missing is NA."),
    ("repair_time_s", "s/query", "Sum repair_time_seconds; excludes verification, orchestration and initialization."),
    ("strategy_time_s", "s/query", "Recorded strategy execution elapsed time including verification/overhead; excludes initialization."),
    ("end_to_end_time_s", "s/query", "Shared initialization elapsed time plus recorded strategy elapsed time; retained execution only."),
    ("guidance_category", "query or attempt", "Positive support only / zero-or-missing support only / both / no relationship; grain is explicit."),
    ("cs_fixed", "check events", "Benchmark CS failure category present before and absent after; locally scored saved translated plans."),
    ("edge_regression", "family opportunity", "Any passing PC in a destination family becomes False; single-target-family/CS edges are flagged separately from multi-target advice."),
    ("recovered_regression", "constraint instance", "A PC broken at least once and passing at loop endpoint; events and distinct constraints are separate."),
]


def avg(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def med(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def ratio(numerator, denominator):
    return 100 * numerator / denominator if denominator else None


def complete_sum(values):
    values = list(values)
    return sum(values) if all(v is not None for v in values) else None


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def export_csv(path, rows, columns=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = columns or list(dict.fromkeys(k for row in rows for k in row)) or ["no_rows"]
    prepared = [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list, tuple))
                 else v for k, v in row.items()} for row in rows]
    write_csv(path, prepared, columns)


def transition(before, after):
    if before is False and after is True:
        return "fixed"
    if before is True and after is False:
        return "regressed"
    if before is None and after is not None:
        return "unknown_to_pass" if after is True else "unknown_to_fail"
    if before is not None and after is None:
        return "known_to_unknown"
    return "still_unknown" if before is None else "still_passed" if before else "still_failed"


def score_saved(team, uid, reference, plan, language, cache, standard_checks):
    """Score saved plans locally. The existing helper owns the 28-check policy."""
    key = (uid, language, canonical_hash(reference), canonical_hash(plan))
    if key not in cache:
        if not isinstance(plan, dict):
            raise ValueError(f"{uid}: missing saved translated plan; cannot rescore")
        cache[key] = team.score_plans([uid], {uid: reference}, {uid: plan}, language)[uid]
        scored = cache[key]
        # Some evaluator functions omit a zero-failure column for a single plan.
        # The saved full-cohort benchmark defines the fixed category universe.
        if not set(scored["cs_failed"]) <= set(standard_checks):
            raise ValueError(f"{uid}: local evaluator emitted an unknown CS check")
        if scored["cs_exception"]:
            scored["cs_failed"] = list(standard_checks)
        scored["cs_total"] = len(standard_checks)
    return cache[key]


def guidance_cells(metadata):
    for target in metadata.get("risk_target_ranking") or []:
        for cell in target.get("destination_risks") or []:
            yield target.get("family") or "unmapped", cell
    for cell in metadata.get("commonsense_source_risks") or []:
        yield "commonsense_repair", cell


def extract_run(role, root, cache):
    """One query/attempt/constraint data model for all three descriptive modes."""
    from scripts.result_analysis import build_test_result_tables as team
    from chinatravel.evaluation.constraint_families import classify_constraints
    from chinatravel.evaluation.repair_comparison import pair_path
    root = root.resolve()
    manifest = read_json(root / "run_manifest.json")
    ids = manifest["query_uids"]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{root}: duplicate manifest query IDs")
    if not str(manifest.get("split_query_source", "")).endswith("_test"):
        raise ValueError(f"{root}: expected a TEST split")
    bench = team.benchmark_dir(root, role)
    references = read_json(bench / "evaluation_population.json")["queries"]
    if set(references) != set(ids):
        raise ValueError(f"{role}: benchmark and manifest populations differ")
    origin = read_json(PROJECT_ROOT / "chinatravel/evaluation/splits/subset_origin.json")["origin"]
    summary = {r["query_uid"]: r for r in csv.DictReader((root / "summaries.csv").open(encoding="utf-8-sig", newline=""))}
    if set(summary) != set(ids):
        raise ValueError(f"{role}: summary population mismatch")
    stream = defaultdict(list)
    with (root / "attempts.jsonl").open(encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                a = json.loads(line)
                if a["query_uid"] not in ids or a.get("repair_strategy") != role:
                    raise ValueError(f"{role}: unexpected attempt identity")
                # Do not retain enormous prompt/raw-plan copies in memory.
                m = a.get("repair_metadata") or {}
                compact = {k: v for k, v in a.items()
                           if k not in ("candidate_plan", "accepted_plan_after", "repair_metadata")}
                compact["repair_metadata"] = {k: v for k, v in m.items()
                    if k not in ("prompt", "raw_response", "full_verification_report",
                                 "editable_slots", "per_target_edits", "targeted_constraints")}
                compact["request_error_reply"] = "Request failed, please try again." in str(m.get("raw_response") or "")
                stream[a["query_uid"]].append(compact)
    data = dict(role=role, root=root, manifest=manifest, references=references,
                queries=[], attempts=[], constraints=[], events=[], cs_events=[], cs_endpoints=[],
                edges=[], states=[], validation=[], sources=[])
    logical = {r["data_id"]: r for r in csv.DictReader((bench / "logical_py.csv").open(encoding="utf-8-sig", newline=""))}
    cs_file_rows = {r["data_id"]: r for r in csv.DictReader((bench / "commonsense.csv").open(encoding="utf-8-sig", newline=""))}
    standard_checks = [c for c in next(iter(cs_file_rows.values())) if c not in ("data_id", team.CS_EXCEPTION_COLUMN)]
    if len(standard_checks) != 28:
        raise ValueError(f"{role}: saved benchmark must define 28 standard CS checks")
    for ordinal, uid in enumerate(ids, 1):
        cp_path = pair_path(root, uid, role)
        cp = read_json(cp_path)
        qdir = cp_path.parent.parent if cp_path.parent.name == "trials" else cp_path.parent
        initial = read_json(qdir / "initial_state.json")
        exported = read_json(qdir / "final_state.json") if role == "R4" else cp
        records = sorted(stream[uid], key=lambda a: a["step"])
        if len({a["step"] for a in records}) != len(records):
            raise ValueError(f"{role}/{uid}: duplicate attempt steps")
        if len(records) != len(cp.get("repair_attempts", [])):
            raise ValueError(f"{role}/{uid}: canonical attempt log/checkpoint count mismatch")
        if cp.get("execution_status") != "completed":
            raise ValueError(f"{role}/{uid}: incomplete execution")
        hist = {h["step"]: h for h in cp["repair_history"]}
        reference = references[uid]
        original = team.original_code(reference)
        mapped = {c["constraint_index"]: c for c in classify_constraints(
            [{"constraint_index": i, "hard_logic_py": code} for i, code in enumerate(original, 1)])}
        descriptors = {i: dict(kind=team.constraint_kind(code),
                              family=mapped.get(i, {}).get("family") or "unmapped",
                              classification_status=mapped.get(i, {}).get("classification_status", "unmapped"),
                              constraint_text=code)
                       for i, code in enumerate(original, 1)}
        initial_report = cp["initial_verification"]
        final_report = cp["final_verification"]
        initial_plan = initial_report.get("translated_plan")
        final_plan = read_json(bench / "plans" / f"{uid}.json")
        if final_plan != final_report.get("translated_plan"):
            raise ValueError(f"{role}/{uid}: scored final export differs from authoritative trial endpoint")
        si = score_saved(team, uid, reference, initial_plan, manifest["language"], cache, standard_checks)
        sf = score_saved(team, uid, reference, final_plan, manifest["language"], cache, standard_checks)
        stored_pc = [str(logical[uid][f"logic_py_{i}"]).strip() in ("1", "1.0") for i in range(len(original))]
        if sf["pc"] != stored_pc:
            raise ValueError(f"{role}/{uid}: local final PC score disagrees with saved benchmark")
        stored_cs = {c for c, v in cs_file_rows[uid].items()
                     if c not in ("data_id", team.CS_EXCEPTION_COLUMN) and float(v or 0) != 0}
        if not sf["cs_exception"] and set(sf["cs_failed"]) != stored_cs:
            raise ValueError(f"{role}/{uid}: local final CS score disagrees with saved benchmark")
        prefix = dict(strategy=role, query_uid=uid, difficulty=origin[uid])
        for check in standard_checks:
            data["cs_endpoints"].append(dict(**prefix, check=check,
                initially_failed=check in si["cs_failed"], finally_failed=check in sf["cs_failed"],
                initial_scoring_exception=si["cs_exception"], final_scoring_exception=sf["cs_exception"]))
        for i, (bi, bf) in enumerate(zip(si["pc"], sf["pc"]), 1):
            data["constraints"].append(dict(**prefix, constraint_index=i, **descriptors[i],
                initial_passed=bi, final_passed=bf, endpoint_transition=transition(bi, bf),
                scoring_basis="benchmark endpoints"))
        generation = initial["state"].get("generation_metadata", {})
        init_metrics = generation.get("shared_initialization_system_metrics", {})
        current_report, current_score = initial_report, si
        cumulative_tokens = cumulative_time = 0
        local_attempts, regressed_indices = [], set()
        known_regression_history = defaultdict(list)
        cs_ever_broken_pc = set()
        for a in records:
            step = a["step"]
            m = a["repair_metadata"]
            report = hist[step]["verification"]
            before, after = a["before_personal_constraints"], a["after_personal_constraints"]
            if before != current_report["personal_constraints"]:
                raise ValueError(f"{role}/{uid}/{step}: before states do not match accepted history")
            if after != report["personal_constraints"]:
                raise ValueError(f"{role}/{uid}/{step}: candidate states do not match history")
            scored = score_saved(team, uid, reference, report["translated_plan"], manifest["language"], cache, standard_checks)
            target_indices = set(a.get("target_constraint_indices") or [])
            source_families = {descriptors[i]["family"] for i in target_indices}
            eligible_source = next(iter(source_families)) if len(source_families) == 1 and "unmapped" not in source_families else None
            cells = list(guidance_cells(m))
            supports = sum(is_supported(c) for _, c in cells)
            category = guidance_category(supports, len(cells) - supports) if role == "R4" else "not_applicable"
            fixed = [i for i, (b, f) in enumerate(zip(before, after), 1) if b is False and f is True]
            regressed = [i for i, (b, f) in enumerate(zip(before, after), 1) if b is True and f is False]
            if sorted(fixed) != sorted(a.get("fixed", [])) or sorted(regressed) != sorted(a.get("newly_violated", [])):
                raise ValueError(f"{role}/{uid}/{step}: recomputed transitions disagree with saved fixed/newly_violated")
            accepted = a.get("accepted")
            if accepted not in (True, False):
                raise ValueError(f"{role}/{uid}/{step}: missing acceptance")
            kept = after if accepted else before
            cumulative_tokens = cumulative_tokens + a["total_tokens_delta"] if cumulative_tokens is not None and a.get("total_tokens_delta") is not None else None
            cumulative_time = cumulative_time + a["repair_time_seconds"] if cumulative_time is not None and a.get("repair_time_seconds") is not None else None
            for i, (b, candidate, kept_state) in enumerate(zip(before, after, kept), 1):
                kind = transition(b, candidate)
                if accepted and kind == "regressed":
                    regressed_indices.add(i)
                    known_regression_history[i].append(step)
                    if a.get("repair_phase") == "commonsense":
                        cs_ever_broken_pc.add(i)
                data["events"].append(dict(**prefix, step=step, phase=a.get("repair_phase"),
                    constraint_index=i, **descriptors[i], targeted=i in target_indices,
                    matrix_recommended=(m.get("recommended_risk_target") or {}).get("constraint_index") == i,
                    before=b, candidate=candidate, accepted_state=kept_state,
                    candidate_transition=kind, accepted_transition=transition(b, kept_state),
                    accepted=accepted, guidance_category=category,
                    attempt_tokens=a.get("total_tokens_delta"), attempt_repair_time_s=a.get("repair_time_seconds"),
                    cumulative_tokens=cumulative_tokens, cumulative_repair_time_s=cumulative_time,
                    source_artifact=str(cp_path.relative_to(PROJECT_ROOT))))
            known_cs = not (current_score["cs_exception"] or scored["cs_exception"])
            cs_fixed = set(current_score["cs_failed"]) - set(scored["cs_failed"]) if known_cs else None
            cs_new = set(scored["cs_failed"]) - set(current_score["cs_failed"]) if known_cs else None
            if known_cs:
                for check in sorted(set(current_score["cs_failed"]) | set(scored["cs_failed"])):
                    data["cs_events"].append(dict(**prefix, step=step, phase=a.get("repair_phase"),
                        check=check, failed_before=check in current_score["cs_failed"],
                        failed_candidate=check in scored["cs_failed"],
                        outcome="fixed" if check in cs_fixed else "new_failure" if check in cs_new else "still_failed",
                        accepted=accepted, guidance_category=category,
                        scoring_basis="local benchmark rescore of saved translated plans"))
            changed_count = a.get("changed_slot_count")
            changed = changed_count > 0 if isinstance(changed_count, (int, float)) else None
            cache_hit = bool(m.get("llm_cache_hits"))
            if changed is None:
                changed = report.get("translated_plan") != current_report.get("translated_plan")
                change_basis = "saved translated-plan equality; slot count missing"
            else:
                change_basis = "logged changed_slot_count"
            ar = dict(**prefix, step=step, phase=a.get("repair_phase"), accepted=accepted,
                guidance_category=category, supported_relationships=supports,
                unsupported_relationships=len(cells)-supports,
                pc_fixed=len(fixed), pc_regressed=len(regressed), pc_net=len(fixed)-len(regressed),
                accepted_pc_fixed=len(fixed) if accepted else 0,
                accepted_pc_regressed=len(regressed) if accepted else 0,
                pc_failing_opportunities=sum(b is False and f is not None for b, f in zip(before, after)),
                pc_passing_opportunities=sum(b is True and f is not None for b, f in zip(before, after)),
                target_failing_opportunities=sum(before[i-1] is False and after[i-1] is not None for i in target_indices),
                target_fixed=sum(i in target_indices for i in fixed),
                unknown_before=sum(b is None for b in before), unknown_after=sum(f is None for f in after),
                unknown_recovered=sum(b is None and f is not None for b, f in zip(before, after)),
                known_to_unknown=sum(b is not None and f is None for b, f in zip(before, after)),
                cs_fixed=len(cs_fixed) if known_cs else None, cs_new=len(cs_new) if known_cs else None,
                cs_net=len(cs_fixed)-len(cs_new) if known_cs else None,
                cs_before=len(current_score["cs_failed"]), cs_after=len(scored["cs_failed"]),
                cs_scoring_error=not known_cs,
                loop_cs_messages_before=len(current_report.get("commonsense_errors") or []),
                loop_cs_messages_after=len(report.get("commonsense_errors") or []),
                translation_errors_before=len(current_report.get("translation_errors") or []),
                translation_errors_after=len(report.get("translation_errors") or []),
                changed=changed, change_measurement=change_basis, changed_slots=changed_count,
                cache_hit=cache_hit,
                round_outcome="changed" if changed else "unchanged_cache" if cache_hit else "unchanged_other",
                repair_tokens=a.get("total_tokens_delta"), repair_time_s=a.get("repair_time_seconds"),
                attempt_time_s=a.get("attempt_time_seconds"), model_calls=a.get("model_calls"),
                failed_model_calls=a.get("failed_model_calls"), failed_tool_calls=a.get("failed_tool_call_count"),
                verification_count=a.get("verification_count"),
                request_error_reply=a["request_error_reply"], parse_failed=m.get("parse_failed"),
                structural_guard_failure=bool(m.get("proposal_rejected_reason")),
                structural_guard_reason=m.get("proposal_rejected_reason"),
                single_target_family=eligible_source, target_families=sorted(source_families),
                fixed_indices=fixed, regressed_indices=regressed,
                cumulative_tokens=cumulative_tokens, cumulative_repair_time_s=cumulative_time)
            local_attempts.append(ar)
            # Collapse repeated identical source/destination family advice within a prompt.
            edge_map = {(source, c["family"]): c for source, c in cells}
            edge_source = "commonsense_repair" if a.get("repair_phase") == "commonsense" else eligible_source
            edge_keys = set(edge_map)
            if edge_source:
                edge_keys |= {(edge_source, descriptors[i]["family"]) for i, b in enumerate(before, 1)
                              if b is True and descriptors[i]["family"] != edge_source}
            for source, destination in sorted(edge_keys):
                passing = [i for i, b in enumerate(before, 1) if b is True
                           and descriptors[i]["family"] == destination and after[i-1] is not None]
                c = edge_map.get((source, destination))
                if not passing:
                    continue
                data["edges"].append(dict(**prefix, step=step, phase=a.get("repair_phase"),
                    source_family=source, destination_family=destination,
                    single_target_or_commonsense=edge_source == source,
                    logged_edge=c is not None, support_status=("supported" if is_supported(c) else "unsupported") if c else "no_logged_edge",
                    training_support_count=c.get("support_count") if c else None,
                    training_support_query_count=c.get("support_query_count") if c else None,
                    training_regression_probability=c.get("regression_probability") if c else None,
                    evidence_status=c.get("evidence_status") if c else None,
                    passing_destination_constraints=len(passing),
                    regressed=any(i in regressed for i in passing),
                    regressed_indices=[i for i in passing if i in regressed],
                    target_fixed=bool(set(fixed) & target_indices), accepted=accepted))
            if accepted:
                current_report, current_score = report, scored
            data["states"].append(dict(**prefix, step=step, active=True,
                pc_pass_pct=100*sum(current_score["pc"])/len(original),
                cs_failed=len(current_score["cs_failed"]), all_pass=current_score["all_pass"],
                cumulative_tokens=cumulative_tokens, cumulative_repair_time_s=cumulative_time))
        totals = {key: complete_sum(a.get(key) for a in local_attempts)
                  for key in ("repair_tokens", "repair_time_s", "model_calls", "failed_model_calls",
                              "failed_tool_calls", "verification_count")}
        for ours, field in [("repair_tokens", "total_tokens"), ("repair_time_s", "total_repair_time_seconds")]:
            expected = float(summary[uid][field]) if summary[uid].get(field) else None
            actual = totals[ours]
            if expected is None or actual is None or not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-6):
                raise ValueError(f"{role}/{uid}: {ours} disagrees with saved summary")
        selected_initial = role == "R4" and exported.get("selected_source") == "initial"
        query_category = guidance_category(sum(a["supported_relationships"] for a in local_attempts),
                sum(a["unsupported_relationships"] for a in local_attempts)) if role == "R4" else "not_applicable"
        q = dict(**prefix, initial_plan_hash=initial["initial_plan_hash"],
            request=reference.get("nature_language_en") or reference.get("nature_language"),
            pc_total=len(original), pc_initial_passed=sum(si["pc"]), pc_final_passed=sum(sf["pc"]),
            pc_initial_failed=len(original)-sum(si["pc"]), pc_final_failed=len(original)-sum(sf["pc"]),
            pc_initial_pct=100*sum(si["pc"])/len(original), pc_final_pct=100*sum(sf["pc"])/len(original),
            pc_gain_pp=100*(sum(sf["pc"])-sum(si["pc"]))/len(original),
            endpoint_pc_fixed=sum(b is False and f is True for b, f in zip(si["pc"], sf["pc"])),
            endpoint_pc_regressed=sum(b is True and f is False for b, f in zip(si["pc"], sf["pc"])),
            cs_initial_failed=len(si["cs_failed"]), cs_final_failed=len(sf["cs_failed"]),
            cs_reduction=len(si["cs_failed"])-len(sf["cs_failed"]),
            cs_initial_pct=100*(28-len(si["cs_failed"]))/28, cs_final_pct=100*(28-len(sf["cs_failed"]))/28,
            initial_all_pass=si["all_pass"], final_all_pass=sf["all_pass"],
            initial_schema_pass=si["schema"], final_schema_pass=sf["schema"],
            cs_evaluator_exception=si["cs_exception"] or sf["cs_exception"],
            attempts=len(records), personal_attempts=sum(a["phase"] == "personal" for a in local_attempts),
            commonsense_attempts=sum(a["phase"] == "commonsense" for a in local_attempts),
            no_repair_attempts=not records,
            guidance_category=query_category,
            no_guidance_reason=("no_repair_needed" if not records else "all_PC_states_unknown_before_every_attempt"
                if local_attempts and all(a["unknown_before"] == len(original) for a in local_attempts)
                else "other_no_relationship") if query_category == "none" else None,
            loop_fixed_events=sum(a["accepted_pc_fixed"] for a in local_attempts),
            loop_regression_events=sum(a["accepted_pc_regressed"] for a in local_attempts),
            loop_net_events=sum(a["accepted_pc_fixed"]-a["accepted_pc_regressed"] for a in local_attempts),
            constraints_ever_regressed=len(regressed_indices),
            regressions_recovered_final=sum(current_report["personal_constraints"][i-1] is True for i in regressed_indices),
            regressions_still_failed_final=sum(current_report["personal_constraints"][i-1] is False for i in regressed_indices),
            regressions_unknown_final=sum(current_report["personal_constraints"][i-1] is None for i in regressed_indices),
            cs_broke_pc=bool(cs_ever_broken_pc),
            changed_attempts=sum(a["changed"] for a in local_attempts),
            cached_attempts=sum(a["round_outcome"] == "unchanged_cache" for a in local_attempts),
            unchanged_other_attempts=sum(a["round_outcome"] == "unchanged_other" for a in local_attempts),
            structural_guard_attempts=sum(a["structural_guard_failure"] for a in local_attempts),
            parse_failure_attempts=sum(a["parse_failed"] is True for a in local_attempts),
            request_error_replies=sum(a["request_error_reply"] for a in local_attempts),
            translation_error_attempts=sum(a["translation_errors_after"] > 0 for a in local_attempts),
            unknown_before_attempts=sum(a["unknown_before"] > 0 for a in local_attempts),
            loop_initial_unknown=sum(b is None for b in initial_report["personal_constraints"]),
            loop_final_unknown=sum(b is None for b in current_report["personal_constraints"]),
            loop_initial_cs_messages=len(initial_report.get("commonsense_errors") or []),
            loop_final_cs_messages=len(current_report.get("commonsense_errors") or []),
            loop_final_passed=current_report.get("passed"),
            loop_final_pc=[b for b in current_report["personal_constraints"]],
            initial_failed_model_calls=generation.get("failed_model_calls"),
            initial_failed_tool_calls=init_metrics.get("failed_tool_call_count"),
            initial_tokens=generation.get("total_tokens"),
            initial_time_s=generation.get("shared_initialization_time_s"),
            strategy_time_s=cp.get("system_metrics", {}).get("strategy_execution_time_s"),
            execution_status=cp.get("execution_status"), stop_reason=cp.get("stop_reason"),
            exception=cp.get("exception"), selected_initial=selected_initial,
            selected_step=exported.get("selected_step") if role == "R4" else (records[-1]["step"] if records else 0),
            selected_equals_trial_endpoint=exported.get("final_accepted_plan") == cp.get("final_accepted_plan"),
            source_checkpoint=str(cp_path.relative_to(PROJECT_ROOT)), **totals)
        q["end_to_end_tokens"] = complete_sum([q["initial_tokens"], q["repair_tokens"]])
        q["end_to_end_time_s"] = complete_sum([q["initial_time_s"], q["strategy_time_s"]])
        data["queries"].append(q)
        data["attempts"].extend(local_attempts)
        data["states"].append(dict(**prefix, step=0, active=False,
            pc_pass_pct=q["pc_initial_pct"], cs_failed=q["cs_initial_failed"],
            all_pass=q["initial_all_pass"], cumulative_tokens=0, cumulative_repair_time_s=0))
        data["validation"].append(dict(strategy=role, query_uid=uid, status="pass",
            checked="population; endpoint plan identity; final PC/CS versus saved benchmark; history transitions; repair tokens/time versus summary",
            attempts=len(records), scoring_basis="current local benchmark helper; saved loop transitions"))
        data["sources"].append(dict(strategy=role, query_uid=uid, path=str(cp_path.relative_to(PROJECT_ROOT)),
            sha256=hashlib.sha256(cp_path.read_bytes()).hexdigest(),
            initial_plan_hash=q["initial_plan_hash"], benchmark_directory=str(bench.relative_to(PROJECT_ROOT))))
        if ordinal % 10 == 0:
            print(f"{role}: scored and reconciled {ordinal}/{len(ids)} queries", flush=True)
    return data


def summarize_cohort(queries, attempts):
    n = len(queries)
    result = dict(queries=n, initial_pc_pass_pct=avg(q["pc_initial_pct"] for q in queries),
        final_pc_pass_pct=avg(q["pc_final_pct"] for q in queries),
        pc_gain_pp=avg(q["pc_gain_pp"] for q in queries),
        logical_micro_pct=ratio(sum(q["pc_final_passed"] for q in queries), sum(q["pc_total"] for q in queries)),
        logical_macro_pct=ratio(sum(q["pc_final_failed"] == 0 for q in queries), n),
        avg_pc_failed_initial=avg(q["pc_initial_failed"] for q in queries),
        avg_pc_failed_final=avg(q["pc_final_failed"] for q in queries),
        avg_cs_failed_initial=avg(q["cs_initial_failed"] for q in queries),
        avg_cs_failed_final=avg(q["cs_final_failed"] for q in queries),
        cs_micro_pct=avg(q["cs_final_pct"] for q in queries),
        all_cs_pass_pct=ratio(sum(q["cs_final_failed"] == 0 for q in queries), n),
        schema_pass_pct=ratio(sum(q["final_schema_pass"] for q in queries), n),
        all_pass_count=sum(q["final_all_pass"] for q in queries),
        all_pass_pct=ratio(sum(q["final_all_pass"] for q in queries), n),
        pc_improved_queries=sum(q["pc_gain_pp"] > 0 for q in queries),
        pc_unchanged_queries=sum(q["pc_gain_pp"] == 0 for q in queries),
        pc_worsened_queries=sum(q["pc_gain_pp"] < 0 for q in queries),
        cs_improved_queries=sum(q["cs_reduction"] > 0 for q in queries),
        cs_worsened_queries=sum(q["cs_reduction"] < 0 for q in queries),
        cs_unchanged_queries=sum(q["cs_reduction"] == 0 for q in queries),
        final_pc_failed_0=sum(q["pc_final_failed"] == 0 for q in queries),
        final_pc_failed_1=sum(q["pc_final_failed"] == 1 for q in queries),
        final_pc_failed_2plus=sum(q["pc_final_failed"] >= 2 for q in queries),
        final_cs_failed_0=sum(q["cs_final_failed"] == 0 for q in queries),
        final_cs_failed_1=sum(q["cs_final_failed"] == 1 for q in queries),
        final_cs_failed_2plus=sum(q["cs_final_failed"] >= 2 for q in queries),
        avg_attempts=avg(q["attempts"] for q in queries), median_attempts=med(q["attempts"] for q in queries),
        no_repair_queries=sum(q["no_repair_attempts"] for q in queries),
        budget_exhausted_queries=sum(q["stop_reason"] == "repair_budget_exhausted" for q in queries),
        queries_with_regression=sum(q["loop_regression_events"] > 0 for q in queries),
        cs_broke_pc_queries=sum(q["cs_broke_pc"] for q in queries),
        structural_guard_queries=sum(q["structural_guard_attempts"] > 0 for q in queries),
        initial_selected_queries=sum(q["selected_initial"] for q in queries),
        queries_with_unknown_states=sum(q["unknown_before_attempts"] > 0 for q in queries),
        cs_evaluator_exception_queries=sum(q["cs_evaluator_exception"] for q in queries),
        token_complete_queries=sum(q["repair_tokens"] is not None for q in queries))
    for metric in ["repair_tokens", "repair_time_s", "strategy_time_s", "end_to_end_time_s", "end_to_end_tokens"]:
        result["mean_"+metric] = avg(q[metric] for q in queries)
        result["median_"+metric] = med(q[metric] for q in queries)
    for metric in ["loop_fixed_events", "loop_regression_events", "loop_net_events", "constraints_ever_regressed",
                   "regressions_recovered_final", "regressions_still_failed_final",
                   "failed_model_calls", "failed_tool_calls", "initial_failed_model_calls", "initial_failed_tool_calls",
                   "request_error_replies"]:
        result[metric] = complete_sum(q[metric] for q in queries)
    result.update(summarize_attempts(attempts))
    return result


def summarize_attempts(rows):
    count = len(rows)
    failures = sum(a["pc_failing_opportunities"] for a in rows)
    passing = sum(a["pc_passing_opportunities"] for a in rows)
    target_n = sum(a["target_failing_opportunities"] for a in rows)
    return dict(attempts=count, distinct_queries=len({a["query_uid"] for a in rows}),
        personal_rounds=sum(a["phase"] == "personal" for a in rows),
        commonsense_rounds=sum(a["phase"] == "commonsense" for a in rows),
        pc_fixed_events=sum(a["pc_fixed"] for a in rows), pc_regression_events=sum(a["pc_regressed"] for a in rows),
        pc_net_events=sum(a["pc_net"] for a in rows),
        failing_opportunities=failures, passing_opportunities=passing,
        fix_rate_pct=ratio(sum(a["pc_fixed"] for a in rows), failures),
        regression_rate_pct=ratio(sum(a["pc_regressed"] for a in rows), passing),
        target_failing_opportunities=target_n,
        target_fix_rate_pct=ratio(sum(a["target_fixed"] for a in rows), target_n),
        rounds_fixing_any=sum(a["pc_fixed"] > 0 for a in rows),
        rounds_regressing_any=sum(a["pc_regressed"] > 0 for a in rows),
        rounds_fixing_without_regression=sum(a["pc_fixed"] > 0 and a["pc_regressed"] == 0 for a in rows),
        unknown_to_known_events=sum(a["unknown_recovered"] for a in rows),
        known_to_unknown_events=sum(a["known_to_unknown"] for a in rows),
        cs_fixed_events=complete_sum(a["cs_fixed"] for a in rows),
        cs_new_failure_events=complete_sum(a["cs_new"] for a in rows),
        cs_evaluable_attempts=sum(not a["cs_scoring_error"] for a in rows),
        changed_attempts=sum(a["changed"] for a in rows),
        unchanged_cache_attempts=sum(a["round_outcome"] == "unchanged_cache" for a in rows),
        unchanged_other_attempts=sum(a["round_outcome"] == "unchanged_other" for a in rows),
        structural_guard_attempts=sum(a["structural_guard_failure"] for a in rows),
        parse_failure_attempts=sum(a["parse_failed"] is True for a in rows),
        mean_tokens_per_attempt=avg(a["repair_tokens"] for a in rows),
        median_tokens_per_attempt=med(a["repair_tokens"] for a in rows),
        mean_repair_time_per_attempt_s=avg(a["repair_time_s"] for a in rows),
        mean_changed_slots=avg(a["changed_slots"] for a in rows))


def grouped_overview(data):
    result = []
    for label, group in GROUPS.items():
        qs = [q for q in data["queries"] if group is None or q["difficulty"] == group]
        ids = {q["query_uid"] for q in qs}
        result.append(dict(strategy=data["role"], group=label,
            **summarize_cohort(qs, [a for a in data["attempts"] if a["query_uid"] in ids])))
    return result


def constraint_summary(data, group="All"):
    rows = []
    for dimension in ("family", "kind"):
        for name in sorted({c[dimension] for c in data["constraints"]}):
            end = [c for c in data["constraints"] if c[dimension] == name]
            ev = [e for e in data["events"] if e[dimension] == name]
            fail_n = sum(e["before"] is False and e["candidate"] is not None for e in ev)
            pass_n = sum(e["before"] is True and e["candidate"] is not None for e in ev)
            fixes = [e for e in ev if e["candidate_transition"] == "fixed"]
            regressions = [e for e in ev if e["candidate_transition"] == "regressed"]
            targeted = [e for e in ev if e["targeted"] and e["before"] is False and e["candidate"] is not None]
            rows.append(dict(strategy=data["role"], group=group, dimension=dimension, constraint_type=name,
                query_count=len({c["query_uid"] for c in end}), constraint_instances=len(end),
                initial_failed=sum(not c["initial_passed"] for c in end),
                final_failed=sum(not c["final_passed"] for c in end),
                final_failure_rate_pct=ratio(sum(not c["final_passed"] for c in end), len(end)),
                endpoint_fixed=sum(c["endpoint_transition"] == "fixed" for c in end),
                endpoint_regressed=sum(c["endpoint_transition"] == "regressed" for c in end),
                fix_events=len(fixes), distinct_constraints_ever_fixed=len({(e["query_uid"],e["constraint_index"]) for e in fixes}),
                queries_with_fix=len({e["query_uid"] for e in fixes}), failing_opportunities=fail_n,
                fix_rate_pct=ratio(len(fixes), fail_n), regression_events=len(regressions),
                distinct_constraints_ever_regressed=len({(e["query_uid"],e["constraint_index"]) for e in regressions}),
                queries_with_regression=len({e["query_uid"] for e in regressions}), passing_opportunities=pass_n,
                regression_rate_pct=ratio(len(regressions), pass_n),
                targeted_opportunities=len(targeted), target_fix_rate_pct=ratio(sum(e["candidate"] is True for e in targeted), len(targeted)),
                unknown_before_events=sum(e["before"] is None for e in ev),
                unknown_to_known_events=sum(e["before"] is None and e["candidate"] is not None for e in ev),
                known_to_unknown_events=sum(e["candidate_transition"] == "known_to_unknown" for e in ev)))
    if group == "All":
        for label, difficulty in GROUPS.items():
            if difficulty is None:
                continue
            subset={**data,"constraints":[c for c in data["constraints"] if c["difficulty"]==difficulty],
                    "events":[e for e in data["events"] if e["difficulty"]==difficulty]}
            rows.extend(constraint_summary(subset,label))
    return rows


def cs_summary(data):
    rows = []
    all_checks = sorted({e["check"] for e in data["cs_endpoints"]})
    known_rounds = sum(not a["cs_scoring_error"] for a in data["attempts"])
    for check in all_checks:
        events = [e for e in data["cs_events"] if e["check"] == check]
        endpoints = [e for e in data["cs_endpoints"] if e["check"] == check]
        fixed = sum(e["outcome"] == "fixed" for e in events)
        new = sum(e["outcome"] == "new_failure" for e in events)
        fail_n = sum(e["failed_before"] for e in events)
        pass_n = known_rounds-fail_n
        rows.append(dict(strategy=data["role"], check=check,
            initial_failed_queries=sum(e["initially_failed"] for e in endpoints),
            final_failed_queries=sum(e["finally_failed"] for e in endpoints),
            final_failure_rate_pct=ratio(sum(e["finally_failed"] for e in endpoints), len(endpoints)),
            endpoint_fixed=sum(e["initially_failed"] and not e["finally_failed"] for e in endpoints),
            endpoint_new_failure=sum(not e["initially_failed"] and e["finally_failed"] for e in endpoints),
            fixed_events=fixed, new_failure_events=new,
            failing_opportunities=fail_n, passing_opportunities=pass_n,
            fix_rate_pct=ratio(fixed,fail_n), new_failure_rate_pct=ratio(new,pass_n),
            queries_with_fix=len({e["query_uid"] for e in events if e["outcome"] == "fixed"}),
            queries_with_new_failure=len({e["query_uid"] for e in events if e["outcome"] == "new_failure"})))
    return rows


def round_summary(data):
    rows = []
    for step in range(int(data["manifest"].get("max_steps", 6))+1):
        kept = []
        active = []
        for q in data["queries"]:
            states = [s for s in data["states"] if s["query_uid"] == q["query_uid"] and s["step"] <= step]
            if not states:
                continue
            latest = max(states, key=lambda s: s["step"])
            kept.append(latest)
            if step and any(a["query_uid"] == q["query_uid"] and a["step"] == step for a in data["attempts"]):
                active.append(latest)
        rows.append(dict(strategy=data["role"], step=step, cohort_queries=len(kept),
            active_queries=len(active), cohort_pc_pass_pct=avg(s["pc_pass_pct"] for s in kept),
            cohort_cs_failed=avg(s["cs_failed"] for s in kept),
            active_pc_pass_pct=avg(s["pc_pass_pct"] for s in active),
            active_cs_failed=avg(s["cs_failed"] for s in active),
            cohort_all_pass=sum(s["all_pass"] for s in kept),
            mean_cumulative_tokens=avg(s["cumulative_tokens"] for s in kept),
            cohort_policy="carry last accepted state forward after stopping; local benchmark scoring"))
    return rows


def edge_summary(data):
    grouped = defaultdict(list)
    for e in data["edges"]:
        grouped[(e["source_family"],e["destination_family"],e["support_status"],e["single_target_or_commonsense"])].append(e)
    return [dict(strategy=data["role"], source_family=key[0], destination_family=key[1],
                 support_status=key[2], single_target_or_commonsense=key[3],
                 family_opportunities=len(es), distinct_queries=len({e["query_uid"] for e in es}),
                 regression_attempts=sum(e["regressed"] for e in es),
                 observed_regression_rate_pct=ratio(sum(e["regressed"] for e in es), len(es)),
                 training_support_count=es[0]["training_support_count"],
                 training_support_query_count=es[0]["training_support_query_count"])
            for key, es in sorted(grouped.items())]


def export_run(data, folder, selected_uids=None):
    export_csv(folder/"overview.csv", grouped_overview(data))
    export_csv(folder/"per_query.csv", data["queries"])
    export_csv(folder/"attempts.csv", data["attempts"])
    export_csv(folder/"constraints.csv", data["constraints"])
    export_csv(folder/"constraint_types.csv", constraint_summary(data))
    trace = [e for e in data["events"] if not selected_uids or e["query_uid"] in selected_uids]
    export_csv(folder/"query_trace.csv", trace)
    export_csv(folder/"commonsense_checks.csv", cs_summary(data))
    export_csv(folder/"commonsense_endpoints.csv", data["cs_endpoints"])
    export_csv(folder/"commonsense_events.csv", data["cs_events"])
    export_csv(folder/"by_round.csv", round_summary(data))
    export_csv(folder/"by_phase.csv", [dict(strategy=data["role"], phase=p,
        **summarize_attempts([a for a in data["attempts"] if a["phase"] == p])) for p in ("personal","commonsense")])
    export_csv(folder/"edge_outcomes.csv", data["edges"])
    export_csv(folder/"edge_summary.csv", edge_summary(data))
    export_csv(folder/"validation.csv", data["validation"])
    export_csv(folder/"failure_diagnostics.csv", [q for q in data["queries"] if
        q["failed_model_calls"] or q["initial_failed_model_calls"] or q["failed_tool_calls"]
        or q["initial_failed_tool_calls"] or q["structural_guard_attempts"]
        or q["parse_failure_attempts"] or q["unknown_before_attempts"]])


def comparison_tables(left, right, folder):
    lq = {q["query_uid"]:q for q in left["queries"]}
    rq = {q["query_uid"]:q for q in right["queries"]}
    if set(lq) != set(rq):
        raise ValueError("R0/R4 query populations differ; refusing a silent intersection")
    paired = []
    metrics = ["pc_initial_pct","pc_final_pct","pc_gain_pp","pc_final_failed","cs_initial_failed",
               "cs_final_failed","cs_reduction","final_all_pass","repair_tokens","repair_time_s",
               "strategy_time_s","end_to_end_time_s","attempts","loop_fixed_events","loop_regression_events"]
    for uid in sorted(lq):
        a,b = lq[uid],rq[uid]
        if a["difficulty"] != b["difficulty"] or left["references"][uid]["hard_logic_py"] != right["references"][uid]["hard_logic_py"]:
            raise ValueError(f"{uid}: R0/R4 query definition/difficulty mismatch")
        row = dict(query_uid=uid, difficulty=a["difficulty"],
            same_initial_plan=a["initial_plan_hash"] == b["initial_plan_hash"])
        for key in metrics:
            row["R0_"+key], row["R4_"+key] = a[key], b[key]
            row["delta_"+key] = b[key]-a[key] if a[key] is not None and b[key] is not None else None
        paired.append(row)
    summary = []
    lower_is_better = {"pc_final_failed","cs_initial_failed","cs_final_failed","repair_tokens",
                      "repair_time_s","strategy_time_s","end_to_end_time_s","attempts","loop_regression_events"}
    for group, difficulty in GROUPS.items():
        cohort = [p for p in paired if difficulty is None or p["difficulty"] == difficulty]
        for metric in metrics:
            valid = [p for p in cohort if p["delta_"+metric] is not None]
            direction = -1 if metric in lower_is_better else 1
            summary.append(dict(group=group, metric=metric, paired_queries=len(valid),
                R0_mean=avg(p["R0_"+metric] for p in valid), R4_mean=avg(p["R4_"+metric] for p in valid),
                mean_delta_R4_minus_R0=avg(p["delta_"+metric] for p in valid),
                median_delta_R4_minus_R0=med(p["delta_"+metric] for p in valid),
                R4_higher_count=sum(p["delta_"+metric] > 0 for p in valid),
                tied_count=sum(p["delta_"+metric] == 0 for p in valid),
                R4_lower_count=sum(p["delta_"+metric] < 0 for p in valid),
                R4_better_count=sum(direction*p["delta_"+metric] > 0 for p in valid)
                    if metric not in ("pc_initial_pct","cs_initial_failed","attempts","loop_fixed_events") else None,
                direction="descriptive" if metric in ("pc_initial_pct","cs_initial_failed","attempts","loop_fixed_events")
                    else "lower" if metric in lower_is_better else "higher"))
    checks = [dict(check="query_population",status="pass",detail=f"{len(paired)} common queries; no exclusions"),
              dict(check="identical_initial_plan",status="descriptive limitation",
                   detail=f"{sum(p['same_initial_plan'] for p in paired)}/{len(paired)} matching initial plan hashes")]
    for key in ["model_identifier","max_steps","language","oracle_translation","seed","sampling_settings","implementation_hash"]:
        a,b=left["manifest"].get(key),right["manifest"].get(key)
        checks.append(dict(check=key,status="same" if a==b and a is not None else "unknown" if a is None or b is None else "different",
                           R0=a,R4=b))
    checks.append(dict(check="interpretation",status="descriptive",detail="R0/R4 differ in prompts, parsing/structural guards and initial plans; this is not an isolated matrix ablation."))
    export_csv(folder/"paired_queries.csv", paired)
    export_csv(folder/"comparison_summary.csv", summary)
    export_csv(folder/"compatibility.csv", checks)
    export_csv(folder/"constraint_types.csv", constraint_summary(left)+constraint_summary(right))
    export_run(left,folder/"r0_details")
    return paired,summary


def guidance_tables(data, folder):
    query_groups=[]
    for category in GUIDANCE_CATEGORIES:
        for group,difficulty in GROUPS.items():
            qs=[q for q in data["queries"] if q["guidance_category"]==category
                and (difficulty is None or q["difficulty"]==difficulty)]
            ids={q["query_uid"] for q in qs}
            query_groups.append(dict(category=category,group=group,
                **summarize_cohort(qs,[a for a in data["attempts"] if a["query_uid"] in ids])))
    attempt_groups=[]
    for category in GUIDANCE_CATEGORIES:
        for phase in ("personal","commonsense","All"):
            for group,difficulty in GROUPS.items():
                rows=[a for a in data["attempts"] if a["guidance_category"]==category
                      and (phase=="All" or a["phase"]==phase)
                      and (difficulty is None or a["difficulty"]==difficulty)]
                attempt_groups.append(dict(category=category,phase=phase,group=group,**summarize_attempts(rows)))
    export_csv(folder/"query_groups.csv",query_groups)
    export_csv(folder/"attempt_groups.csv",attempt_groups)
    export_csv(folder/"query_membership.csv",data["queries"])
    export_csv(folder/"attempt_membership.csv",data["attempts"])
    export_csv(folder/"edge_outcomes.csv",data["edges"])
    export_csv(folder/"edge_summary.csv",edge_summary(data))
    export_csv(folder/"no_relationship_queries.csv",[q for q in data["queries"] if q["guidance_category"]=="none"])
    matrix_paths = sorted((data["root"]/"inputs").glob("*/main_matrix.csv"))
    coverage=[]
    for path in matrix_paths:
        with path.open(encoding="utf-8-sig",newline="") as f:
            cells=list(csv.DictReader(f))
        for label,predicate in [
                ("PC to PC off-diagonal",lambda c:c["source_family"]!="commonsense_repair" and c["destination_family"]!="commonsense_repair" and c["source_family"]!=c["destination_family"]),
                ("CS repair to PC",lambda c:c["source_family"]=="commonsense_repair" and c["destination_family"]!="commonsense_repair"),
                ("PC repair to CS",lambda c:c["source_family"]!="commonsense_repair" and c["destination_family"]=="commonsense_repair")]:
            part=[c for c in cells if predicate(c)]
            observed=sum(float(c["support_count"] or 0)>0 for c in part)
            coverage.append(dict(matrix=str(path.relative_to(data["root"])),scope=label,
                possible_pairs=len(part),observed_pairs=observed,
                observed_pair_pct=ratio(observed,len(part)),
                pairs_with_observed_regression=sum(float(c["regression_count"] or 0)>0 for c in part)))
    export_csv(folder/"matrix_coverage.csv",coverage)
    return query_groups,attempt_groups


def fmt(value, digits=2):
    if value is None:
        return "NA"
    if isinstance(value,bool):
        return "Yes" if value else "No"
    if isinstance(value,(float,int)):
        return f"{value:,.{digits}f}" if isinstance(value,float) else f"{value:,}"
    return str(value).replace("|","/").replace("\n"," ")


def md_table(rows,columns):
    return "\n".join(["| "+" | ".join(label for key,label in columns)+" |",
                      "|"+"|".join("---" for _ in columns)+"|"]+
                     ["| "+" | ".join(fmt(row.get(key)) for key,label in columns)+" |" for row in rows])


def rate_display(count, denominator):
    return f"{count}/{denominator} ({fmt(ratio(count,denominator))}%)" if denominator else "NA (0 opportunities)"


def bar_chart(path, title, labels, series, unit="", note=""):
    """Dependency-free SVG export for the explicitly requested Markdown report."""
    width,left,right,top,row_height=1050,320,125,95,56
    height=top+len(labels)*row_height+90
    max_value=max([v for _,_,values in series for v in values if v is not None]+[1])
    tick_count=4
    if "percentage" in unit.lower():
        max_value=100
    elif all(isinstance(v,int) for _,_,values in series for v in values if v is not None) and max_value<=8:
        max_value=math.ceil(max_value)
        tick_count=max_value
    else:
        magnitude=10**math.floor(math.log10(max_value/4))
        tick_step=math.ceil(max_value/4/magnitude)*magnitude
        max_value=tick_step*4
    span=width-left-right
    texts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<g font-family="Arial, sans-serif" font-size="17" fill="#202b35">',
           f'<text x="26" y="31" font-size="23" font-weight="bold">{escape(title)}</text>']
    for tick in range(tick_count+1):
        x=left+span*tick/tick_count
        texts += [f'<line x1="{x}" y1="{top-10}" x2="{x}" y2="{height-65}" stroke="#dce2e6"/>',
                  f'<text x="{x}" y="{height-43}" text-anchor="middle" font-size="14">{max_value*tick/tick_count:,.0f}</text>']
    for j,(name,color,values) in enumerate(series):
        texts += [f'<rect x="{left+j*175}" y="47" width="15" height="15" fill="{color}"/>',
                  f'<text x="{left+23+j*175}" y="61" font-size="15">{escape(name)}</text>']
        bar_h=min(20,36/len(series))
        for i,(label,value) in enumerate(zip(labels,values)):
            y=top+i*row_height+j*(bar_h+3)
            if j==0:
                texts.append(f'<text x="{left-15}" y="{y+18}" text-anchor="end">{escape(label)}</text>')
            if value is not None:
                w=span*value/max_value
                texts += [f'<rect x="{left}" y="{y}" width="{w}" height="{bar_h}" fill="{color}"/>',
                          f'<text x="{left+w+7}" y="{y+bar_h-2}" font-size="14">{fmt(value)}</text>']
    texts += [f'<text x="{left}" y="{height-15}" font-size="14">{escape(unit+"  "+note)}</text>',"</g></svg>"]
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text("\n".join(texts),encoding="utf8")


def write_report(output,datasets,paired,query_groups,attempt_groups,selected_uids):
    r4=datasets["R4"]
    overview=grouped_overview(r4)
    total=next(r for r in overview if r["group"]=="All")
    b=chr(96)
    title="R4 improves several TEST outcomes, with higher token use and limited matrix coverage" if "R0" in datasets else "R4 TEST outcomes, repair behaviour and costs"
    lines=["# "+title,
           "","> Descriptive analysis of retained TEST executions. No significance tests or causal estimates.", "",
           "## What the results support",""]
    if "R0" in datasets:
        other=next(r for r in grouped_overview(datasets["R0"]) if r["group"]=="All")
        lines += [f"- R4 finishes at **{total['final_pc_pass_pct']:.2f}% mean per-query PC satisfaction**, versus **{other['final_pc_pass_pct']:.2f}%** for R0. Initial values are {total['initial_pc_pass_pct']:.2f}% and {other['initial_pc_pass_pct']:.2f}%, respectively.",
            f"- Average final failed CS categories fall from **{other['avg_cs_failed_final']:.2f} to {total['avg_cs_failed_final']:.2f}**. All-pass rises from **{other['all_pass_count']}/{other['queries']} to {total['all_pass_count']}/{total['queries']}**.",
            f"- R4 uses **{100*(total['mean_repair_tokens']/other['mean_repair_tokens']-1):.1f}% more repair tokens**. Its repair generation time is {total['mean_repair_time_s']:.2f}s versus {other['mean_repair_time_s']:.2f}s, but strategy elapsed time including verification/overhead is {total['mean_strategy_time_s']:.2f}s versus {other['mean_strategy_time_s']:.2f}s.",
            f"- The same {len(paired)} requests were evaluated, but **{sum(p['same_initial_plan'] for p in paired)}/{len(paired)} initial plans match**. Differences describe these recorded strategy runs, not the causal contribution of matrix guidance.",""]
    else:
        lines += [f"- R4 finishes at {total['final_pc_pass_pct']:.2f}% mean per-query PC satisfaction and {total['avg_cs_failed_final']:.2f} failed CS categories/query.",
                  f"- {total['all_pass_count']}/{total['queries']} plans pass schema, all PCs and all CS checks.",""]
    lines += ["## R4 results by difficulty","",
        md_table(overview,[("group","Group"),("queries","N"),("initial_pc_pass_pct","Initial PC %"),
            ("final_pc_pass_pct","Final PC %"),("pc_gain_pp","Gain pp"),("avg_cs_failed_final","Final CS fails"),
            ("all_pass_count","All-pass"),("mean_repair_tokens","Repair tokens/query"),("mean_repair_time_s","Repair s/query")]),"",
        f"Across the recorded repair loop, there are **{total['loop_fixed_events']} confirmed PC fix events** and **{total['loop_regression_events']} regression events**. These can involve repeated changes to the same constraint. "
        f"**{total['queries_with_regression']} queries** experience at least one regression, while **{total['pc_worsened_queries']}** finish with lower benchmark PC satisfaction. These are different measures.",
        f"Of {total['constraints_ever_regressed']} distinct query-constraint instances ever broken, {total['regressions_recovered_final']} pass at the loop endpoint and {total['regressions_still_failed_final']} remain failed. "
        f"Commonsense edits break a PC on {total['cs_broke_pc_queries']} queries.","",
        "Detailed results: [overview](r4/overview.csv), [per query](r4/per_query.csv), [rounds](r4/by_round.csv), [phases](r4/by_phase.csv).",""]
    successes=[q for q in r4["queries"] if q["final_all_pass"]]
    lines += ["### Which queries actually pass every benchmark check?","",
        md_table(successes,[("query_uid","Query"),("difficulty","Group"),("pc_total","PCs all passed"),
            ("cs_initial_failed","Initial CS fails"),("cs_final_failed","Final CS fails"),
            ("attempts","Attempts"),("repair_tokens","Repair tokens"),("loop_final_passed","Loop also passed?")]),"",
        "These are the benchmark all-pass cases. A loop pass and a benchmark all-pass are different outcomes; both flags are retained. "
        "For a clean final-success demo, use e20241028161037866126: both evaluations pass after one repair. "
        "Use the hot-pot query below to demonstrate budget/commonsense interactions, while stating its remaining benchmark CS failures.",""]
    families=sorted([r for r in constraint_summary(r4) if r["dimension"]=="kind" and r["group"]=="All"],key=lambda r:(-r["final_failed"],r["constraint_type"]))
    family_display=[dict(r,final_failure=rate_display(r["final_failed"],r["constraint_instances"]),
        fix_display=rate_display(r["fix_events"],r["failing_opportunities"]),
        regression_display=rate_display(r["regression_events"],r["passing_opportunities"]))
        for r in families]
    lines += ["## Which constraints are difficult or fragile?","",
        md_table(family_display,[("constraint_type","Constraint kind"),("query_count","Queries"),
            ("final_failure","Final failed / instances"),("fix_display","Fixes / failing opportunities"),
            ("regression_display","Regressions / passing opportunities")]),"",
        "Final failures above use consistent benchmark scoring; loop events use the verifier states the repair actually saw. "
        "A named-place constraint can therefore fail throughout the loop yet pass the endpoint benchmark after name normalization. "
        "Unknown-to-known transitions are listed separately and are not counted as confirmed fixes.",""]
    family_counts=sorted([r for r in constraint_summary(r4) if r["dimension"]=="family" and r["group"]=="All"],
                         key=lambda r:-r["final_failed"])
    bar_chart(output/"figures/constraint_failures.svg","Final benchmark failures by matrix family",
              [r["constraint_type"].replace("_"," ") for r in family_counts],
              [("Failed constraints","#2b5c8a",[r["final_failed"] for r in family_counts])],
              "Constraint instances; see the type table for applicability denominators.")
    lines += ["![Final constraint failures by matrix family](figures/constraint_failures.svg)","",
              "Unmapped constraints remain visible; they are not assigned a family by guesswork. "
              "The food-cost-per-person constraint is classified by the detailed kind helper but is unmapped by the matrix's structural family classifier.",""]
    if families and families[0]["final_failed"]:
        top=families[0]
        lines += [f"The largest remaining failure count is **{top['constraint_type']}**, with **{top['final_failed']}/{top['constraint_instances']}** applicable constraints failed. "
                  "Use both counts and denominators: a 1/1 failure is not evidence that a family is generally harder than one observed on many requests.",""]
    lines += ["The [constraint-type table](r4/constraint_types.csv) also contains matrix families, target-fix rates, unique affected constraints, and unknown-state counts. "
              "The [CS-check table](r4/commonsense_checks.csv) ranks the 28 categories and records their round-level fixes/new failures.",""]
    for name in ["Rooms / room type","Total budget","Food cost per person"]:
        row=next((r for r in families if r["constraint_type"]==name),None)
        if row:
            lines += [f"- **{name}:** {row['fix_events']} loop fix events and {row['regression_events']} regressions across {row['query_count']} applicable queries. "
                + ("These events all concern one query, so the 100% fix rate does not establish broad reliability." if row["query_count"]==1
                   else "The combination of fixes and regressions is more informative than final failure count alone.")]
    lines += ["","### Commonsense failures and repair progress",""]
    cs_types=sorted(cs_summary(r4),key=lambda r:-r["final_failed_queries"])
    lines += [md_table(cs_types[:6],[("check","CS category"),("initial_failed_queries","Initially failed"),
        ("final_failed_queries","Finally failed"),("fixed_events","Round fixes"),("new_failure_events","New failures")]),"",
        f"Personal rounds account for {sum(a['cs_fixed'] or 0 for a in r4['attempts'] if a['phase']=='personal')} CS category fixes and "
        f"{sum(a['cs_new'] or 0 for a in r4['attempts'] if a['phase']=='personal')} new CS failures. Commonsense rounds account for "
        f"{sum(a['cs_fixed'] or 0 for a in r4['attempts'] if a['phase']=='commonsense')} fixes and "
        f"{sum(a['cs_new'] or 0 for a in r4['attempts'] if a['phase']=='commonsense')} new failures. "
        "These are repeated check transitions, not counts of independent queries.","",
        "## Cost and execution diagnostics","",
        f"R4's mean repair-token cost is {total['mean_repair_tokens']:,.0f}, versus a median of {total['median_repair_tokens']:,.0f}; "
        "the mean is affected by the expensive tail. All 30 queries have complete repair-token totals, including the zero-repair query.","",
        md_table(sorted(r4["queries"],key=lambda q:q["repair_tokens"],reverse=True)[:5],
            [("query_uid","Highest-token queries"),("difficulty","Group"),("repair_tokens","Tokens"),
             ("repair_time_s","Repair s"),("pc_final_passed","Final PCs passed"),("pc_total","PCs total"),
             ("cs_final_failed","Final CS fails")]),"",
        f"There are {total['changed_attempts']} changed proposals, {total['unchanged_cache_attempts']} cached unchanged proposals, "
        f"and {total['unchanged_other_attempts']} other unchanged proposals, out of {total['attempts']} attempts. "
        f"{total['budget_exhausted_queries']}/{total['queries']} queries exhaust the repair budget.","",
        f"Recorded model request failures: initialization {total['initial_failed_model_calls']}, repair {total['failed_model_calls']}; "
        f"error replies: {total['request_error_replies']}. Recorded failed tool calls: initialization {total['initial_failed_tool_calls']}, repair {total['failed_tool_calls']}. "
        f"Structural guards fire on {total['structural_guard_attempts']} attempts from {total['structural_guard_queries']} query. "
        "Tool counts include repeated and nested verification calls; they do not count distinct underlying issues. "
        "See [failure diagnostics](r4/failure_diagnostics.csv) for affected query IDs.",""]
    if "R0" in datasets:
        left=next(r for r in grouped_overview(datasets["R0"]) if r["group"]=="All")
        comp=[dict(metric=label,R0=left[key],R4=total[key],delta=total[key]-left[key])
              for key,label in [("final_pc_pass_pct","Mean per-query PC pass %"),("logical_micro_pct","Pooled logical micro %"),
                  ("logical_macro_pct","All-PC-pass %"),("avg_pc_failed_final","Final PC fails/query"),
                  ("avg_cs_failed_final","Final CS fails/query"),("all_pass_pct","All-pass %"),
                  ("mean_repair_tokens","Repair tokens/query"),("median_repair_tokens","Median repair tokens/query"),
                  ("mean_repair_time_s","Repair generation s/query"),("mean_strategy_time_s","Strategy elapsed s/query"),
                  ("mean_end_to_end_time_s","Initialization + strategy s/query")]]
        lines += ["## R0 versus R4: quality and cost","",
            md_table(comp,[("metric","Metric"),("R0","R0"),("R4","R4"),("delta","R4 minus R0")]),"",
            "![Initial and final PC satisfaction](figures/pc_comparison.svg)","",
            "![Repair tokens](figures/cost_comparison.svg)","",
            "![Strategy execution time](figures/timing_comparison.svg)","",
            "The distinction between repair generation time and full strategy elapsed time changes the runtime comparison. "
            "Neither number should be labelled simply 'runtime' without its scope. End-to-end values additionally include separately generated initial plans.","",
            md_table([dict(metric=label,better=sum(sign*p['delta_'+key]>0 for p in paired),tied=sum(p['delta_'+key]==0 for p in paired),
                worse=sum(sign*p['delta_'+key]<0 for p in paired)) for key,label,sign in
                [("pc_final_pct","Final PC satisfaction",1),("pc_gain_pp","PC repair gain",1),
                 ("cs_final_failed","Final CS failures",-1),("repair_tokens","Repair tokens",-1)]],
                [("metric","Per-query comparison"),("better","R4 better"),("tied","Tied"),("worse","R4 worse")]),"",
            "Use [paired queries](r0_vs_r4/paired_queries.csv) for exact per-query differences, "
            "[comparison summary](r0_vs_r4/comparison_summary.csv) for all difficulty groups, and "
            "[compatibility](r0_vs_r4/compatibility.csv) for recorded control differences.","",
            f"The final PC gap is {total['final_pc_pass_pct']-left['final_pc_pass_pct']:.2f} pp. "
            f"Arithmetically, {total['initial_pc_pass_pct']-left['initial_pc_pass_pct']:.2f} pp was already present before repair, "
            f"and {total['pc_gain_pp']-left['pc_gain_pp']:.2f} pp is the difference in repair gains. "
            "This is a decomposition of the observed gap, not a causal allocation.",""]
        bar_chart(output/"figures/pc_comparison.svg","PC satisfaction before and after repair",
            ["Initial","Final"],[("R0","#2b5c8a",[left["initial_pc_pass_pct"],left["final_pc_pass_pct"]]),
                                  ("R4","#c08018",[total["initial_pc_pass_pct"],total["final_pc_pass_pct"]])],
            "Mean per-query PC pass percentage; 30 requests/strategy.")
        # Each metric has its own panel in the file to avoid mixing units on one axis.
        for name,key,label in [("cost_comparison","mean_repair_tokens","Repair tokens per query"),
                               ("timing_comparison","mean_strategy_time_s","Strategy elapsed seconds per query")]:
            bar_chart(output/f"figures/{name}.svg",label,["R0","R4"],
                [("Mean","#2b5c8a",[left[key],total[key]])],
                "Tokens; initialization excluded." if "tokens" in key else "Seconds; initialization excluded.")
    if query_groups:
        cohorts=[r for r in query_groups if r["group"]=="All"]
        lines += ["## Supported and unsupported guidance are not separate treatments","",
            md_table([dict(r,category=GUIDANCE_CATEGORIES[r["category"]]) for r in cohorts],[("category","Query category"),("queries","N"),("initial_pc_pass_pct","Initial PC %"),
                ("final_pc_pass_pct","Final PC %"),("pc_gain_pp","Gain pp"),("avg_cs_failed_final","Final CS fails"),
                ("avg_attempts","Attempts/query"),("mean_repair_tokens","Tokens/query"),
                ("queries_with_regression","Queries with regression")]),"",
            "![Guidance categories](figures/guidance_coverage.svg)","",
            "Unsupported-only has no queries. The meaningful available query comparison is supported-only versus mixed. "
            "The groups have different requests and starting conditions, and longer trajectories have more chances to encounter unsupported advice. "
            "An overall group difference cannot be attributed to unsupported guidance.","",
            md_table([dict(r,category=GUIDANCE_CATEGORIES[r["category"]],
                fix_display=rate_display(r["pc_fixed_events"],r["failing_opportunities"]),
                regression_display=rate_display(r["pc_regression_events"],r["passing_opportunities"]))
                for r in attempt_groups if r["phase"]!="All" and r["group"]=="All" and r["attempts"]],
                [("category","Attempt category"),("phase","Phase"),("attempts","Attempts"),("distinct_queries","Queries"),
                 ("fix_display","Fixes / failing opp."),("regression_display","Regressions / passing opp.")]),"",
            "All five unsupported-only attempts belong to one query. Supported-only attempts are concentrated in the commonsense phase, "
            "so compare phases separately. Attempts from the same query are repeated observations, not independent samples.","",
            "An observed zero risk with positive support is supported evidence. A neutral fallback of 0.5 is not an observed 50% regression rate. "
            "The [edge evidence](guidance/edge_outcomes.csv) identifies whether the specific source-to-victim family edge was supported, "
            "and flags single-target-family/commonsense opportunities separately from multi-target advice.",""]
        supported=next(r for r in cohorts if r["category"]=="supported_only")
        mixed=next(r for r in cohorts if r["category"]=="both")
        lines += [f"Supported-only queries start at {fmt(supported['initial_pc_pass_pct'])}% PC satisfaction; mixed queries start at "
            f"{fmt(mixed['initial_pc_pass_pct'])}%. Mixed queries have a larger mean gain ({fmt(mixed['pc_gain_pp'])} pp versus "
            f"{fmt(supported['pc_gain_pp'])} pp), despite a lower final score. This baseline imbalance is central to interpretation.","",
            "The [matrix coverage table](guidance/matrix_coverage.csv) reports observed versus possible family pairs in the exact runtime matrix. "
            "For the current pooled matrix, 21 of 72 off-diagonal PC-to-PC pairs have observed support; lack of evidence is distinct from an observed zero regression rate.",""]
        bar_chart(output/"figures/guidance_coverage.svg","R4 guidance received across each full query",
            [GUIDANCE_CATEGORIES[r["category"]] for r in cohorts],
            [("Queries","#2b5c8a",[r["queries"] for r in cohorts])],
            "Unique queries; mutually exclusive; total N=30.")
        none=[q for q in r4["queries"] if q["guidance_category"]=="none"]
        lines += ["### Why three queries have no logged relationship","",
            md_table(none,[("query_uid","Query"),("no_guidance_reason","Reason"),("attempts","Attempts"),
                ("initial_failed_model_calls","Initial request failures"),("failed_model_calls","Repair request failures"),
                ("initial_failed_tool_calls","Initial tool failures"),("failed_tool_calls","Repair tool failures")]),"",
            "One initial plan already passed. The two other queries had transport-translation failures and all PCs unknown before every attempt; "
            "R4 had neither known failing PCs to rank nor known passing PCs to protect with family advice. "
            "Their constraints became evaluable only after the final commonsense edit. The matrix was loaded, but no relationships were emitted.",""]
    lines += ["## Query traces and demo recommendations","",
        "The [trace CSV](r4/query_trace.csv) is one constraint per step, including before/candidate/accepted states, "
        "target flags, matrix recommendation, guidance category, event type, tokens, cumulative cost and source checkpoint. "
        "The [CS event CSV](r4/commonsense_events.csv) uses the standard benchmark categories, not text-message matching.",""]
    for uid,label in [("h20241029143652031792","Budget-repair success, with a transient regression"),
                      ("e20241028161334777418","An unsupported attraction-to-accommodation edge"),
                      ("h20241029143921648851","All five unsupported-only personal attempts come from this query")]:
        q=next((q for q in r4["queries"] if q["query_uid"]==uid),None)
        if not q:
            continue
        rows=[a for a in r4["attempts"] if a["query_uid"]==uid]
        lines += [f"### {label}: {uid}","",q["request"],"",
            md_table(rows,[("step","Step"),("phase","Phase"),("guidance_category","Advice"),
                ("fixed_indices","PCs fixed"),("regressed_indices","PCs broken"),
                ("loop_cs_messages_after","Loop CS messages after"),("cs_after","Benchmark CS fails after"),
                ("repair_tokens","Tokens"),("repair_time_s","Repair s")]),"",
            f"Final benchmark result: **{q['pc_final_passed']}/{q['pc_total']} PCs**, **{q['cs_final_failed']} failed CS categories**. "
            f"The loop endpoint instead records **{sum(v is True for v in q['loop_final_pc'])}/{q['pc_total']} PCs**, "
            f"**{q['loop_final_cs_messages']} CS messages**, passed={q['loop_final_passed']}. "
            f"Recorded loop regressions: {q['loop_regression_events']}; repair cost: {q['repair_tokens']:,} tokens, {q['repair_time_s']:.2f}s.",""]
        failed_checks=[e["check"] for e in r4["cs_endpoints"] if e["query_uid"]==uid and e["finally_failed"]]
        lines += ["Remaining benchmark CS categories: "+"; ".join(failed_checks)+".",""]
        if "R0" in datasets:
            baseline=next(x for x in datasets["R0"]["queries"] if x["query_uid"]==uid)
            lines += [f"For the same request, R0 starts at {baseline['pc_initial_passed']}/{baseline['pc_total']} PCs and finishes at "
                f"{baseline['pc_final_passed']}/{baseline['pc_total']}, with {baseline['cs_final_failed']} benchmark CS failures and "
                f"{baseline['repair_tokens']:,} repair tokens. Its initial plan differs from R4's.",""]
    lines += ["The TRAIN cascade e20241028160908981620 remains a useful introductory example, but is not part of these TEST aggregates. "
              "The hot-pot success can be shown beside R0 for the same request, explicitly displaying their different initial plans. "
              "The unsupported-edge case illustrates a limitation; it is not an R4 guidance-disabled experiment.","",
        "## How to read these results","",
        "- Endpoint quality is the final accepted trial plan scored by the existing benchmark helpers. R4 selected-export provenance is retained separately and checked for endpoint equality.",
        "- Mean per-query PC satisfaction and pooled logical micro use different weights. Both are labelled; logical macro means every PC passes.",
        "- Loop states reflect what the repair saw, including Chinese/English named-place mismatches and Unknown states. Offline benchmark endpoint scoring must not overwrite that history.",
        "- Round-level CS fixes/new failures are locally rescored on saved translated plans, with identical 28-check definitions. The category universe comes from the saved full-cohort benchmark CSV because a single-plan evaluator call can omit zero-failure columns. A scoring exception makes transition counts NA rather than silently zero.",
        "- Fix/regression events can repeat. Endpoint gains and unique query-constraint instances are separate columns.",
        "- Every opportunity rate includes its denominator. Unknown endpoints are excluded from known-state event denominators and counted separately.",
        "- Group-by-round quality carries the last accepted state forward after stopping; active-query counts are also shown to expose survivor bias.",
        "- Repair cost includes every retained proposal, including no-ops and guarded proposals; cached requests can cost zero model tokens. Initialization and superseded retries are excluded from repair totals.",
        "- All comparisons are descriptive. No significance tests, independence assumptions for attempts, or causal matrix-effect estimates are supplied.","",
        "## Reproduce and inspect","",
        b*3+"powershell", "python test_results_r4.py --analysis all",
        "python test_results_r4.py --analysis r4",
        "python test_results_r4.py --analysis r0-vs-r4",
        "python test_results_r4.py --analysis guidance",
        "python test_results_r4.py --analysis all --query-uid h20241029143652031792",b*3,"",
        "Run from this folder or provide the script's path. Defaults resolve relative to the script, not the working directory. "
        "Use --run-r4, --run-r0 and --output-dir to choose different saved runs/output locations. "
        "--query-uid filters only the detailed trace export; summary denominators stay unchanged.","",
        "Requires the project's existing evaluator environment (including pandas). The script adds no model requests and writes only to the output directory. "
        "SVG charts use the Python standard library, so no plotting installation is needed.","",
        "Sources and checks: [metric definitions](metric_definitions.csv), [source manifest](source_manifest.csv), "
        "[per-query reconciliation](r4/validation.csv), and [query/attempt audits](test_results_r4_queries.csv). "
        f"Analysis implementation version: {ANALYSIS_VERSION}. Evaluator/source hashes are recorded in source_manifest.csv.","",
        "Recommended slide wording: report final quality, actual loop regressions, and cost separately. "
        "Replace 'zero new violations' when the evidence only shows zero queries with a lower final PC score. "
        "Label R0/R4 as a strategy comparison and supported-only/mixed as observed coverage groups. "
        "Keep detailed family rankings and query traces in the appendix.",""]
    # Omit links to comparison/guidance sections not generated by the selected mode.
    content="\n".join(lines)
    (output/"ANALYSIS.md").write_text(content,encoding="utf-8")
    try:
        script_link=Path(os.path.relpath(Path(__file__).resolve(),output)).as_posix()
    except ValueError:
        # Windows permits output on a different drive from the source checkout.
        script_link=Path(__file__).resolve().as_posix()
    readme=["# R4 TEST analysis outputs","",
        "Start with [ANALYSIS.md](ANALYSIS.md) for results, interpretation and demo traces.","",
        f"One source file controls all analysis: [test_results_r4.py]({script_link}). "
        "The root test_results_r4*.csv files retain the compact Excel table and coverage audits.","",
        "| Folder/file | Purpose |","|---|---|",
        "| r4/ | Initial/final quality, per-query costs, constraint rankings, events, phases, rounds and validation |",
        "| r0_vs_r4/ | Paired differences, compatibility checks, and R0 detail tables |",
        "| guidance/ | Mutually exclusive query/attempt groups and supported/unsupported edge outcomes |",
        "| metric_definitions.csv | Definitions, units and denominators |",
        "| source_manifest.csv | Exact artifact and evaluator fingerprints |",
        "| figures/ | Reproducible SVG figures referenced by the Markdown report |","",
        "## Main tables to use","",
        "| Question | Start here |",
        "|---|---|",
        "| How well does R4 finish, by difficulty? | r4/overview.csv |",
        "| What happens on each query, including token/time cost? | r4/per_query.csv |",
        "| Which kinds/families are fixed or broken most? | r4/constraint_types.csv |",
        "| What happens at each repair step for a particular constraint? | r4/query_trace.csv |",
        "| Which of the 28 CS checks improve or regress? | r4/commonsense_checks.csv |",
        "| What differs between R0 and R4 on the same request? | r0_vs_r4/paired_queries.csv |",
        "| Which settings/initial plans differ? | r0_vs_r4/compatibility.csv |",
        "| How do supported-only and mixed queries compare? | guidance/query_groups.csv |",
        "| How do advice categories compare within repair phases? | guidance/attempt_groups.csv |",
        "| Was the particular regression edge supported? | guidance/edge_outcomes.csv |","",
        "Empty numeric CSV cells mean unavailable/not applicable, not zero. Preserve denominators, difficulty, phase and scoring basis when copying a value into Excel. "
        "Category totals are mutually exclusive only within the same grain, group and phase.","",
        "Only the requested analysis modes are refreshed. Use --analysis all for a coherent full report. "
        "Raw run artifacts are read-only. No p-values are computed."]
    (output/"README.md").write_text("\n".join(readme)+"\n",encoding="utf8")


def run_analyses(args,output):
    sys.path.insert(0,str(PROJECT_ROOT))
    cache={}
    data={"R4":extract_run("R4",args.run_r4.resolve(),cache)}
    selected=set(args.query_uid or [])
    if selected-set(data["R4"]["manifest"]["query_uids"]):
        raise ValueError("Requested --query-uid is not in the R4 TEST population")
    # R4 evidence underpins all modes, so its detailed tables are always available.
    export_run(data["R4"],output/"r4",selected)
    paired=[]
    query_groups=[]
    attempt_groups=[]
    if args.analysis in ("all","r0-vs-r4"):
        data["R0"]=extract_run("R0",args.run_r0.resolve(),cache)
        paired,_=comparison_tables(data["R0"],data["R4"],output/"r0_vs_r4")
    if args.analysis in ("all","guidance"):
        query_groups,attempt_groups=guidance_tables(data["R4"],output/"guidance")
    export_csv(output/"metric_definitions.csv",[dict(metric=m,unit=u,definition=d) for m,u,d in CORE_DEFINITIONS])
    sources=[]
    for role,d in data.items():
        sources.extend(d["sources"])
        for p in [d["root"]/"run_manifest.json",d["root"]/"summaries.csv",d["root"]/"attempts.jsonl",
                  PROJECT_ROOT/"scripts/result_analysis/build_test_result_tables.py",
                  PROJECT_ROOT/"chinatravel/evaluation/hard_constraint.py",
                  PROJECT_ROOT/"chinatravel/evaluation/schema_constraint.py",
                  PROJECT_ROOT/"chinatravel/evaluation/output_schema.json",
                  PROJECT_ROOT/"chinatravel/evaluation/commonsense_constraint.py",
                  PROJECT_ROOT/"chinatravel/evaluation/constraint_families.py",
                  *sorted((d["root"]/"inputs").glob("*/main_matrix.csv")),
                  *sorted((d["root"]/"inputs").glob("*/main_matrix_manifest.json"))]:
            sources.append(dict(strategy=role,path=str(p.relative_to(PROJECT_ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    source_file=Path(__file__).resolve()
    sources.append(dict(strategy="analysis",path=str(source_file.relative_to(PROJECT_ROOT)),
        sha256=hashlib.sha256(source_file.read_bytes()).hexdigest(),
        analysis_mode=args.analysis,trace_query_filter=sorted(selected),analysis_version=ANALYSIS_VERSION))
    export_csv(output/"source_manifest.csv",sources)
    write_report(output,data,paired,query_groups,attempt_groups,selected)
    print(f"Completed {args.analysis}: {len(cache)} unique saved plans scored locally. Report: {output/'ANALYSIS.md'}",flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", "--run-r4", dest="run_r4", type=Path, default=PROJECT_ROOT / "experiments/subset_test-r4",
                        help="Saved R4 run directory (default: experiments/subset_test-r4)")
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR,
                        help="Output CSV directory (default: beside this script)")
    parser.add_argument("--analysis",choices=["coverage","r4","r0-vs-r4","guidance","all"],default="all",
                        help="Analysis to generate (default: all); coverage reproduces the compact table only")
    parser.add_argument("--run-r0",type=Path,default=PROJECT_ROOT/"experiments/subset_test-r0")
    parser.add_argument("--query-uid",action="append",help="Limit detailed trace exports to this UID; repeatable; summaries retain all queries")
    args = parser.parse_args(argv)
    run_dir, output_dir = args.run_r4.resolve(), args.output_dir.resolve()
    queries = load_queries(run_dir)
    attempts = load_attempts(run_dir, queries)
    query_rows = summarize_queries(queries, attempts)
    table = build_table(query_rows)
    definitions = [{"Metric": metric, "Unit": "unique queries", "Definition": definition}
                   for metric, _flag, definition in METRICS]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "test_results_r4.csv", table, TABLE_COLUMNS)
    write_csv(output_dir / "test_results_r4_queries.csv", query_rows)
    write_csv(output_dir / "test_results_r4_attempts.csv", attempts,
              list(attempts[0]) if attempts else ["query_uid", "difficulty", "step"])
    write_csv(output_dir / "test_results_r4_definitions.csv", definitions)
    print(f"Read {len(queries)} queries and {len(attempts)} attempts from {run_dir}")
    for row in table:
        values = " | ".join(f"{group}: {row[group]}" for group in GROUPS)
        print(f"{row['Metric']}: {values}")
    print("Verified: guidance categories are mutually exclusive and sum to each query total.")
    print("Both types may occur in different attempts; no relationship includes zero-attempt queries.")
    print(f"Wrote four CSV files to {output_dir}")
    if args.analysis != "coverage":
        run_analyses(args,output_dir)


if __name__ == "__main__":
    main()
