"""Streamlit entry point.

Declares the two pages explicitly (rather than relying on Streamlit's
filename-based auto-discovery) so the sidebar shows friendly titles -
"Upload workouts" / "Manage workouts" - independent of the underlying
file/function names.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from upload_workouts_page import render_upload_workouts_page

st.set_page_config(page_title="Claude -> Garmin Workout Planner", layout="wide")

pg = st.navigation(
    [
        st.Page(render_upload_workouts_page, title="Upload workouts", default=True),
        st.Page("pages/1_Manage_Workouts.py", title="Manage workouts"),
    ]
)
pg.run()
