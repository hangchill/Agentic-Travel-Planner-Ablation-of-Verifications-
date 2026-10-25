"""Streamlit UI for the verification-guided travel planner."""

from datetime import datetime, timezone
import os
from pathlib import Path
import uuid

import streamlit as st
from dotenv import load_dotenv

from frontend.history import discover_saved_runs
from frontend.planner import PROJECT_ROOT, execute_trip
from frontend.presentation import (
    ACTIVITY_ICONS,
    ACTIVITY_LABELS,
    activity_title,
    change_summary,
    count_constraint_states,
    format_money,
    itinerary_days,
    transport_description,
    verification_issue_groups,
)
from frontend.storage import save_run_artifacts


load_dotenv(PROJECT_ROOT / ".env")

RUNS_DIR = Path(__file__).resolve().parent / "runs"
DEFAULT_MODEL = "deepseek/deepseek-chat"
STRATEGIES = ("R0", "R1", "R2", "R3", "R4")
DEFAULT_STRATEGY = "R3"


def _render_itinerary(plan: object) -> None:
    days = itinerary_days(plan)
    if not days:
        st.warning("The planner did not return a displayable day-by-day itinerary.")
        return

    for day_number, day in enumerate(days, start=1):
        activities = day.get("activities")
        if not isinstance(activities, list):
            activities = []
        day_label = day.get("day", day_number)
        day_total = sum(
            float(activity["cost"])
            for activity in activities
            if isinstance(activity, dict)
            and isinstance(activity.get("cost"), (int, float))
            and not isinstance(activity.get("cost"), bool)
        )
        st.markdown(f"### Day {day_label}")
        st.caption(
            f"{len(activities)} planned activities"
            + (f" · Listed costs total {format_money(day_total)}" if day_total else "")
        )
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            activity_type = str(activity.get("type", "")).lower()
            label = ACTIVITY_LABELS.get(activity_type, activity_type.title() or "Activity")
            icon = ACTIVITY_ICONS.get(activity_type, "•")
            title = activity_title(activity)
            start_time = activity.get("start_time")
            end_time = activity.get("end_time")

            with st.container(border=True):
                time_col, detail_col, cost_col = st.columns([1, 4, 1])
                with time_col:
                    st.markdown(f"**{start_time or 'Time TBD'}**")
                    if end_time:
                        st.caption(f"to {end_time}")
                with detail_col:
                    st.markdown(f"{icon} **{label}: {title}**")
                    transport = transport_description(activity.get("transports"))
                    if transport:
                        st.caption(f"🚗 {transport}")
                    extras = []
                    for key, display in (
                        ("FlightID", "Flight"),
                        ("TrainID", "Train"),
                        ("tickets", "Tickets"),
                        ("rooms", "Rooms"),
                    ):
                        value = activity.get(key)
                        if value is not None:
                            extras.append(f"{display}: {value}")
                    room_type = activity.get("room_type")
                    if room_type is not None:
                        extras.append(
                            f"Room type: {'single' if room_type == 1 else 'double' if room_type == 2 else room_type}"
                        )
                    if extras:
                        st.caption(" · ".join(extras))
                with cost_col:
                    cost = format_money(activity.get("cost"))
                    if cost:
                        st.markdown(f"**{cost}**")
                        st.caption("listed cost")


def _render_verification(verification: object) -> None:
    if not isinstance(verification, dict):
        st.info("No verification result was recorded.")
        return

    passed = verification.get("passed")
    if passed is True:
        st.success("All available verification checks passed.")
    elif passed is None:
        st.info("This saved result does not include an overall verification status.")
    else:
        st.warning("The itinerary has checks that need attention.")

    constraint_counts = count_constraint_states(
        verification.get("personal_constraints")
    )
    issues = verification_issue_groups(verification)
    technical_count = sum(
        len(values)
        for label, values in issues
        if label in {"Itinerary structure", "Travel / transport", "Verification execution", "Verifier diagnostics"}
    )
    cols = st.columns(4)
    cols[0].metric("Preference checks passed", constraint_counts["passed"])
    cols[1].metric("Preference checks failed", constraint_counts["failed"])
    cols[2].metric("Commonsense issues", len(verification.get("commonsense_errors") or []))
    cols[3].metric("Technical issues", technical_count)

    states = verification.get("personal_constraints")
    if not isinstance(states, list) or not states:
        st.info(
            "No formal preference rules were available to score for this result."
        )
    else:
        with st.expander("Preference check results", expanded=constraint_counts["failed"] > 0):
            for index, state in enumerate(states, start=1):
                if state is True:
                    st.write(f"✅ Preference check {index}: passed")
                elif state is False:
                    st.write(f"❌ Preference check {index}: failed")
                else:
                    st.write(f"❔ Preference check {index}: unknown")

    if issues:
        with st.expander("Issues and diagnostics", expanded=passed is not True):
            for label, values in issues:
                st.markdown(f"**{label}**")
                for value in values:
                    if isinstance(value, dict):
                        index = value.get("constraint_index")
                        message = value.get("error") or value.get("message") or str(value)
                        prefix = f"Check {index}: " if index is not None else ""
                        st.write(f"- {prefix}{message}")
                    else:
                        st.write(f"- {value}")


