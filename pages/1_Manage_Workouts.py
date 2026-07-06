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
    calendar_checkbox_key,
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
if "garmin_cal_selected" not in st.session_state:
    st.session_state.garmin_cal_selected = set()  # schedule_ids currently checked on the calendar
if "garmin_delete_all_future_open" not in st.session_state:
    st.session_state.garmin_delete_all_future_open = False
if "garmin_delete_all_future_preview" not in st.session_state:
    st.session_state.garmin_delete_all_future_preview = None  # list of items, fetched once per dialog open


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


def _find_all_future_scheduled(max_months: int = 12, stop_after_empty: int = 6) -> list[dict]:
    """Scan forward month by month from today collecting every scheduled
    workout dated today or later. Garmin Coach plans can generate workouts
    indefinitely, so this is bounded rather than scanning forever: it stops
    after `max_months`, or after `stop_after_empty` consecutive months with
    no qualifying items. stop_after_empty deliberately isn't small - e.g. a
    manually-scheduled item a few months out with nothing in between is a
    perfectly normal gap, and stopping too eagerly would silently leave
    real future workouts behind despite the button claiming "ALL". Reuses
    garmin_cal_cache for months already fetched (e.g. the one currently on
    screen) instead of re-hitting the API for them.
    """
    today = date.today()
    found: list[dict] = []
    empty_streak = 0
    year, month = today.year, today.month
    for _ in range(max_months):
        cache_key = (year, month)
        if cache_key in st.session_state.garmin_cal_cache:
            _, items = st.session_state.garmin_cal_cache[cache_key]
        else:
            try:
                raw = gc.get_scheduled_workouts(year, month)
                items = parse_calendar_workouts(raw)
                st.session_state.garmin_cal_cache[cache_key] = (raw, items)
            except Exception as e:
                st.error(f"Couldn't fetch {year}-{month:02d} while scanning ahead: {e}")
                break

        future_items = [
            item
            for item in items
            if item.get("date") and item.get("schedule_id") is not None and item["date"] >= today.isoformat()
        ]
        found.extend(future_items)
        empty_streak = empty_streak + 1 if not future_items else 0
        if empty_streak >= stop_after_empty:
            break

        month += 1
        if month > 12:
            month, year = 1, year + 1

    return found


