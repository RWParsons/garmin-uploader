"""Shared Garmin Connect login sidebar.

Rendered once from app.py, above st.navigation()'s pg.run() - not from
individual pages - so it exists once per session instead of being rebuilt
(and re-triggering login state) separately on every page.

The actual network login runs on a plain background thread rather than
inline in the script run. Streamlit cancels the *script's own* thread on
the next rerun (e.g. the one triggered by clicking to a different page),
so a login done inline gets silently abandoned mid-request if the user
navigates away before it finishes - session_state.garmin never gets set,
and it looks like login was "prevented". A detached thread isn't part of
the script run Streamlit is tracking, so it keeps going regardless of
which page is showing, and whichever page is on screen when it finishes
picks up the result on its next rerun.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time

import streamlit as st

from garmin_client import GarminClient


class _LoginTask:
    """Plain (non-session_state) result box a background thread writes to.

    Deliberately not stored inside st.session_state's tracked values beyond
    holding the box itself - the thread only ever mutates these plain
    attributes, never st.session_state directly, since st.session_state
    access requires a script-run context that a plain background thread
    doesn't have.
    """

    def __init__(self):
        self.done = False
        self.client: GarminClient | None = None
        self.error: Exception | None = None


def _login_in_background(gc: GarminClient, mfa_callback, task: _LoginTask) -> None:
    try:
        gc.login(mfa_callback=mfa_callback)
        task.client = gc
    except Exception as e:
        task.error = e
    finally:
        task.done = True


def render_garmin_login_sidebar() -> None:
    st.session_state.setdefault("garmin", None)
    st.session_state.setdefault("garmin_login_task", None)

    with st.sidebar:
        st.header("Settings")
        st.subheader("Garmin Connect")

        task: _LoginTask | None = st.session_state.garmin_login_task

        garmin_email = st.text_input(
            "Garmin email", value=os.getenv("GARMIN_EMAIL", ""), key="garmin_email_input",
            disabled=task is not None and not task.done,
        )
        garmin_password = st.text_input(
            "Garmin password",
            value=os.getenv("GARMIN_PASSWORD", ""),
            type="password",
            key="garmin_password_input",
            disabled=task is not None and not task.done,
        )
        mfa_code = st.text_input(
            "MFA code (only if Garmin asks for one - enter it, then click Log in again)",
            value="",
            key="garmin_mfa_input",
            disabled=task is not None and not task.done,
        )

        if st.session_state.garmin is not None:
            st.success("Logged in to Garmin Connect.")

        login_clicked = st.button(
            "Log in to Garmin",
            key="garmin_login_button",
            disabled=task is not None and not task.done,
        )
        if login_clicked:
            if "garmin_token_dir" not in st.session_state:
                # A per-session token directory - not the shared ~/.garminconnect
                # default - so concurrent users on a public deployment can't end
                # up reusing each other's cached Garmin session.
                st.session_state.garmin_token_dir = tempfile.mkdtemp(prefix="garmin_tokens_")
            gc = GarminClient(garmin_email, garmin_password, token_store=st.session_state.garmin_token_dir)
            new_task = _LoginTask()
            st.session_state.garmin_login_task = new_task
            threading.Thread(
                target=_login_in_background,
                args=(gc, (lambda: mfa_code) if mfa_code else None, new_task),
                daemon=True,
            ).start()
            st.rerun()

        if task is not None:
            if not task.done:
                st.info("Logging in... this keeps running even if you switch pages.")
                time.sleep(0.4)
                st.rerun()
            elif task.error is not None:
                st.error(f"Garmin login failed: {task.error}")
                st.session_state.garmin_login_task = None
            else:
                st.session_state.garmin = task.client
                st.session_state.garmin_login_task = None
                st.rerun()