def _render_repair_history(history: object) -> None:
    if not isinstance(history, list) or not history:
        st.info("No repair history was recorded.")
        return

    repair_entries = [entry for entry in history if isinstance(entry, dict)]
    repair_attempts = [
        entry for entry in repair_entries
        if isinstance(entry.get("step"), (int, float)) and entry["step"] > 0
    ]
    accepted_count = sum(entry.get("accepted") is True for entry in repair_attempts)
    cols = st.columns(3)
    cols[0].metric("Repair attempts", len(repair_attempts))
    cols[1].metric("Accepted", accepted_count)
    cols[2].metric("Not accepted", len(repair_attempts) - accepted_count)

    for entry in repair_entries:
        step = entry.get("step", "?")
        attempt = entry.get("repair_attempt")
        if not isinstance(attempt, dict):
            attempt = {}
        is_initial = isinstance(step, (int, float)) and step == 0
        accepted = entry.get("accepted") is True
        heading = "Initial itinerary check" if is_initial else f"Repair attempt {step}"
        with st.container(border=True):
            title_col, result_col = st.columns([4, 1])
            title_col.markdown(f"**{heading}**")
            if is_initial:
                result_col.markdown("Starting plan")
            elif accepted:
                result_col.success("Accepted")
            else:
                result_col.error("Not accepted")

            metadata = entry.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            phase = attempt.get("repair_phase") or metadata.get("repair_phase")
            scope = attempt.get("editable_scope")
            labels = attempt.get("target_constraint_labels") or []
            indices = attempt.get("target_constraint_indices") or []
            details = []
            if phase:
                details.append(f"Repair focus: {str(phase).title()}")
            if scope:
                details.append(f"Editable scope: {str(scope).replace('_', ' ')}")
            if labels:
                details.append(f"Target checks: {', '.join(map(str, labels))}")
            elif indices:
                details.append(f"Target check numbers: {', '.join(map(str, indices))}")
            if details:
                st.caption(" · ".join(details))

            changes = change_summary(entry)
            if changes:
                for change in changes:
                    st.write(f"- {change}")
            elif not is_initial:
                before = count_constraint_states(attempt.get("before_personal_constraints"))
                after = count_constraint_states(attempt.get("after_personal_constraints"))
                if before["passed"] or after["passed"] or before["failed"] or after["failed"]:
                    st.caption(
                        f"Preference checks: {before['passed']} passed / {before['failed']} "
                        f"failed before → {after['passed']} passed / {after['failed']} failed after"
                    )

            reason = attempt.get("decision_reason") or attempt.get("escalation_reason")
            if reason:
                st.write(f"**Reason:** {reason}")
            error = attempt.get("exception")
            if error:
                st.error(f"Attempt error: {error}")

            duration = attempt.get("attempt_time_seconds")
            if isinstance(duration, (int, float)):
                st.caption(f"Time spent: {duration:.1f} seconds")

            candidate_verification = entry.get("verification")
            if not is_initial and isinstance(candidate_verification, dict):
                with st.expander("Checks for this proposed repair"):
                    _render_verification(candidate_verification)


def _render_run(record: dict) -> None:
    request = record.get("request", {})
    if request:
        st.markdown(
            f"**{request.get('start_city', '?')} → {request.get('target_city', '?')}**"
            f" · {request.get('days', '?')} days"
            f" · {request.get('people_number', '?')} traveller(s)"
            f" · Strategy {request.get('strategy', '?')}"
        )
        st.write(request.get("prompt", ""))

    if record.get("itinerary") is not None:
        st.subheader("Your itinerary")
        _render_itinerary(record["itinerary"])
    if record.get("verification") is not None:
        st.subheader("Verification summary")
        _render_verification(record["verification"])
    if record.get("repair_history") is not None:
        st.subheader("How the planner refined it")
        _render_repair_history(record["repair_history"])


