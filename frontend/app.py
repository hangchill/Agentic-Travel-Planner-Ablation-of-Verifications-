"""A recorded, API-free demonstration of itinerary verification and repair."""

from html import escape
from pathlib import Path
import sys

# Support `streamlit run frontend/app.py` without installing the project.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from frontend.presentation import ACTIVITY_LABELS, activity_title, format_money, transport_description
from frontend.replay import (
    activity_changes, baseline_index, issue_transitions, listed_cost, load_demo, plan_changes,
    violating_time_fields,
)


CSS = """
<style>
.stApp {background:#f6f7f3;color:#182b28;}
.block-container {max-width:1400px;padding-top:4.2rem;padding-bottom:3rem;}
h1,h2,h3 {color:#182b28;letter-spacing:-.035em;}
h1 {font-size:2.8rem!important;} h3 {font-size:1.25rem!important;}
.eyebrow {color:#427568;font-size:.73rem;font-weight:750;letter-spacing:.16em;text-transform:uppercase;}
.hero {background:#173d35;color:#fff;border-radius:18px;padding:25px 30px;margin:15px 0 22px;}
.hero .route {font-size:1.7rem;font-weight:650;letter-spacing:-.025em;margin:6px 0;}
.hero .query {color:#e0ece7;font-size:1rem;max-width:900px;line-height:1.65;margin:10px 0;}
.hero .meta {color:#bdd4ca;font-size:.85rem;}
.pill {display:inline-block;border-radius:5px;padding:3px 7px;font-size:.69rem;font-weight:650;margin:0 5px 4px 0;}
.red {background:#fce7e4;color:#a63029;} .blue {background:#e4edff;color:#2c59a0;}
.green {background:#e0f0e8;color:#226344;} .gray {background:#ecf0ed;color:#52635b;}
.amber {background:#fff0ce;color:#8c5c0d;}
.activity {background:white;border:1px solid #dfe5df;border-left:4px solid #c9d8ce;border-radius:10px;padding:17px 20px;margin-bottom:10px;}
.activity.invalid {border-left-color:#c95449;background:#fffcfb;}
.activity.changed {box-shadow:inset 0 0 0 1px #98b6ec;}
.activity.focus {outline:2px solid #d79531;outline-offset:2px;}
.activity.resolved {border-left-color:#388467;}
.activity-top {display:flex;justify-content:space-between;gap:20px;align-items:start;}
.activity-title {font-size:1rem;font-weight:650;line-height:1.45;}
.time {color:#5a6962;font-size:.85rem;margin-bottom:7px;}
.bad-value {color:#ac3029;background:#fce7e4;border-radius:3px;padding:1px 3px;font-weight:650;}
.transfer {color:#617069;font-size:.79rem;margin-top:10px;line-height:1.6;}
.issue-inline {color:#a63029;font-size:.82rem;line-height:1.5;margin-top:8px;}
.delta {font-size:.79rem;color:#315c99;padding-top:8px;line-height:1.5;overflow-wrap:anywhere;}
.delta del {color:#77817c;}.cost {font-size:.88rem;white-space:nowrap;font-weight:650;}
.check {border-bottom:1px solid #e1e6df;padding:12px 0;}
.check-title {font-size:.88rem;font-weight:650;line-height:1.5;}
.check-detail {font-size:.79rem;line-height:1.55;color:#63726a;margin-top:4px;}
.legend {font-size:.78rem;color:#65736b;margin:8px 0 16px;}
.trend {display:flex;align-items:center;gap:20px;background:#fff;border:1px solid #e0e5de;border-radius:12px;padding:14px 20px;margin:10px 0 20px;}
.trend svg {width:100%;height:70px;overflow:visible;}.trend-label {min-width:150px;font-size:.8rem;color:#64726a;}
div[data-testid="stMetric"] {background:white;border:1px solid #e0e5de;border-radius:10px;padding:12px 16px;}
button[kind="primary"] {background:#246350;border-color:#246350;}
div[data-testid="stTabs"] {margin-top:15px;}
@media(max-width:640px) {.hero {padding:20px;}h1 {font-size:2rem!important;}.trend-label{min-width:85px;}.activity{padding:14px;}}
</style>
"""


def html(value: object) -> str:
    return escape(str(value))


def badge(text: str, color: str) -> str:
    return f'<span class="pill {color}">{html(text)}</span>'


FIELD_LABELS = {
    "position": "Place", "start_time": "Starts", "end_time": "Ends", "cost": "Cost",
    "price": "Unit price", "transports.from": "Transfer origin", "transports.to": "Transfer destination",
    "transports.start_time": "Transfer departs", "transports.end_time": "Transfer arrives",
    "transports.cost": "Transfer cost", "transports.mode": "Transfer mode",
}

