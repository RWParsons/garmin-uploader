"""Streamlit app: import Claude-drafted workouts from CSV, review/edit them, push to Garmin.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from csv_import import parse_csv_to_plan
from garmin_client import GarminClient, build_raw_payload
from models import CardioStep, Exercise, WorkoutPlan
from prompt_templates import CSV_TEMPLATE

load_dotenv()

STEP_ICON = {
    "warmup": "🟠",
    "cooldown": "🔵",
    "interval": "🟢",
    "recovery": "⚪",
    "rest": "⏸️",
}


def _format_duration(step: CardioStep) -> str:
    if step.duration_type == "time":
        if step.duration_value is None:
            return "—"
        minutes, seconds = divmod(int(step.duration_value), 60)
        return f"{minutes}:{seconds:02d}"
    if step.duration_type == "distance":
        if step.duration_value is None:
            return "—"
        meters = step.duration_value
        return f"{meters / 1000:.2f} km" if meters >= 1000 else f"{meters:.0f} m"
    return "Lap button"


def _format_pace(seconds_per_km: float) -> str:
    minutes, seconds = divmod(int(round(seconds_per_km)), 60)
    return f"{minutes}:{seconds:02d}/km"


def _format_target(step: CardioStep) -> Optional[str]:
    low, high = step.target_low, step.target_high
    if step.target_type == "none" or (low is None and high is None):
        return None
    if step.target_type == "pace":
        if low is not None and high is not None:
            # Faster pace = fewer seconds/km, so the low target_value is the faster end.
            return f"Pace {_format_pace(low)}–{_format_pace(high)}"
        return f"Pace {_format_pace(low if low is not None else high)}"
    unit = {"power": "W", "heart_rate": "bpm", "cadence": ""}[step.target_type]
    label = {"power": "Power", "heart_rate": "HR", "cadence": "Cadence"}[step.target_type]
    if low is not None and high is not None:
        return f"{label} {int(low)}–{int(high)}{(' ' + unit) if unit else ''}"
    val = low if low is not None else high
    return f"{label} {int(val)}{(' ' + unit) if unit else ''}"


def render_step_blocks(steps: list[CardioStep]) -> None:
    """Render steps as nested blocks, similar to how Garmin Connect displays a workout."""
    for step in steps:
        if step.type == "repeat":
            with st.container(border=True):
                st.markdown(f"**🔁 Repeat {step.repeat_count or 1}×**")
                render_step_blocks(step.repeat_steps or [])
            continue

        line = f"{STEP_ICON.get(step.type, '•')} **{step.type.replace('_', ' ').title()}** — {_format_duration(step)}"
        target = _format_target(step)
        if target:
            line += f" @ {target}"
        st.markdown(line)
        if step.note:
            st.caption(step.note)

st.set_page_config(page_title="Claude -> Garmin Workout Planner", layout="wide")
st.title("🏋️ Claude → Garmin workout planner")
st.caption(
    "Draft cycling / running / stairs / gym workouts with Claude Desktop, "
    "import the CSV, review and edit them, then push straight to Garmin Connect."
)

if "plan" not in st.session_state:
    st.session_state.plan: WorkoutPlan | None = None
if "garmin" not in st.session_state:
    st.session_state.garmin: GarminClient | None = None
if "push_log" not in st.session_state:
    st.session_state.push_log = []

# --------------------------------------------------------------------------
# Sidebar: Garmin credentials
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")
    st.subheader("Garmin Connect")
    garmin_email = st.text_input("Garmin email", value=os.getenv("GARMIN_EMAIL", ""))
    garmin_password = st.text_input(
        "Garmin password", value=os.getenv("GARMIN_PASSWORD", ""), type="password"
    )
    mfa_code = st.text_input(
        "MFA code (only if Garmin asks for one - enter it, then click Log in again)",
        value="",
    )
    if st.session_state.garmin is not None:
        st.success("Logged in to Garmin Connect.")
    if st.button("Log in to Garmin"):
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

# --------------------------------------------------------------------------
# Step 1: import the workout CSV
# --------------------------------------------------------------------------
st.subheader("1. Upload the workout(s) CSV")

with st.expander("📥 Need a starting template instead?", expanded=False):
    st.caption(
        "A small example CSV showing the expected columns - download it, "
        "edit by hand, or hand it to Claude Desktop as a format reference."
    )
    st.download_button(
        "⬇️ Download CSV template",
        data=CSV_TEMPLATE,
        file_name="workout_template.csv",
        mime="text/csv",
    )
    st.code(CSV_TEMPLATE, language="text")

uploaded_csv = st.file_uploader("Upload workout CSV", type="csv")
if uploaded_csv is not None:
    try:
        st.session_state.plan = parse_csv_to_plan(uploaded_csv)
        st.success(f"Loaded {len(st.session_state.plan.workouts)} workout(s) from CSV.")
    except Exception as e:
        st.error(f"Couldn't parse that CSV: {e}")

if st.button("Clear draft"):
    st.session_state.plan = None

# --------------------------------------------------------------------------
# Step 2: review / edit
# --------------------------------------------------------------------------
st.divider()
st.subheader("2. Review / edit the draft")

plan = st.session_state.plan
if plan is None or not plan.workouts:
    st.info("No draft yet - upload a workout CSV from Claude Desktop above.")
else:
    for idx, workout in enumerate(plan.workouts):
        header = f"{workout.name}  ·  {workout.sport}  ·  {workout.date or 'unscheduled'}"
        with st.expander(header, expanded=True):
            new_name = st.text_input("Name", value=workout.name, key=f"name_{idx}")
            new_date = st.date_input(
                "Date to schedule on Garmin",
                value=date.fromisoformat(workout.date) if workout.date else date.today(),
                key=f"date_{idx}",
            )
            workout.name = new_name
            workout.date = new_date.isoformat()

            if workout.sport == "strength":
                if workout.exercises:
                    df = pd.DataFrame([e.model_dump() for e in workout.exercises])
                    edited = st.data_editor(df, num_rows="dynamic", key=f"ex_{idx}")
                    workout.exercises = [Exercise(**row) for row in edited.to_dict("records")]
                else:
                    st.warning("Claude didn't return any exercises for this workout.")
            else:
                if workout.steps:
                    def flatten(steps):
                        rows = []
                        for s in steps:
                            rows.append(
                                {
                                    "type": s.type,
                                    "duration_type": s.duration_type,
                                    "duration_value": s.duration_value,
                                    "target_type": s.target_type,
                                    "target_low": s.target_low,
                                    "target_high": s.target_high,
                                    "note": s.note,
                                }
                            )
                            if s.repeat_steps:
                                rows.extend(flatten(s.repeat_steps))
                        return rows

                    df = pd.DataFrame(flatten(workout.steps))
                    st.dataframe(df, use_container_width=True)
                    st.caption(
                        "Repeat-group steps are flattened here for readability. "
                        "For structural changes (more/fewer intervals etc.), it's "
                        "easiest to ask Claude to redraft rather than hand-edit."
                    )

                    st.markdown("**As it will appear in Garmin Connect:**")
                    render_step_blocks(workout.steps)
                else:
                    st.warning("Claude didn't return any steps for this workout.")

            if workout.notes:
                st.caption(workout.notes)

            with st.expander("🔍 Show raw Garmin payload (debug)"):
                st.caption(
                    "This is exactly what would be sent to Garmin Connect. "
                    "Step/target type IDs are best-effort reverse-engineered "
                    "values - check this if a pushed workout looks wrong on "
                    "your watch. See README.md for how to verify them."
                )
                st.json(build_raw_payload(workout))

            if st.button(f"🚀 Push '{workout.name}' to Garmin", key=f"push_{idx}"):
                gc = st.session_state.garmin
                if gc is None:
                    st.error("Log in to Garmin Connect in the sidebar first.")
                else:
                    try:
                        result = gc.push_workout(workout)
                        wid = result.get("workoutId", result) if isinstance(result, dict) else result
                        st.success(f"Pushed. Garmin workout ID: {wid}")
                        st.session_state.push_log.append((workout.name, workout.sport, "ok"))
                    except Exception as e:
                        st.error(f"Push failed: {e}")
                        st.session_state.push_log.append((workout.name, workout.sport, f"error: {e}"))

    st.divider()
    if st.button("🚀 Push ALL workouts above"):
        gc = st.session_state.garmin
        if gc is None:
            st.error("Log in to Garmin Connect in the sidebar first.")
        else:
            for workout in plan.workouts:
                try:
                    gc.push_workout(workout)
                    st.session_state.push_log.append((workout.name, workout.sport, "ok"))
                except Exception as e:
                    st.session_state.push_log.append((workout.name, workout.sport, f"error: {e}"))
            st.rerun()

    st.download_button(
        "⬇️ Download draft as JSON",
        data=plan.model_dump_json(indent=2),
        file_name="workout_plan.json",
        mime="application/json",
    )

if st.session_state.push_log:
    st.divider()
    st.subheader("Push log (this session)")
    st.table(pd.DataFrame(st.session_state.push_log, columns=["workout", "sport", "result"]))
