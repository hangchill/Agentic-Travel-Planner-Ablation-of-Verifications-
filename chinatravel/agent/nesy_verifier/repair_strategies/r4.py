"""Whole-plan repair with advisory regression-matrix guidance and R3's contract."""

import csv
import hashlib
import json
import math
import time
from copy import deepcopy
from pathlib import Path

from chinatravel.agent.nesy_verifier.repair_strategies.base import RepairResult
from chinatravel.agent.nesy_verifier.repair_strategies.r3 import (
    PLAN, SCOPE_LEVEL, R3AdaptiveScopeRepair, _feedback_commonsense_count,
    _feedback_personal_indices, _structure_problem, _total_slots,
)
from chinatravel.evaluation.repair_attempt import failed_constraint_indices
from chinatravel.evaluation.constraint_families import (
    CONSTRAINT_FAMILIES,
    classify_constraints,
)
from r4.build_main_matrix import SOURCE_FAMILIES, DESTINATION_FAMILIES
from r4.commonsense_evidence import COMMONSENSE_FAMILY, commonsense_state


class MatrixGuidedRepair(R3AdaptiveScopeRepair):
    """Let the model choose repairs using matrix advice, with full-plan freedom.

    R3's parsing, feedback, structure checks and metadata helpers are reused.
    The shared loop owns the attempt budget and the personal/commonsense schedule.
    Matrix rankings are recommendations and never filter the repair targets.
    """

    def __init__(self, matrix_path, neutral_risk=0.5):
        super().__init__()
        if not 0 <= neutral_risk <= 1:
            raise ValueError("neutral_risk must be between 0 and 1")
        self.matrix_path = Path(matrix_path).resolve()
        self.neutral_risk = float(neutral_risk)
        self._matrix, self._matrix_sha256 = self._load_matrix(self.matrix_path)
        manifest_path = self.matrix_path.with_name("main_matrix_manifest.json")
        self._matrix_perspective = "candidate"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            perspective = manifest.get("perspective", "candidate")
            if perspective not in ("candidate", "accepted"):
                raise ValueError(f"{manifest_path}: unsupported matrix perspective")
            self._matrix_perspective = perspective
        self._strategy_name = "R4"

    @staticmethod
    def _load_matrix(path):
        if not path.is_file():
            raise FileNotFoundError(f"R4 risk matrix does not exist: {path}")
        matrix = {}
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            expected = {
                "source_family", "destination_family", "regression_count",
                "support_count", "regression_probability", "evidence_status",
            }
            if reader.fieldnames is None or not expected.issubset(reader.fieldnames):
                raise ValueError(f"{path}: not an R4 main_matrix.csv")
            for row in reader:
                source, destination = row["source_family"], row["destination_family"]
                if source not in SOURCE_FAMILIES or destination not in DESTINATION_FAMILIES:
                    raise ValueError(f"{path}: unknown constraint family in {(source, destination)}")
                if destination in matrix.setdefault(source, {}):
                    raise ValueError(f"{path}: duplicate matrix cell {(source, destination)}")
                unavailable = row["evidence_status"] == "unavailable"
                support = None if unavailable else int(row["support_count"])
                count = None if unavailable else int(row["regression_count"])
                if unavailable and (destination != COMMONSENSE_FAMILY or source == destination
                                    or row["support_count"] != "" or row["regression_count"] != ""
                                    or row.get("support_query_count", "") != ""
                                    or row["regression_probability"] != ""):
                    raise ValueError(f"{path}: unavailable evidence must have blank counts and probability")
                if not unavailable and (support < 0 or count < 0 or count > support):
                    raise ValueError(f"{path}: invalid counts for {(source, destination)}")
                raw_probability = row["regression_probability"]
                probability = None if raw_probability == "" else float(raw_probability)
                if probability is not None and (
                    not math.isfinite(probability) or not 0 <= probability <= 1
                ):
                    raise ValueError(f"{path}: invalid probability for {(source, destination)}")
                if source == destination:
                    if support or count or probability is not None:
                        raise ValueError(f"{path}: diagonal must be unsupported")
                elif bool(support) != (probability is not None):
                    raise ValueError(f"{path}: probability/support mismatch for {(source, destination)}")
                elif support and abs(probability - count / support) > 1e-9:
                    raise ValueError(f"{path}: probability/count/support mismatch for {(source, destination)}")
                matrix[source][destination] = {
                    "probability": probability,
                    "support_count": support,
                    "support_query_count": None if unavailable else int(row.get("support_query_count") or 0),
                    "regression_count": count,
                    "evidence_status": row["evidence_status"],
                }
        if set(matrix) != set(SOURCE_FAMILIES):
            raise ValueError(f"{path}: expected all ten source families")
        axes = [set(matrix[source]) for source in SOURCE_FAMILIES]
        if all(axis == set(CONSTRAINT_FAMILIES) for axis in axes):
            # Older saved runs use 10 by 9 evidence; absence is unknown.
            for source in SOURCE_FAMILIES:
                diagonal = source == COMMONSENSE_FAMILY
                matrix[source][COMMONSENSE_FAMILY] = {
                    "probability": None, "support_count": 0 if diagonal else None,
                    "support_query_count": 0 if diagonal else None,
                    "regression_count": 0 if diagonal else None,
                    "evidence_status": "structural_diagonal" if diagonal else "unavailable",
                }
        elif any(axis != set(DESTINATION_FAMILIES) for axis in axes):
            raise ValueError(f"{path}: expected a complete 10-by-10 matrix (or legacy 10-by-9)")
        return matrix, hashlib.sha256(path.read_bytes()).hexdigest()

    def _recommend_target(self, problem, verification):
        states = verification.get("personal_constraints", []) or []
        failed = [index for index, state in enumerate(states, 1) if state is False]
        if not failed:
            return None, []

        constraints = problem.get("hard_logic_py", []) or []
        descriptors = [
            {"constraint_index": index, "hard_logic_py": constraint}
            for index, constraint in enumerate(constraints, 1)
        ]
        classified = {
            item["constraint_index"]: item
            for item in classify_constraints(descriptors)
        }
        passing_families = {
            classified[index]["family"]
            for index, state in enumerate(states, 1)
            if state is True
            and index in classified
            and classified[index]["classification_status"] == "mapped"
        }
        if commonsense_state(verification) is True:
            passing_families.add(COMMONSENSE_FAMILY)

        candidates = []
        for index in failed:
            classification = classified.get(index, {})
            source = (
                classification.get("family")
                if classification.get("classification_status") == "mapped"
                else None
            )
            destinations = []
            total_risk = 0.0
            total_support = 0
            for destination in sorted(passing_families):
                if source == destination:
                    continue
                cell = self._matrix[source][destination] if source else None
                probability = (
                    cell["probability"]
                    if cell is not None and cell["probability"] is not None
                    else self.neutral_risk
                )
                support = cell["support_count"] if cell is not None else 0
                total_risk += probability
                total_support += support or 0
                destinations.append({
                    "family": destination,
                    "regression_probability": probability,
                    "support_count": support,
                    "support_query_count": cell.get("support_query_count") if cell else None,
                    "evidence_status": (
                        cell["evidence_status"] if cell else "unmapped_target_neutral_fallback"
                    ),
                })
            candidates.append({
                "constraint_index": index,
                "family": source,
                "expected_regressed_families": total_risk,
                "support_sum": total_support,
                "destination_risks": destinations,
            })

        # Minimize expected regressions, prefer better-supported ties, then stable index.
        candidates.sort(key=lambda item: (
            item["expected_regressed_families"], -item["support_sum"],
            item["constraint_index"],
        ))
        return candidates[0], candidates

    def _commonsense_risks(self, problem, verification):
        states = verification.get("personal_constraints", []) or []
        descriptors = [
            {"constraint_index": index, "hard_logic_py": constraint}
            for index, constraint in enumerate(problem.get("hard_logic_py", []) or [], 1)
        ]
        mapped = {item["constraint_index"]: item for item in classify_constraints(descriptors)}
        risks = []
        for index, state in enumerate(states, 1):
            item = mapped.get(index, {})
            family = item.get("family")
            if state is not True or item.get("classification_status") != "mapped" or family not in DESTINATION_FAMILIES:
                continue
            cell = self._matrix["commonsense_repair"][family]
            risks.append({
                "family": family,
                "regression_probability": cell["probability"] if cell["probability"] is not None else self.neutral_risk,
                "support_count": cell["support_count"],
                "support_query_count": cell.get("support_query_count", 0),
                "evidence_status": cell["evidence_status"] if cell["probability"] is not None else "unobserved_neutral_fallback",
            })
        return risks

    @staticmethod
    def _matrix_guidance(recommended, ranking, phase, commonsense_risks=None):
        lines = [
            "R4 MATRIX GUIDANCE (advisory):",
            "You may edit the whole plan. Use the matrix as advice: choose which "
            "failures to repair together, their order, and which variables to change. "
            "You may depart from the ranking. Preserve currently satisfied constraints.",
        ]
        if phase == "commonsense":
            lines.append(
                "This attempt targets the supplied commonsense failures. Historical "
                "commonsense repairs are associated with these risks to currently passing personal families:"
            )
            for cell in commonsense_risks or []:
                lines.append(
                    f"- {cell['family']}: estimated regression probability "
                    f"{cell['regression_probability']:.3f} (attempt support={cell['support_count']}, "
                    f"query support={cell.get('support_query_count', 0)}, evidence={cell['evidence_status']})."
                )
            if not commonsense_risks:
                lines.append("No mapped passing personal family is available for a risk estimate.")
        elif recommended is None:
            lines.append(
                "No currently failing personal constraint is available to rank. "
                "Address the supplied feedback, including UNKNOWN personal checks."
            )
        else:
            lines.extend([
                f"Lowest estimated regression risk: personal constraint "
                f"{recommended['constraint_index']} (a recommendation, not a required target).",
                "All current failed personal targets, ranked by summed regression "
                "probabilities to currently passing families. Probabilities are "
                "empirical only when support > 0; unsupported cells use a neutral fallback:",
            ])
            for candidate in ranking:
                lines.append(
                    f"Personal constraint {candidate['constraint_index']} "
                    f"(family={candidate['family'] or 'unmapped'}, "
                    f"expected_regressed_families={candidate['expected_regressed_families']:.3f}):"
                )
                lines.extend(
                    f"- {cell['family']}: estimated regression probability "
                    f"{cell['regression_probability']:.3f} (attempt support={cell['support_count']}, "
                    f"query support={cell.get('support_query_count', 0)}, evidence={cell['evidence_status']})"
                    for cell in candidate["destination_risks"]
                )
                if not candidate["destination_risks"]:
                    lines.append("- No mapped passing destination family to score.")
        return "\n".join(lines)

    def repair(self, problem, raw_plan, verification_results, context, llm):
        self._step += 1
        phase = context.get("repair_phase")
        if phase not in (None, "personal", "commonsense"):
            raise ValueError("Unknown shared repair_phase")
        if phase != "commonsense":
            self._iteration += 1

        objective_verification = verification_results
        if phase == "commonsense":
            objective_verification = {
                **verification_results,
                "schema_errors": [],
                "error_info": list(verification_results.get("commonsense_errors") or []),
            }
        targets = self._collect_targets(problem, objective_verification, phase)
        localized = self._localize_targets(targets, raw_plan)
        editable, global_present = self._editable_region(PLAN, raw_plan, localized)
        feedback_lines, protected = self._feedback_lines(problem, objective_verification, phase)
        if phase == "personal":
            hard_logic = problem.get("hard_logic_py", [])
            feedback_lines.extend(
                f"Personal constraint {i} is UNKNOWN; make it evaluable: {hard_logic[i - 1]}"
                for i, state in enumerate(verification_results.get("personal_constraints", []), 1)
                if state is None and i <= len(hard_logic)
            )

        recommended, ranking = (
            (None, []) if phase == "commonsense"
            else self._recommend_target(problem, verification_results)
        )
        commonsense_risks = self._commonsense_risks(problem, verification_results) if phase == "commonsense" else []
        query_message = self._build_prompt(
            PLAN, problem, context, raw_plan, feedback_lines, editable
        ) + "\n\n" + self._matrix_guidance(recommended, ranking, phase, commonsense_risks)
        start_time = time.time()
        response = llm([{"role": "user", "content": query_message}], one_line=False)
        inference_time = time.time() - start_time
        proposal, raw_response = self._parse_response(response)
        structure_problem = _structure_problem(raw_plan, proposal) if proposal is not None else None
        if proposal is None or structure_problem is not None:
            merged, changed = deepcopy(raw_plan), 0
        else:
            merged, changed = proposal, self._count_changed_all(raw_plan, proposal)

        total = _total_slots(raw_plan)
        metadata = {
            "strategy": "R4",
            "target_constraint_indices": [] if phase == "commonsense" else failed_constraint_indices(
                verification_results.get("personal_constraints", []) or []
            ),
            "editable_scope": PLAN,
            "scope_level": SCOPE_LEVEL[PLAN],
            "target_provenance": "r4_matrix_guidance",
            "feedback_personal_constraint_indices": _feedback_personal_indices(feedback_lines),
            "feedback_commonsense_failure_count": _feedback_commonsense_count(
                verification_results.get("commonsense_errors"), feedback_lines
            ),
            "parse_failed": proposal is None,
            "proposal_rejected_reason": structure_problem,
            "scope_fraction": round(len(editable) / total, 4) if total else 0.0,
            "changed_slots": changed,
            "editable_slots": self._slot_descriptors(editable, raw_plan),
            "targeted_constraints": targets,
            "per_target_edits": self._per_target_edits(
                targets, localized, editable, raw_plan, merged, raw_plan
            ),
            "global_targets": global_present,
            "iteration": self._iteration,
            "prompt": query_message,
            "raw_response": raw_response,
            "llm_inference_time": inference_time,
            "risk_matrix_sha256": self._matrix_sha256,
            "risk_matrix_path": str(self.matrix_path),
            "neutral_risk_fallback": self.neutral_risk,
            "matrix_guidance_policy": "advisory",
            "recommended_risk_target": recommended,
            "risk_target_ranking": ranking,
            "commonsense_source_risks": commonsense_risks,
            "matrix_perspective": self._matrix_perspective,
            "full_verification_report": verification_results,
        }
        if phase is not None:
            metadata.update({
                "protected_constraint_indices": protected,
                "repair_phase": phase,
                "target_commonsense_errors": (
                    list(objective_verification.get("commonsense_errors") or [])
                    if phase == "commonsense" else []
                ),
                "personal_iteration": self._iteration,
                "repair_call": self._step,
            })
        return RepairResult(repaired_plan=merged, metadata=metadata)