STEP_NOTES = [
    "The initial schedule puts the museum visit and dinner outside opening hours, and both meals start too late.",
    "The repair changes the attraction and dinner venue. The restaurant-hours issue disappears, but the new attraction visit still ends after closing.",
    "A regression: the attraction switches back to the museum, and the verifier flags a metro-fare error. The late meals remain.",
    "The attraction switches back to the palace and the metro-fare error is no longer reported. The visit still ends after closing.",
    "The palace visit now ends at 18:00, and later activities move earlier. Opening hours are resolved, but dinner still starts at 20:30 and lunch at 15:40.",
    "The proposed itinerary is unchanged. The verifier still reports the two late meals.",
    "The final proposal is unchanged again. All six attempts are used, with the two late-meal violations unresolved.",
]


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").replace(".", " · ").title())


def value_label(value: object, field: str) -> str:
    if value is None:
        return "Not recorded"
    if field.endswith(("cost", "price")):
        return format_money(value) or str(value)
    return str(value)


def go_to(index: int) -> None:
    st.session_state.step = index
    st.session_state.issue_focus = "All activities"


def trend(snapshots: list[dict], selected: int) -> None:
    counts = [len(s["issues"]) for s in snapshots]
    points = [(18 + i * 100, 52 - count * 9) for i, count in enumerate(counts)]
    line = " ".join(f"{x},{y}" for x, y in points)
    circles = "".join(
        f'<circle cx="{x}" cy="{y}" r="{6 if i == selected else 4}" fill="{"#c45145" if i == selected else "#32765f"}"/>'
        f'<text x="{x}" y="{y-12}" text-anchor="middle" font-size="12" fill="#435b50">{counts[i]}</text>'
        for i, (x, y) in enumerate(points)
    )
    st.markdown(
        '<div class="trend"><div class="trend-label"><b>Commonsense errors</b><br>Lower is better</div>'
        f'<svg viewBox="0 0 640 70" role="img" aria-label="Commonsense errors by attempt: {", ".join(map(str, counts))}">'
        f'<polyline points="{line}" fill="none" stroke="#86ac9c" stroke-width="2"/>{circles}</svg></div>',
        unsafe_allow_html=True,
    )


def render_activity(demo: dict, activity: dict, slot: int, before: dict, current: dict,
                    transitions: dict, focus: str, compare: bool) -> None:
    checks = {c["id"]: c for c in demo["checks"]}
    issues = [i for i in current["issues"] if checks[i["check_id"]]["activity"] == slot]
    resolved = [checks[key] for key in sorted(transitions["resolved"]) if checks[key]["activity"] == slot]
    changes = activity_changes(before, activity) if compare else []
    focused = focus != "All activities" and any(c["label"] == focus and c["activity"] == slot for c in demo["checks"])
    classes = "activity" + (" invalid" if issues else " resolved" if resolved else "")
    classes += " changed" if changes else ""
    classes += " focus" if focused else ""
    title = activity_title(activity)
    display = demo["display_names"].get(title, title)
    tags = badge(ACTIVITY_LABELS.get(activity.get("type"), "Activity"), "gray")
    if changes:
        tags += badge("Changed", "blue")
    if issues:
        tags += badge("Violation" if len(issues) == 1 else f"{len(issues)} violations", "red")
        if any(issue["check_id"] in transitions["new"] for issue in issues):
            tags += badge("New issue", "red")
    for check in resolved:
        tags += badge("Resolved: " + check["label"], "green")
    transport = transport_description(activity.get("transports"))
    issue_ids = {issue["check_id"] for issue in issues}
    bad_times = violating_time_fields(activity, issues)
    start = html(activity.get("start_time", "?"))
    end = html(activity.get("end_time", "?"))
    if "start_time" in bad_times:
        start = f'<span class="bad-value">{start}</span>'
    if "end_time" in bad_times:
        end = f'<span class="bad-value">{end}</span>'
    body = f'<div class="{classes}"><div class="time">{start} – {end} · Activity {slot+1}</div>'
    body += f'<div class="activity-top"><div><div>{tags}</div><div class="activity-title" title="{html(title)}">{html(display)}</div></div><div class="cost">{html(format_money(activity.get("cost")) or "")}</div></div>'
    if transport:
        transfer_text = html(transport)
        if "transport_cost" in issue_ids:
            transfer_text += ' ' + badge("Fare flagged by verifier", "red")
        body += f'<div class="transfer">↳ {transfer_text}</div>'
    for issue in issues:
        check = checks[issue["check_id"]]
        body += f'<div class="issue-inline">● {html(check["category"])} · {html(check["label"])}</div>'
    for change in changes:
        body += f'<div class="delta">{html(field_label(change["field"]))}: <del>{html(value_label(change["before"], change["field"]))}</del> → <b>{html(value_label(change["after"], change["field"]))}</b></div>'
    body += '</div>'
    st.markdown(body, unsafe_allow_html=True)


