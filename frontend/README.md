# Recorded repair walkthrough

The frontend replays one saved experiment locally. It replaces the live planner:
there is no prompt submission, API client, credential loading, or live verification.

From the repository root:

```powershell
python -m pip install "streamlit>=1.40,<2"
python -m streamlit run frontend/app.py
```

Open the local URL printed by Streamlit (usually http://localhost:8501).
The demo needs only Streamlit and the bundled JSON file; no travel database,
model credentials, or running backend is required.

## Walkthrough

- Select **Initial plan**, any **Repair 1–6**, or use **Previous / Next**.
- Red labels locate saved violations. Blue outlines and before/after values show
  changed activities, including their inbound transfers. Green badges identify
  previously reported issues that are no longer reported.
- Compare a proposal with **Input to this repair** or **Initial itinerary**.
  Input means the last accepted plan, skipping rejected proposals.
- Use **Locate a constraint** to outline the associated activity in amber.
- **What changed** lists all changed fields. **Constraint history** shows the
  checks across all seven snapshots. Evidence expanders preserve verifier messages.
- The final attempt explicitly reports budget exhaustion and unresolved issues.

The example is a one-day solo trip from Guangzhou to Nanjing, budget RMB 2,000,
from `experiments/subset_train-r2`, query `e20241028160445320665`, strategy R2.
Its commonsense error counts are **4 → 3 → 4 → 3 → 2 → 2 → 2**.
All five personal checks pass throughout; overall verification never passes.
Repairs 5 and 6 make no itinerary changes.

## Evidence and scope

`demo_data/nanjing_r2.json` is a compact, frozen copy of the original query, raw
initial/candidate itineraries, saved verifier results, and acceptance decisions.
It retains the original artifact path and SHA-256. It is independent of experiment
files changing during other work. No synthetic itineraries or repairs are added.

English check names, shortened display names, and issue-to-activity mappings are
manually curated for this example. Original place names remain in tooltips and
source evidence. The attraction-opening-hours check retains the same identity
when the venue changes, so replacing a museum with a still-invalid palace visit
does not incorrectly count as a resolution. A clear status means an issue is not
reported by the saved verifier; it is not an independently rerun assessment.

Activity slots remain stable in this example. Adding a case that inserts,
removes, or reorders activities requires explicit alignment and reviewed mappings.
`replay.py` owns comparisons; `app.py` owns presentation. Existing planner/history
helpers remain available to other code but are not imported by the replay UI.

Run focused checks with:

```powershell
python -m pytest tests/test_frontend_replay.py tests/test_frontend_replay_app.py
```
