"""The "Upload workouts" page: import a CSV, review/edit, push to Garmin.

Wrapped in a function (rather than living inline as the entry script) so
app.py can register it with st.navigation() under a custom sidebar title
instead of the name Streamlit would otherwise derive from this file's name.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from csv_import import parse_csv_to_plan
from garmin_session import render_garmin_login_sidebar
from models import WorkoutPlan
from prompt_templates import CSV_TEMPLATE
from workout_ui import (
    render_month_grid,
    render_month_nav,
    render_workout_editor,
    render_workout_summary,
    sport_icon,
)

load_dotenv()


def render_upload_workouts_page() -> None:
    st.title("🏋️ Claude → Garmin workout planner")
    st.caption(
        "Draft cycling / running / stairs / gym workouts with Claude Desktop, "
        "import the CSV, review and edit them, then push straight to Garmin Connect."
    )

    if "plan" not in st.session_state:
        st.session_state.plan: WorkoutPlan | None = None
    if "push_log" not in st.session_state:
        st.session_state.push_log = []

    def push_one(workout) -> None:
        gc = st.session_state.garmin
        if gc is None:
            st.error("Log in to Garmin Connect in the sidebar first.")
            return
        try:
            result = gc.push_workout(workout)
            wid = result.get("workoutId", result) if isinstance(result, dict) else result
            st.success(f"Pushed. Garmin workout ID: {wid}")
            st.session_state.push_log.append((workout.name, workout.sport, "ok"))
        except Exception as e:
            st.error(f"Push failed: {e}")
            st.session_state.push_log.append((workout.name, workout.sport, f"error: {e}"))

    def push_many(workouts) -> None:
        gc = st.session_state.garmin
        if gc is None:
            st.error("Log in to Garmin Connect in the sidebar first.")
            return
        for workout in workouts:
            try:
                gc.push_workout(workout)
                st.session_state.push_log.append((workout.name, workout.sport, "ok"))
            except Exception as e:
                st.session_state.push_log.append((workout.name, workout.sport, f"error: {e}"))
        st.rerun()

    render_garmin_login_sidebar()

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
    # st.file_uploader keeps returning the same file on every rerun (not just
    # the one right after upload), so without this check we'd re-parse it -
    # and rebuild every Workout as a brand-new object - on every single
    # interaction anywhere on the page, silently discarding in-progress edits
    # and breaking anything keyed by object identity (e.g. the calendar
    # checkboxes below, which would immediately appear to "uncheck themselves").
    if uploaded_csv is not None and uploaded_csv.file_id != st.session_state.get("_uploaded_csv_file_id"):
        try:
            st.session_state.plan = parse_csv_to_plan(uploaded_csv)
            st.session_state._uploaded_csv_file_id = uploaded_csv.file_id
            st.success(f"Loaded {len(st.session_state.plan.workouts)} workout(s) from CSV.")
        except Exception as e:
            st.error(f"Couldn't parse that CSV: {e}")

    if st.button("Clear draft"):
        st.session_state.plan = None

    plan = st.session_state.plan
    if plan is None or not plan.workouts:
        st.divider()
        st.info("No draft yet - upload a workout CSV from Claude Desktop above.")
    else:
        # --------------------------------------------------------------------------
        # Step 2: calendar view of dated workouts in this draft
        # --------------------------------------------------------------------------
        st.divider()
        st.subheader("2. Calendar view")

        dated_workouts = [w for w in plan.workouts if w.date]
        if not dated_workouts:
            st.info("No workouts in this draft have a date set yet - nothing to show on the calendar.")
        else:
            st.caption(
                "Click a workout to view its steps and push it, tick the checkbox to select it, "
                "or push/delete everything on the calendar at once."
            )
            if st.button("🚀 Push ALL workouts on the calendar", key="draft_cal_push_all"):
                push_many(dated_workouts)

            if "draft_cal_year" not in st.session_state:
                first_date = min(date.fromisoformat(w.date) for w in dated_workouts)
                st.session_state.draft_cal_year = first_date.year
                st.session_state.draft_cal_month = first_date.month

            year, month = render_month_nav(
                st.session_state.draft_cal_year, st.session_state.draft_cal_month, key_prefix="draft_cal"
            )
            st.session_state.draft_cal_year, st.session_state.draft_cal_month = year, month

            if "draft_cal_selected" not in st.session_state:
                st.session_state.draft_cal_selected: set[int] = set()

            def make_on_select(wid: int):
                def _on_select(checked: bool) -> None:
                    if checked:
                        st.session_state.draft_cal_selected.add(wid)
                    else:
                        st.session_state.draft_cal_selected.discard(wid)

                return _on_select

            events: dict[str, list[dict]] = {}
            for w in dated_workouts:
                # id() rather than a list index - indices shift after a
                # delete, which would otherwise let a stale selection bleed
                # onto whichever workout happens to land on that same index.
                wid = id(w)

                def make_detail(workout=w):
                    def _detail():
                        render_workout_summary(workout)
                        if st.button("🚀 Push to Garmin", key=f"draft_cal_push_{id(workout)}"):
                            push_one(workout)

                    return _detail

                events.setdefault(w.date, []).append(
                    {
                        "label": f"{sport_icon(w.sport)} {w.name}",
                        "render_detail": make_detail(),
                        "selected": wid in st.session_state.draft_cal_selected,
                        "on_select": make_on_select(wid),
                        "event_id": str(wid),
                    }
                )
            render_month_grid(events, year, month, key_prefix="draft_cal")

            selected = [w for w in dated_workouts if id(w) in st.session_state.draft_cal_selected]
            if st.button(
                f"🗑️ Delete selected ({len(selected)})",
                key="draft_cal_delete_selected",
                disabled=not selected,
            ):
                selected_ids = {id(w) for w in selected}
                plan.workouts = [w for w in plan.workouts if id(w) not in selected_ids]
                st.session_state.draft_cal_selected -= selected_ids
                st.rerun()

        # --------------------------------------------------------------------------
        # Step 3: review / edit individual workouts
        # --------------------------------------------------------------------------
        st.divider()
        with st.expander("3. Review / edit individual workouts", expanded=False):
            for workout in plan.workouts:
                icon = sport_icon(workout.sport)
                header = f"{icon} {workout.name}  ·  {workout.sport}  ·  {workout.date or 'unscheduled'}"
                # A plain bordered container, not a nested st.expander - Streamlit
                # discourages nesting expanders (the outer one above already
                # provides the collapse/expand control for this whole section).
                with st.container(border=True):
                    st.markdown(f"**{header}**")
                    # id(workout), not a list index - render_workout_editor's
                    # text_input/date_input only honor value= the first time a
                    # given key is seen, so a positional key here would let a
                    # workout that shifts into a just-deleted one's old slot
                    # silently inherit that deleted workout's stale name/date
                    # (see the identical bug already fixed in render_month_grid).
                    render_workout_editor(workout, key_prefix=f"draft_{id(workout)}")

                    if st.button(f"🚀 Push '{workout.name}' to Garmin", key=f"push_{id(workout)}"):
                        push_one(workout)

            st.divider()
            if st.button("🚀 Push ALL workouts above"):
                push_many(plan.workouts)

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
