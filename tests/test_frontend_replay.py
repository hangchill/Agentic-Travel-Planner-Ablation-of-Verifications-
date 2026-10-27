import hashlib
import json
from pathlib import Path

from frontend.replay import (
    activity_changes, baseline_index, issue_transitions, listed_cost, load_demo, plan_changes,
    violating_time_fields,
)


def test_bundled_evidence_matches_saved_experiment():
    demo = load_demo()
    source = Path(__file__).resolve().parents[1] / demo["source"]
    original = json.loads(source.read_text(encoding="utf-8"))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == demo["source_sha256"]
    assert len(demo["snapshots"]) == len(original["repair_history"]) == 7
    for snapshot, entry in zip(demo["snapshots"], original["repair_history"]):
        assert snapshot["plan"] == entry.get("candidate_plan", original["initial_raw_plan"])
        assert snapshot["accepted"] == entry["accepted"]
        assert [i["message"] for i in snapshot["issues"]] == entry["verification"]["commonsense_errors"]
        for key, value in snapshot["verification"].items():
            assert value == entry["verification"].get(key)


def test_replay_preserves_regressions_resolutions_and_stalled_attempts():
    snapshots = load_demo()["snapshots"]
    assert [len(s["issues"]) for s in snapshots] == [4, 3, 4, 3, 2, 2, 2]
    # Changing venues still violates the SAME opening-hours rule.
    transitions = issue_transitions(snapshots[0], snapshots[1])
    assert "attraction_hours" in transitions["remaining"]
    assert transitions["resolved"] == {"restaurant_hours"}
    assert issue_transitions(snapshots[1], snapshots[2])["new"] == {"transport_cost"}
    assert issue_transitions(snapshots[3], snapshots[4])["resolved"] == {"attraction_hours"}
    assert not plan_changes(snapshots[4]["plan"], snapshots[5]["plan"])
    assert not plan_changes(snapshots[5]["plan"], snapshots[6]["plan"])
    assert all(s["verification"]["passed"] is False for s in snapshots)


def test_rejected_proposal_does_not_become_comparison_baseline():
    snapshots = [{"accepted": True}, {"accepted": True}, {"accepted": False}, {"accepted": False}]
    assert baseline_index(snapshots, 0) == 0
    assert baseline_index(snapshots, 3) == 1


def test_field_diff_includes_transfers_and_cost_does_not_count_unit_price_twice():
    changes = activity_changes({"transports": {"cost": 3}}, {"transports": {"cost": 2}})
    assert changes == [{"field": "transports.cost", "before": 3, "after": 2}]
    assert listed_cost([{"activities": [{"price": 90, "cost": 180, "transports": {"cost": 3}}]}]) == 183


def test_only_invalid_endpoint_is_highlighted_for_palace_opening_hours():
    snapshot = load_demo()["snapshots"][1]
    palace = snapshot["plan"][0]["activities"][3]
    issues = [i for i in snapshot["issues"] if i["check_id"] == "attraction_hours"]
    assert palace["start_time"] == "17:00"  # Valid arrival, before 18:00 closing.
    assert violating_time_fields(palace, issues) == {"end_time"}