def main() -> None:
    st.set_page_config(page_title="Travel Planner", page_icon="✈️", layout="wide")
    st.title("Verification-Guided Travel Planner")
    st.caption(
        "Describe a trip and inspect the itinerary, verification result, and "
        "repair attempts produced by the selected strategy."
    )

    saved_runs, history_errors = discover_saved_runs(PROJECT_ROOT)
    st.subheader("Past results")
    if saved_runs:
        st.caption(
            f"{len(saved_runs)} saved result(s) found on this computer. "
            "Opening one does not call the model API."
        )
        selected_history_index = st.selectbox(
            "Display a previous itinerary",
            options=[-1, *range(len(saved_runs))],
            index=0,
            format_func=lambda index: (
                "Choose a saved result..."
                if index < 0
                else saved_runs[index].get("history_label", "Saved result")
            ),
            key="saved_history_selection",
        )
        if selected_history_index >= 0:
            saved_record = saved_runs[selected_history_index]
            st.caption(
                f"Loaded from {saved_record.get('history_source', 'saved run')}: "
                f"{saved_record.get('history_path', '')}"
            )
            _render_run(saved_record)
    else:
        st.info(
            "No saved itineraries were found yet. Completed runs will appear here, "
            "along with recognized results already saved under experiments/."
        )
    if history_errors:
        with st.expander(f"Could not read {len(history_errors)} saved file(s)"):
            for error in history_errors[:20]:
                st.write(f"- {error}")
            if len(history_errors) > 20:
                st.caption(f"...and {len(history_errors) - 20} more.")

    st.divider()
    with st.sidebar:
        st.header("Planner settings")
        cities = ["Beijing", "Shanghai", "Nanjing", "Suzhou", "Hangzhou",
                  "Shenzhen", "Chengdu", "Wuhan", "Guangzhou", "Chongqing"]
        start_city = st.selectbox("Starting city", cities, index=0)
        target_city = st.selectbox(
            "Destination", [city for city in cities if city != start_city]
        )
        people_number = st.number_input("Travellers", min_value=1, max_value=20, value=2)
        days = st.number_input("Trip length (days)", min_value=1, max_value=14, value=3)
        strategy = st.selectbox(
            "Repair strategy",
            STRATEGIES,
            index=STRATEGIES.index(DEFAULT_STRATEGY),
        )
        matrix_path = ""
        if strategy == "R4":
            matrix_path = st.text_input(
                "R4 pooled matrix path",
                value=os.getenv("CHINATRAVEL_R4_MATRIX", ""),
                help=(
                    "Path to an empirical R0-R3 pooled main_matrix.csv with its "
                    "manifest and source matrix provenance."
                ),
            ).strip()
            st.caption(
                "R4 requires a validated empirical pooled matrix. Synthetic fixture "
                "matrices are not accepted by the demo."
            )
        max_steps = st.slider("Maximum repair attempts", min_value=0, max_value=6, value=3)
        model_name = st.text_input(
            "Model",
            value=os.getenv("CHINATRAVEL_OPENAI_MODEL", DEFAULT_MODEL),
        )

    prompt = st.text_area(
        "What would you like to do?",
        placeholder=(
            "For example: I enjoy museums and local food. Keep the schedule relaxed "
            "and avoid expensive attractions."
        ),
        height=150,
    )
    st.info(
        "The shared verifier checks itinerary structure, travel data, and "
        "commonsense constraints. Free-text preferences are included in the planning "
        "prompt, but are not converted into formal personal-constraint rules."
    )

    if st.button(
        "Generate itinerary",
        type="primary",
        disabled=(
            not prompt.strip()
            or not model_name.strip()
            or (strategy == "R4" and not matrix_path)
        ),
    ):
        run_id = uuid.uuid4().hex
        run_dir = RUNS_DIR / run_id
        request = {
            "run_id": run_id,
            "prompt": prompt.strip(),
            "start_city": start_city,
            "target_city": target_city,
            "people_number": int(people_number),
            "days": int(days),
            "strategy": strategy,
            "matrix_path": matrix_path or None,
            "max_steps": max_steps,
            "model": model_name.strip(),
        }
        record = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "request": request,
            "itinerary": None,
            "verification": None,
            "repair_history": [],
            "attempts": [],
        }
        save_run_artifacts(run_dir, record)

        def checkpoint_history(history: list[dict]) -> None:
            record["repair_history"] = history
            record["attempts"] = [
                entry["repair_attempt"]
                for entry in history
                if isinstance(entry.get("repair_attempt"), dict)
            ]
            save_run_artifacts(run_dir, record)

        try:
            with st.spinner("Collecting travel options, generating, and verifying..."):
                result = execute_trip(request, run_dir, checkpoint_history)
            record["itinerary"] = result["itinerary"]
            record["verification"] = result["verification"]
            record["generation_metadata"] = result["generation_metadata"]
            record["repair_history"] = result["repair_history"]
            record["attempts"] = [
                entry["repair_attempt"]
                for entry in result["repair_history"]
                if isinstance(entry.get("repair_attempt"), dict)
            ]
            record["status"] = "completed"
            save_run_artifacts(run_dir, record)
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
            save_run_artifacts(run_dir, record)
            st.error(f"Planner run failed. The partial run was saved to {run_dir}.")
            st.exception(exc)

        if record["status"] == "completed":
            st.success(
                f"Run saved to frontend/runs/{run_id} "
                f"({len(record['attempts'])} repair attempt(s))."
            )
            _render_run(record)

if __name__ == "__main__":
    main()
