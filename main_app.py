from pathlib import Path

import streamlit as st

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "mode" not in st.session_state:
    st.session_state.mode = "TEST"

MODES = ["LOCAL", "TEST", "REMOTE"]


def toggle_mode():
    curr_idx = MODES.index(st.session_state.mode)
    st.session_state.mode = MODES[(curr_idx + 1) % len(MODES)]


if st.session_state.logged_in:
    with st.sidebar:
        st.markdown("### Environment")
        st.button(
            f"Switch to {MODES[(MODES.index(st.session_state.mode) + 1) % len(MODES)]}",
            on_click=toggle_mode,
            use_container_width=True,
        )
        st.caption(f"Current: **{st.session_state.mode}**")

ROOT = Path(__file__).resolve().parent

LOGIN = ROOT / "pages" / "login.py"
SURVEYS = ROOT / "pages" / "surveys.py"
PATIENT_ANALYTICS = ROOT / "pages" / "patient_analytics.py"
MEASUREMENTS_EDA = ROOT / "pages" / "eda.py"

login_page = st.Page(LOGIN, title="Login")
surveys_page = st.Page(
    SURVEYS, title="Update Surveys", icon=":material/document_scanner:"
)
patient_analytics_page = st.Page(
    PATIENT_ANALYTICS, title="Patient Analytics", icon=":material/person:"
)
measurements_eda_page = st.Page(
    MEASUREMENTS_EDA, title="Data Analytics", icon=":material/frame_inspect:"
)

if st.session_state.logged_in:
    pg = st.navigation(
        [
            surveys_page,
            # * These pages are removed for now.
            # * Currently the dashboard only supports checking eligibility of patients and updating survey data + patient metadata.
            # patient_analytics_page,
            # measurements_eda_page
        ],
        position="sidebar",
    )
else:
    pg = st.navigation([login_page], position="hidden")

pg.run()
