# Streamlit travel planner

The frontend wraps the existing LLM-Modulo agent and shared verification/repair
loop. It offers R0–R4, with R3 selected by default. R4 requires an empirical,
validated matrix pooled from R0–R3 evidence.

## Setup

From the project root, install the project dependencies and set up the ChinaTravel
database and model credentials as described in the main README:

```powershell
python -m pip install -r requirements.txt
python scripts/experiment_setup/setup_project.py
```

Set `CHINATRAVEL_OPENAI_API_KEY`, `CHINATRAVEL_OPENAI_BASE_URL`, and
`CHINATRAVEL_OPENAI_MODEL` in the environment or the project's `.env` file.
To prefill the R4 matrix field, set `CHINATRAVEL_R4_MATRIX` to the path of the
pooled `main_matrix.csv`. The matrix's manifest and source provenance files must
remain available and unchanged; synthetic fixture matrices are rejected.

## Run

From the project root:

```powershell
python -m streamlit run frontend/app.py
```

Each submission creates `frontend/runs/<run-id>/`. It stores `run.json`,
`request.json`, `itinerary.json`, `repair_history.json`, and `attempts.json`, plus
the planner's runtime logs and cache. Repair artifacts are checkpointed as the
shared repair loop runs, so partial attempts remain available if a run fails.
Free-text preferences are passed to the model but are not compiled into formal
personal-constraint rules; the app reports the shared verifier result separately.

## Browse past results

The **Past results** selector at the top of the page loads saved itineraries
locally. It does not invoke the model API. It includes completed frontend runs
from `frontend/runs/`, saved experiment query results under `experiments/`, and
exported benchmark plans and legacy planner outputs under `results/` when a
matching detailed query result is unavailable.
Older experiment outputs may not contain a verification report or repair history;
in that case the UI shows the saved itinerary and indicates that no such details
were stored.