def render_checks(demo: dict, current: dict, transitions: dict) -> None:
    st.markdown("### Constraint checks")
    st.caption("Recorded verifier results. Changes in status follow the selected comparison.")
    active = {i["check_id"]: i["message"] for i in current["issues"]}
    for check in sorted(demo["checks"], key=lambda c: c["id"] not in active):
        key = check["id"]
        state = "New violation" if key in transitions["new"] else "Still violated" if key in transitions["remaining"] else "Violated" if key in active else "Resolved" if key in transitions["resolved"] else "No issue reported"
        color = "red" if key in active else "green" if key in transitions["resolved"] else "gray"
        st.markdown(
            f'<div class="check">{badge(state, color)}<div class="check-title">{html(check["label"])}</div>'
            f'<div class="check-detail">{html(check["category"])} · Activity {check["activity"]+1}<br>{html(check["description"])}</div></div>',
            unsafe_allow_html=True,
        )
        if key in active:
            with st.expander(f"Evidence · {check['label']}"):
                st.write(active[key])
    states = current["verification"]["personal_constraints"] or []
    with st.expander(f"Personal constraints · {sum(s is True for s in states)}/{len(states)} passed"):
        for label, state in zip(demo["personal_labels"], states):
            st.write(f"{'✅' if state is True else '❌' if state is False else '❔'} {label}")
        st.caption("Statuses are saved results. No live verification is performed.")


