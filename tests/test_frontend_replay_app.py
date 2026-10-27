import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "frontend" / "app.py"


def test_navigation_comparison_and_constraint_focus_without_planner_imports():
    app = AppTest.from_file(str(APP)).run(timeout=20)
    assert not app.exception
    assert app.session_state["step"] == 0
    assert not app.text_input and not app.text_area
    assert "frontend.planner" not in sys.modules
    assert "chinatravel.agent.llms" not in sys.modules
    assert app.button[7].disabled
    for index in range(1, 7):
        app.button(key=f"step_{index}").click().run()
        assert not app.exception
        assert app.session_state["step"] == index
        assert app.metric[0].value == str([4, 3, 4, 3, 2, 2, 2][index])
    assert app.button[8].disabled
    assert any("Repair budget exhausted" in item.value for item in app.warning)
    assert any("No itinerary changes" in item.value for item in app.info)
    app.radio[0].set_value("Initial itinerary").run()
    assert not app.exception
    assert int(app.metric[3].value) > 0
    app.selectbox[0].select("Lunch starts by 14:00").run()
    assert any('activity invalid focus' in item.value for item in app.markdown)
    app.button(key="step_2").click().run()
    assert app.selectbox[0].value == "All activities"
    app.button[7].click().run()
    assert app.session_state["step"] == 1
