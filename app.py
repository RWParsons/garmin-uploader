"""Streamlit entry point.

Declares the pages explicitly (rather than relying on Streamlit's
filename-based auto-discovery) so the sidebar shows friendly titles -
"Upload workouts" / "Manage workouts" / "How to" - independent of the
underlying file/function names.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from garmin_session import render_garmin_login_sidebar
from upload_workouts_page import render_upload_workouts_page

st.set_page_config(page_title="Claude -> Garmin Workout Planner", layout="wide")

# Rendered once here, above pg.run(), rather than duplicated inside each
# page - see garmin_session.py's docstring for why that also matters for
# not losing an in-flight login when the user switches pages.
render_garmin_login_sidebar()

pg = st.navigation(
    [
        st.Page(render_upload_workouts_page, title="Upload workouts", default=True),
        st.Page("pages/1_Manage_Workouts.py", title="Manage workouts"),
        st.Page("pages/2_How_To.py", title="How to"),
    ]
)
pg.run()