@st.dialog("Delete ALL future workouts?")
def _confirm_delete_all_future_dialog():
    if st.session_state.garmin_delete_all_future_preview is None:
        with st.spinner("Scanning your calendar for future workouts..."):
            st.session_state.garmin_delete_all_future_preview = _find_all_future_scheduled()

    items = st.session_state.garmin_delete_all_future_preview
    if not items:
        st.info("No future workouts found on your calendar.")
    else:
        st.warning(
            f"This will remove **{len(items)}** workout(s) from your Garmin calendar, from "
            "today onward. This only unschedules them - each workout stays in your Garmin "
            "workout library and can be rescheduled later - but this can't be undone in bulk "
            "from here."
        )
        preview_lines = [f"- {item['date']}: {item['title']}" for item in items[:15]]
        if len(items) > 15:
            preview_lines.append(f"- ...and {len(items) - 15} more")
        st.markdown("\n".join(preview_lines))

    st.caption("Scans up to 12 months ahead - anything scheduled further out than that won't be found.")

    cancel_col, confirm_col = st.columns(2)
    with cancel_col:
        if st.button("Cancel", key="garmin_delete_all_future_cancel"):
            st.session_state.garmin_delete_all_future_open = False
            st.session_state.garmin_delete_all_future_preview = None
            st.rerun()
    with confirm_col:
        if st.button(
            f"🗑️ Yes, delete {len(items)}",
            key="garmin_delete_all_future_confirm",
            type="primary",
            disabled=not items,
        ):
            affected_months = set()
            for item in items:
                try:
                    gc.unschedule_workout(item["schedule_id"])
                    st.session_state.garmin_log.append((item["title"], "unschedule", "ok"))
                except Exception as e:
                    st.session_state.garmin_log.append((item["title"], "unschedule", f"error: {e}"))
                item_date = date.fromisoformat(item["date"])
                affected_months.add((item_date.year, item_date.month))
                st.session_state.garmin_cal_selected.discard(item["schedule_id"])
            for cache_key in affected_months:
                st.session_state.garmin_cal_cache.pop(cache_key, None)
            st.session_state.garmin_delete_all_future_open = False
            st.session_state.garmin_delete_all_future_preview = None
            st.rerun()


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
    refresh_col, delete_all_col = st.columns([1, 1.6])
    with refresh_col:
        if st.button("🔄 Refresh from Garmin", key="garmin_cal_refresh"):
            st.session_state.garmin_cal_cache.pop(cache_key, None)
            st.rerun()
    with delete_all_col:
        if st.button("🗑️ Delete ALL future workouts", key="garmin_delete_all_future_btn"):
            st.session_state.garmin_delete_all_future_open = True
            st.session_state.garmin_delete_all_future_preview = None

    if st.session_state.garmin_delete_all_future_open:
        _confirm_delete_all_future_dialog()

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

    def make_on_select(schedule_id):
        def _on_select(checked: bool) -> None:
            if checked:
                st.session_state.garmin_cal_selected.add(schedule_id)
            else:
                st.session_state.garmin_cal_selected.discard(schedule_id)

        return _on_select

    # Garmin's calendar API for one month also includes a handful of items
    # from the tail/head of the adjacent month (the padding days it uses to
    # fill out a full calendar week) - the grid below already only ever
    # renders days that belong to (year, month), so those spill-over items
    # never get a visible checkbox, but without this date check they'd still
    # silently count towards "select all" / "Delete selected", letting a
    # workout the user never even saw get selected and unscheduled.
    selectable = [
        item
        for item in scheduled
        if item.get("date")
        and item.get("schedule_id") is not None
        and date.fromisoformat(item["date"]).year == year
        and date.fromisoformat(item["date"]).month == month
    ]

    # Selection is scoped to whichever month is currently displayed - drop
    # anything left over from a different month (or a month whose fetch
    # failed) every render, so "Delete selected"/"Select all"/the checkboxes
    # can never drift out of sync with what's actually on screen after
    # navigating between months.
    st.session_state.garmin_cal_selected &= {item["schedule_id"] for item in selectable}

    if scheduled:
        selected = [item for item in selectable if item["schedule_id"] in st.session_state.garmin_cal_selected]

        # Select all / Clear selection must run - and write any
        # st.session_state[key] changes - before render_month_grid below
        # instantiates the checkboxes that own those same keys (see the
        # identical ordering constraint on the Library tab above). Updating
        # garmin_cal_selected alone isn't enough to make the boxes
        # *visually* update: a checkbox only re-reads value= the first time
        # its key is ever seen, so it needs its own widget key written too.
        select_all_col, clear_col, delete_col, count_col = st.columns([1, 1, 1, 2])
        with select_all_col:
            if st.button(f"☑️ Select all ({len(selectable)})", key="garmin_cal_select_all"):
                for item in selectable:
                    st.session_state.garmin_cal_selected.add(item["schedule_id"])
                    st.session_state[calendar_checkbox_key("garmin_cal", str(item["schedule_id"]))] = True
                st.rerun()
        with clear_col:
            if st.button("Clear selection", key="garmin_cal_clear_selection"):
                for item in selectable:
                    st.session_state.garmin_cal_selected.discard(item["schedule_id"])
                    st.session_state[calendar_checkbox_key("garmin_cal", str(item["schedule_id"]))] = False
                st.rerun()
        with delete_col:
            delete_clicked = st.button(
                f"🗑️ Delete selected ({len(selected)})",
                key="garmin_cal_delete_selected",
                disabled=not selected,
            )
        with count_col:
            if selected:
                st.caption(f"{len(selected)} selected")

        st.caption(
            "Selection only ever applies to the month you're currently viewing - it's cleared "
            "automatically when you navigate to a different month. Deleting removes selected "
            "workouts from the calendar only (unschedules) - the workout stays in your Garmin "
            "workout library and can be rescheduled later."
        )

        if delete_clicked:
            for item in selected:
                try:
                    gc.unschedule_workout(item["schedule_id"])
                    st.session_state.garmin_log.append((item["title"], "unschedule", "ok"))
                except Exception as e:
                    st.session_state.garmin_log.append((item["title"], "unschedule", f"error: {e}"))
                st.session_state.garmin_cal_selected.discard(item["schedule_id"])
            st.session_state.garmin_cal_cache.pop(cache_key, None)
            st.rerun()

    events: dict[str, list[dict]] = {}
    for item in selectable:
        events.setdefault(item["date"], []).append(
            {
                "label": f"{sport_icon(item.get('sport'))} {item['title']}",
                "render_detail": _make_detail(item),
                "selected": item["schedule_id"] in st.session_state.garmin_cal_selected,
                "on_select": make_on_select(item["schedule_id"]),
                "event_id": str(item["schedule_id"]),
            }
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
