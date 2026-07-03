"""Smoke tests for the Streamlit Results page (app.py).

Run with either:
    python3 tests/test_results_page.py
    pytest tests/test_results_page.py

Notes on the harness:
- app.py uses st.navigation with callable pages, which AppTest.switch_page
  cannot address (it only accepts file paths). Callable pages are identified
  by md5(url_path), so navigation is done by setting at._page_hash directly.
- AppTest cannot re-run a tree that contains a rendered single-select
  st.segmented_control (its ButtonGroup state serializer iterates the string
  value). Each scenario therefore uses a fresh AppTest, pre-seeds
  session_state, and runs exactly once on the Results page.
"""
import os

from streamlit.testing.v1 import AppTest
from streamlit.util import calc_md5

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
RESULTS_PAGE_HASH = calc_md5("results")


def render_results(seed=None):
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["euler_logged_in"] = True
    if seed:
        for k, v in seed.items():
            at.session_state[k] = v
    at._page_hash = RESULTS_PAGE_HASH
    at.run()
    assert not at.exception, f"results page: {[e.value for e in at.exception]}"
    return at


def test_login_gate():
    """Without a session login (and no auto-login), only the sign-in screen shows."""
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["euler_logged_in"] = False
    at._page_hash = RESULTS_PAGE_HASH
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [b.label for b in at.button]
    assert "Connect" in labels and "Continue offline" in labels, labels
    assert not [s for s in at.selectbox if s.key == "results_sync_scope"], \
        "app content leaked past the login gate"


def job_options():
    at = render_results()
    sbs = [s for s in at.selectbox if s.key == "results_single_job"]
    assert sbs, "job selectbox missing"
    return sbs[0].options


def test_single_job_view_loads():
    at = render_results()
    assert [s for s in at.selectbox if s.key == "results_single_job"]
    scopes = [s for s in at.selectbox if s.key == "results_sync_scope"][0]
    assert scopes.options == [
        "Latest jobs only", "Selected jobs only",
        "Current FLC/source only", "Full results directory",
    ]
    # delete-stale must be hidden outside Full scope
    assert not any(c.key == "results_sync_delete_stale" for c in at.checkbox)
    # prev/next buttons exist
    assert any(b.key == "results_job_prev" for b in at.button)
    assert any(b.key == "results_job_next" for b in at.button)


def test_each_panel_renders():
    opts = job_options()
    for panel in ("Force-Disp.", "Energy", "Strain Path", "V&H",
                  "Forming Limits", "Diagnostics"):
        render_results(seed={
            "results_single_job": opts[0],
            "results_panel_single": panel,
        })


def test_job_switch():
    opts = job_options()
    if len(opts) > 1:
        render_results(seed={"results_single_job": opts[1]})


def test_job_table_toggle():
    opts = job_options()
    # Force-Disp. panel renders no dataframe of its own, so the only dataframe
    # on the page must be the job table (AppTest exposes no key on Dataframe).
    at = render_results(seed={
        "results_single_job": opts[0],
        "results_panel_single": "Force-Disp.",
        "results_job_table_toggle": True,
    })
    assert len(at.dataframe) >= 1, "job table not rendered when toggled on"


def test_flc_view():
    at = render_results(seed={"results_view_mode": "FLC"})
    ms = [m for m in at.multiselect if m.key == "results_flc_sources_empty_default"]
    assert ms, "FLC source multiselect missing"
    if ms[0].options:
        at = render_results(seed={
            "results_view_mode": "FLC",
            "results_flc_sources_empty_default": [ms[0].options[0]],
            "results_flc_show_paths": True,
        })
        dl = [b for b in at.button
              if "Download Post-processing plots" in (b.label or "")]
        keys = [b.key for b in dl]
        assert len(keys) == len(set(keys)), f"duplicate download keys: {keys}"


def test_full_scope_shows_delete_stale():
    at = render_results(seed={"results_sync_scope": "Full results directory"})
    assert any(c.key == "results_sync_delete_stale" for c in at.checkbox)


if __name__ == "__main__":
    test_login_gate()
    print("0. login gate OK")
    test_single_job_view_loads()
    print("1. single job view OK")
    test_each_panel_renders()
    print("2. all panels OK")
    test_job_switch()
    print("3. job switch OK")
    test_job_table_toggle()
    print("4. job table OK")
    test_flc_view()
    print("5. FLC view OK")
    test_full_scope_shows_delete_stale()
    print("6. full-scope sync UI OK")
    print("SMOKE OK")