def main() -> None:
    st.set_page_config(page_title="Repair Replay · Travel Planner", page_icon="🧭", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        demo = load_demo()
    except (OSError, ValueError) as exc:
        st.error(f"Could not load the bundled demonstration: {exc}")
        st.stop()
    snapshots = demo["snapshots"]
    st.session_state.setdefault("step", 0)
    index = st.session_state.step
    current = snapshots[index]
    base_index = baseline_index(snapshots, index)
    base = snapshots[base_index]
    transitions = issue_transitions(base, current) if index else {"resolved": set(), "new": set(), "remaining": set()}
    st.markdown('<div class="eyebrow">Agentic travel planner / recorded experiment</div>', unsafe_allow_html=True)
    st.title("Watch an itinerary get repaired.")
    st.caption("Follow the proposed changes, the checks they fix, and the problems they leave behind.")
    query = demo["query"]
    st.markdown(
        f'<div class="hero"><div class="eyebrow" style="color:#aacabd">THE TRAVEL REQUEST</div><div class="route">{html(query["start_city"])} → {html(query["target_city"])}</div>'
        f'<div class="query">“{html(query["nature_language_en"])}”</div><div class="meta">1 day &nbsp; / &nbsp; 1 traveller &nbsp; / &nbsp; RMB 2,000 budget &nbsp; / &nbsp; Strategy {html(demo["strategy"])} &nbsp; / &nbsp; Saved replay · no API calls</div></div>',
        unsafe_allow_html=True,
    )
    left, right = st.columns([5, 2])
    left.markdown("### Explore the repair attempts")
    right.caption("Seven snapshots · six repair attempts")
    for i, col in enumerate(st.columns(len(snapshots))):
        label = "Initial" if i == 0 else f"Repair {i}"
        col.button(f"{label} · {len(snapshots[i]['issues'])} issues", key=f"step_{i}",
                   type="primary" if i == index else "secondary", use_container_width=True,
                   on_click=go_to, args=(i,))
    trend(snapshots, index)
    prev, title, nxt = st.columns([1, 5, 1])
    prev.button("← Previous", disabled=index == 0, on_click=go_to, args=(max(0, index-1),), use_container_width=True)
    title.markdown(f"### {'Initial itinerary' if index == 0 else f'Repair {index} of {len(snapshots)-1}'}")
    nxt.button("Next →", disabled=index == len(snapshots)-1, on_click=go_to, args=(min(len(snapshots)-1, index+1),), use_container_width=True)
    if index == 0:
        st.caption("The starting itinerary, before any repair. Red markers identify saved verification failures.")
    else:
        status = "Accepted into the working plan" if current["accepted"] else f"Rejected · working plan stays at snapshot {base_index}"
        st.caption(f"{status}. Acceptance and passing verification are separate decisions.")
    if index == len(snapshots)-1:
        st.warning("Repair budget exhausted. Two commonsense violations remain: lunch and dinner still start too late.")
    st.write(STEP_NOTES[index])
    comparison = st.radio("Compare itinerary changes with", ["Input to this repair", "Initial itinerary"], horizontal=True, disabled=index == 0)
    compare_index = 0 if comparison == "Initial itinerary" else base_index
    compare_plan = snapshots[compare_index]["plan"]
    displayed_transitions = issue_transitions(snapshots[compare_index], current) if index else transitions
    changes = plan_changes(compare_plan, current["plan"]) if index else []
    cols = st.columns(4)
    cols[0].metric("Commonsense violations", len(current["issues"]),
                   delta=len(current["issues"])-len(base["issues"]) if index else None, delta_color="inverse")
    cols[1].metric("Resolved in this repair", len(transitions["resolved"]) if index else "—")
    cols[2].metric("New violations", len(transitions["new"]) if index else "—")
    cols[3].metric("Activities changed", len(changes) if index else "—")
    if index and not plan_changes(base["plan"], current["plan"]):
        st.info("No itinerary changes in this attempt. The same violations remain.")
    st.caption("Resolved and new violations compare against the repair input. Changed activities follow the comparison selected above.")
    itinerary_tab, changes_tab, history_tab = st.tabs(["Itinerary & checks", "What changed", "Constraint history"])
    with itinerary_tab:
        itinerary_col, check_col = st.columns([2.1, 1], gap="large")
        with itinerary_col:
            st.markdown("### Day 1 · Nanjing")
            st.caption(f"7 activities · Listed activity + transfer costs: {format_money(listed_cost(current['plan']))}")
            focus = st.selectbox("Locate a constraint in the itinerary", ["All activities"] + [c["label"] for c in demo["checks"]], key="issue_focus")
            st.markdown('<div class="legend">'+badge("Violation", "red")+badge("Changed value", "blue")+badge("Resolved check", "green")+' Highlighted values compare with '+("the initial itinerary" if compare_index == 0 else f"repair {compare_index}")+'.</div>', unsafe_allow_html=True)
            for slot, activity in enumerate(current["plan"][0]["activities"]):
                before = compare_plan[0]["activities"][slot]
                render_activity(demo, activity, slot, before, current, displayed_transitions, focus, index > 0)
        with check_col:
            render_checks(demo, current, displayed_transitions)
    with changes_tab:
        st.markdown("### Changes to the proposed itinerary")
        st.caption(f"Compared with {'the initial itinerary' if compare_index == 0 else f'repair {compare_index}'}. Transfers belong to the activity they lead into.")
        if not index:
            st.info("This is the starting plan. Select a repair attempt to see its changes.")
        elif not changes:
            st.info("No fields changed relative to the selected comparison.")
        for item in changes:
            activity = current["plan"][item["day"]-1]["activities"][item["slot"]]
            st.markdown(f"**Activity {item['slot']+1} · {activity_title(activity)}**")
            st.table([{"Field": field_label(c["field"]), "Before": value_label(c["before"], c["field"]), "After": value_label(c["after"], c["field"])} for c in item["changes"]])
    with history_tab:
        st.markdown("### The full repair trajectory")
        st.caption("Each column is the recorded result of that proposal. ‘Clear’ means the saved verifier did not report this issue.")
        rows = []
        for check in demo["checks"]:
            row = {"Check": check["label"]}
            for i, snapshot in enumerate(snapshots):
                row["Initial" if i == 0 else f"Repair {i}"] = "✕ Violated" if any(issue["check_id"] == check["id"] for issue in snapshot["issues"]) else "✓ Clear"
            rows.append(row)
        st.dataframe(rows, hide_index=True, use_container_width=True)
        st.table([{"Snapshot": "Initial" if i == 0 else f"Repair {i}", "Commonsense errors": len(s["issues"]), "Failed personal checks": sum(v is False for v in s["verification"]["personal_constraints"]), "Decision": "Starting plan" if i == 0 else "Accepted" if s["accepted"] else "Rejected", "All checks passed": "Yes" if s["verification"]["passed"] is True else "No"} for i, s in enumerate(snapshots)])
    st.divider()
    with st.expander("About this recorded example & source evidence"):
        st.write(demo["annotation_note"])
        st.write(f"Query: {demo['query_uid']} · Run: {demo['run_id']} · Stop reason: {demo['stop_reason']}")
        st.code(demo["source"], language=None)
        st.caption("SHA-256 of the original experiment artifact: " + demo["source_sha256"])
        st.json(current, expanded=False)


if __name__ == "__main__":
    main()
