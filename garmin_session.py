"""Shared Garmin Connect login sidebar, used by every page.

Streamlit re-runs only the active page's script on navigation (unlike
st.session_state, sidebar UI isn't automatically shared across pages), so
this is factored out and called from the top of every page instead of
living inline in upload_workouts_page.py.
"""
from __future__ import annotations

import os
import tempfile

import streamlit as st

from garmin_client import GarminClient


def render_garmin_login_sidebar() -> None:
    st.session_state.setdefault("garmin", None)

    with st.sidebar:
        st.header("Settings")
        st.subheader("Garmin Connect")
        garmin_email = st.text_input(
            "Garmin email", value=os.getenv("GARMIN_EMAIL", ""), key="garmin_email_input"
        )
        garmin_password = st.text_input(
            "Garmin password",
            value=os.getenv("GARMIN_PASSWORD", ""),
            type="password",
            key="garmin_password_input",
        )
        mfa_code = st.text_input(
            "MFA code (only if Garmin asks for one - enter it, then click Log in again)",
            value="",
            key="garmin_mfa_input",
        )
        if st.session_state.garmin is not None:
            st.success("Logged in to Garmin Connect.")
        if st.button("Log in to Garmin", key="garmin_login_button"):
            try:
                # A per-session token directory - not the shared ~/.garminconnect
                # default - so concurrent users on a public deployment can't end
                # up reusing each other's cached Garmin session.
                if "garmin_token_dir" not in st.session_state:
                    st.session_state.garmin_token_dir = tempfile.mkdtemp(prefix="garmin_tokens_")
                gc = GarminClient(garmin_email, garmin_password, token_store=st.session_state.garmin_token_dir)
                gc.login(mfa_callback=(lambda: mfa_code) if mfa_code else None)
                st.session_state.garmin = gc
                st.success("Logged in to Garmin Connect.")
            except Exception as e:
                st.error(f"Garmin login failed: {e}")
