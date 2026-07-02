"""Streamlit page: view/edit/delete workouts already saved in your Garmin
Connect workout library (whether or not they're scheduled on a date).

Garmin's workout API has no in-place edit - "Update" here means the app
uploads your edited version as a new workout, then deletes the old one, so
the workout ends up with a new ID after every update.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from garmin_client import SPORT_ID_TO_KEY, parse_calendar_workouts, parse_garmin_workout
from garmin_session import render_garmin_login_sidebar
from workout_ui import (
    SPORT_ICON,
    render_month_grid,
    render_month_nav,
    render_workout_editor,
    render_workout_summary,
    sport_icon,
)

st.title("🗂️ Manage Garmin workouts")
st.caption(
    "View workouts already saved in your Garmin Connect workout library, "
    "edit and re-send them, or delete them (one at a time or in bulk)."
)

if "garmin_workouts" not in st.session_state:
    st.session_state.garmin_workouts = None  # list of raw summaries, or None until first fetch
if "garmin_editing" not in st.session_state:
    st.session_state.garmin_editing = {}  # workout_id -> parsed Workout, once loaded for editing
if "garmin_log" not in st.session_state:
    st.session_state.garmin_log = []
if "garmin_cal_year" not in st.session_state:
    today = date.today()
    st.session_state.garmin_cal_year = today.year
    st.session_state.garmin_cal_month = today.month
if "garmin_cal_cache" not in st.session_state:
    st.session_state.garmin_cal_cache = {}  # (year, month) -> parsed calendar workout list
if "garmin_cal_detail_cache" not in st.session_state:
    st.session_state.garmin_cal_detail_cache = {}  # workout_id -> Workout, once fetched via a popover


def _select_key(workout_id) -> str:
    return f"sel_{workout_id}"


render_garmin_login_sidebar()

gc = st.session_state.get("garmin")
if gc is None:
    st.info("Log in to Garmin Connect in the sidebar first.")
    st.stop()


def _refresh():
    try:
        st.session_state.garmin_workouts = gc.list_workouts(start=0, limit=100)
        st.session_state.garmin_editing = {}
    except Exception as e:
        st.error(f"Couldn't fetch workouts: {e}")


tab_calendar, tab_library = st.tabs(["📅 Calendar", "📋 Library"])

with tab_library:
    if st.session_state.garmin_workouts is None:
        _refresh()

    col_refresh, col_count = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh from Garmin"):
            _refresh()
            st.rerun()

    workouts = st.session_state.garmin_workouts or []
    with col_count:
        st.caption(f"{len(workouts)} workout(s) in your library (showing up to 100 most recent).")

    if not workouts:
        st.info("No workouts found in your Garmin Connect workout library.")
    else:
        st.caption("Check the boxes next to workouts below, or use Select all, then delete in bulk:")

        # Batch selection controls must run - and write any st.session_state[key]
        # changes - before the per-workout loop below creates the checkboxes that
        # own those same keys. Streamlit raises if you write to a widget's session
        # state key after that widget has already been instantiated in the same
        # script run, even if a st.rerun() is queued right after.
        selected_ids = [
            w.get("workoutId") for w in workouts if st.session_state.get(_select_key(w.get("workoutId")))
        ]
        n_selected = len(selected_ids)
        select_all_col, clear_col, delete_col, count_col = st.columns([1, 1, 1, 2])
        with select_all_col:
            if st.button(f"☑️ Select all ({len(workouts)})"):
                for w in workouts:
                    st.session_state[_select_key(w.get("workoutId"))] = True
                st.rerun()
        with clear_col:
            if st.button("Clear selection"):
                for w in workouts:
                    st.session_state[_select_key(w.get("workoutId"))] = False
                st.rerun()
        with delete_col:
            delete_selected_clicked = st.button(
                f"🗑️ Delete selected ({n_selected})", type="primary", disabled=n_selected == 0
            )
        with count_col:
            if n_selected:
                st.caption(f"{n_selected} selected")

        if delete_selected_clicked:
            remaining = list(workouts)
            for summary in workouts:
                workout_id = summary.get("workoutId")
                if workout_id not in selected_ids:
                    continue
                name = summary.get("workoutName") or "Untitled workout"
                try:
                    gc.delete_workout(workout_id)
                    st.session_state.garmin_log.append((name, "delete", "ok"))
                    remaining = [w for w in remaining if w.get("workoutId") != workout_id]
                    st.session_state.garmin_editing.pop(workout_id, None)
                    st.session_state.pop(_select_key(workout_id), None)
                except Exception as e:
                    st.session_state.garmin_log.append((name, "delete", f"error: {e}"))
            st.session_state.garmin_workouts = remaining
            st.rerun()

        st.divider()

        for summary in workouts:
            workout_id = summary.get("workoutId")
            name = summary.get("workoutName") or "Untitled workout"
            sport = SPORT_ID_TO_KEY.get((summary.get("sportType") or {}).get("sportTypeId"), "")
            icon = SPORT_ICON.get(sport, "")
            updated = summary.get("updatedDate") or summary.get("createdDate") or ""

            header_col, select_col = st.columns([0.92, 0.08])
            with select_col:
                # No `value=` here on purpose - once a widget with this key exists,
                # Streamlit treats st.session_state[key] as the source of truth and
                # silently ignores `value=` on reruns. "Select all" / "Clear
                # selection" below write st.session_state[key] directly instead of
                # keeping a separate mirrored set, which would just get overwritten
                # back by this checkbox on the very next rerun.
                st.checkbox("select", key=_select_key(workout_id), label_visibility="collapsed")

            with header_col:
                with st.expander(f"{icon} {name}  ·  {sport}  ·  updated {updated}".strip(), expanded=False):
                    if workout_id not in st.session_state.garmin_editing:
                        if st.button("✏️ Load for editing", key=f"load_{workout_id}"):
                            try:
                                detail = gc.get_workout(workout_id)
                                st.session_state.garmin_editing[workout_id] = parse_garmin_workout(detail)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Couldn't load workout detail: {e}")
                    else:
                        workout = st.session_state.garmin_editing[workout_id]
                        render_workout_editor(workout, key_prefix=f"garmin_{workout_id}")

                        update_col, delete_col = st.columns(2)
                        with update_col:
                            if st.button("💾 Update on Garmin (replace)", key=f"update_{workout_id}"):
                                try:
                                    result = gc.update_workout(workout_id, workout)
                                    new_id = result.get("workoutId") if isinstance(result, dict) else None
                                    st.success(f"Updated. New Garmin workout ID: {new_id}")
                                    st.session_state.garmin_log.append((name, "update", "ok"))
                                    _refresh()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Update failed: {e}")
                                    st.session_state.garmin_log.append((name, "update", f"error: {e}"))
                        with delete_col:
                            if st.button("🗑️ Delete", key=f"delete_{workout_id}"):
                                try:
                                    gc.delete_workout(workout_id)
                                    st.success("Deleted.")
                                    st.session_state.garmin_log.append((name, "delete", "ok"))
                                    st.session_state.garmin_workouts = [
                                        w for w in workouts if w.get("workoutId") != workout_id
                                    ]
                                    st.session_state.garmin_editing.pop(workout_id, None)
                                    st.session_state.pop(_select_key(workout_id), None)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Delete failed: {e}")
                                    st.session_state.garmin_log.append((name, "delete", f"error: {e}"))

        if st.session_state.garmin_log:
            st.divider()
            st.subheader("Action log (this session)")
            st.table(pd.DataFrame(st.session_state.garmin_log, columns=["workout", "action", "result"]))

with tab_calendar:
    st.caption("What's actually scheduled on your Garmin Connect calendar for the selected month.")

    year, month = render_month_nav(
        st.session_state.garmin_cal_year, st.session_state.garmin_cal_month, key_prefix="garmin_cal"
    )
    st.session_state.garmin_cal_year, st.session_state.garmin_cal_month = year, month

    cache_key = (year, month)
    if cache_key not in st.session_state.garmin_cal_cache:
        try:
            raw = gc.get_scheduled_workouts(year, month)
            st.session_state.garmin_cal_cache[cache_key] = (raw, parse_calendar_workouts(raw))
        except Exception as e:
            st.error(f"Couldn't fetch the Garmin calendar: {e}")
            st.session_state.garmin_cal_cache[cache_key] = ({}, [])

    raw, scheduled = st.session_state.garmin_cal_cache[cache_key]

    def _make_detail(item: dict):
        def _detail():
            if not item["fetchable"]:
                st.caption(
                    "Steps aren't available for Garmin Coach / adaptive-training "
                    "workouts from this app - they're not stored in the regular "
                    "workout library this app can fetch full detail from."
                )
                return
            detail_cache = st.session_state.garmin_cal_detail_cache
            wid = item["workout_id"]
            if wid not in detail_cache:
                # Only reached while this event's popover is actually open (see
                # render_month_grid's .open check), so this fetch runs once,
                # the moment the user opens it - not for every event up front.
                with st.spinner("Loading workout steps..."):
                    try:
                        detail_cache[wid] = parse_garmin_workout(gc.get_workout(wid))
                    except Exception as e:
                        st.error(f"Couldn't load workout detail: {e}")
                        return
            render_workout_summary(detail_cache[wid])

        return _detail

    events: dict[str, list[dict]] = {}
    for item in scheduled:
        if not item.get("date"):
            continue
        events.setdefault(item["date"], []).append(
            {"label": f"{sport_icon(item.get('sport'))} {item['title']}", "render_detail": _make_detail(item)}
        )

    render_month_grid(events, year, month, key_prefix="garmin_cal", lazy=True)

    if not scheduled:
        st.caption("No workouts scheduled on Garmin's calendar for this month.")

    all_items = raw.get("calendarItems") or raw.get("items") or []
    item_types = sorted({str((it.get("itemType") or it.get("type") or "?")) for it in all_items})
    with st.expander("🔍 Show raw Garmin calendar payload (debug)"):
        st.caption(
            "If a workout (e.g. one assigned by Garmin Coach) isn't showing up above, it's "
            "likely because its itemType isn't 'workout', or it doesn't carry a workoutId/id "
            "field the way manually-scheduled workouts do - parse_calendar_workouts() in "
            "garmin_client.py only recognizes those. Item types seen this month: "
            f"{', '.join(item_types) if item_types else '(none)'}. Compare that against what "
            "you expect to see, and check the full JSON below for the field names actually "
            "used on the missing item, then update parse_calendar_workouts() to match."
        )
        st.json(raw)
