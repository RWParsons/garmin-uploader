"""Shared Streamlit rendering helpers for editing a Workout.

Used by both upload_workouts_page.py (drafts freshly imported from CSV) and
pages/1_Manage_Workouts.py (workouts fetched back from Garmin), so the
editing UI - and any future fixes to it - stays identical in both places.
"""
from __future__ import annotations

import calendar as _calendar
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from garmin_client import EXERCISE_SPORTS, build_raw_payload
from models import CardioStep, Exercise, Workout

SPORT_ICON = {
    "running": "🏃",
    "cycling": "🚴",
    "swimming": "🏊",
    "cardio": "🏋️",
    "stairs": "🏋️",
    "hiit": "🔥",
    "strength": "🏋️",
    "yoga": "🧘",
    "pilates": "🧘",
}

# Fallback for calendar events whose sport is missing/unrecognized (e.g. a
# Garmin calendar item type this app doesn't have a mapping for yet) - the
# calendar should always show *some* icon next to a workout, never a blank.
DEFAULT_EVENT_ICON = "🏷️"


def sport_icon(sport: Optional[str]) -> str:
    return SPORT_ICON.get(sport or "") or DEFAULT_EVENT_ICON

STEP_ICON = {
    "warmup": "🟠",
    "cooldown": "🔵",
    "interval": "🟢",
    "recovery": "⚪",
    "rest": "⏸️",
}

TARGET_UNIT = {"power": "W", "heart_rate": "bpm", "cadence": "", "speed": "km/h"}
TARGET_LABEL = {"power": "Power", "heart_rate": "HR", "cadence": "Cadence", "speed": "Speed"}


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
    if step.duration_type == "calories":
        if step.duration_value is None:
            return "—"
        return f"{step.duration_value:.0f} cal"
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
            # Faster pace = fewer seconds/km, so low..high is already the
            # ascending (lower-to-higher) time order, e.g. "5:30-6:00".
            midpoint = (low + high) / 2
            return f"Pace {_format_pace(midpoint)} ({_format_pace(low)}–{_format_pace(high)})"
        return f"Pace {_format_pace(low if low is not None else high)}"
    unit = TARGET_UNIT[step.target_type]
    label = TARGET_LABEL[step.target_type]
    if low is not None and high is not None:
        lo, hi = min(low, high), max(low, high)
        midpoint = (lo + hi) / 2
        suffix = (" " + unit) if unit else ""
        return f"{label} {int(round(midpoint))}{suffix} ({int(lo)}–{int(hi)})"
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


def render_exercise_list(exercises: list[Exercise]) -> None:
    """Read-only display of strength/yoga/pilates exercises, for popups and
    other places that just need to show a workout rather than edit it.
    """
    for ex in exercises:
        line = f"🏋️ **{ex.name}** — {ex.sets}×{ex.reps}"
        if ex.weight_kg:
            line += f" @ {ex.weight_kg:g} kg"
        st.markdown(line)
        if ex.note:
            st.caption(ex.note)


def render_workout_summary(workout: Workout) -> None:
    """Read-only summary of a workout's steps or exercises plus its notes,
    for popups and other places that just need to show a workout rather
    than edit it.
    """
    if workout.notes:
        st.caption(workout.notes)
    if workout.steps:
        render_step_blocks(workout.steps)
    elif workout.exercises:
        render_exercise_list(workout.exercises)
    else:
        st.caption("No steps/exercises on this workout.")


def render_month_nav(year: int, month: int, key_prefix: str) -> Tuple[int, int]:
    """Prev/next-month buttons plus a title. Returns the (possibly updated)
    (year, month) - callers should persist it in session_state so navigation
    sticks across reruns, then use it to fetch/filter events before calling
    render_month_grid().
    """
    prev_col, title_col, next_col = st.columns([1, 4, 1])
    with prev_col:
        if st.button("◀", key=f"{key_prefix}_prev"):
            month -= 1
            if month < 1:
                month, year = 12, year - 1
    with next_col:
        if st.button("▶", key=f"{key_prefix}_next"):
            month += 1
            if month > 12:
                month, year = 1, year + 1
    with title_col:
        st.markdown(f"**{_calendar.month_name[month]} {year}**")
    return year, month


def _run_on_select(cb_key: str, on_select) -> None:
    on_select(st.session_state[cb_key])


def render_month_grid(
    events_by_date: Dict[str, List[Dict[str, Any]]],
    year: int,
    month: int,
    key_prefix: str,
    lazy: bool = False,
) -> None:
    """Render a month grid with events shown under their day cell.

    Each event is a dict with a "label" (icon + name, always shown), an
    optional "render_detail" - a zero-arg callable that renders the workout's
    steps - and an optional "selected"/"on_select" pair for a checkbox
    rendered beside the event, separate from the popover button (checking it
    does not open the popover):

    - "selected": bool, whether the checkbox should currently show checked.
    - "on_select": Callable[[bool], None], called with the new checked state
      when the user toggles it.

    The caller owns the actual selected/not-selected truth (e.g. a set of
    ids in session_state) and updates it inside on_select - deliberately
    NOT read back from the checkbox widget's own session_state after the
    fact. A widget's own state only survives while it keeps getting
    instantiated on every rerun; since a given day's events (and thus this
    checkbox) only render while that month is the one currently displayed,
    navigating to a different month and back would otherwise silently drop
    the selection the next time Streamlit re-mounts the checkbox.

    Each event should also carry a stable "event_id" (e.g. str(id(workout))
    for in-memory objects, or a Garmin schedule_id) - it's used as part of
    the checkbox/popover widget keys instead of that event's (date,
    position-in-day) slot. Positional keys are unsafe here: once items can
    be deleted, a later render's event at the same slot is a *different*
    logical event, but Streamlit still treats it as the same widget (a
    widget's `value=` is only honored the first time its key is ever seen -
    every render after that, Streamlit ignores `value=` and keeps reusing
    whatever's already in session_state for that key). Without a stable id,
    that shows up as a checkbox silently inheriting a previous, unrelated
    event's checked state right after a delete shifts positions - which
    then makes the *next* delete act on whatever that stale checkbox
    happens to say, not what the user actually selected. Falls back to
    (date, position) if "event_id" is omitted, for callers with no
    select/delete UI where this doesn't matter.

    lazy=True makes the popover stateful (on_change="rerun") and gates
    render_detail behind the .open check, so it only runs once the user has
    actually opened that event - use this when render_detail does expensive
    on-demand work like a Garmin API fetch, for events with no further
    interactive content once opened.

    lazy=False (default) renders content eagerly every rerun, same as a
    plain st.popover - use this whenever render_detail contains its own
    interactive widgets (e.g. a push-to-Garmin button), since a stateful
    popover's .open flag isn't guaranteed to still read True on the very
    rerun triggered by clicking something inside it, which would silently
    swallow that click before the button widget is even instantiated.
    """
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    header_cols = st.columns(7)
    for c, name in zip(header_cols, day_names):
        c.markdown(f"**{name}**")

    today = date.today()
    for week in _calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        cols = st.columns(7)
        for c, day in zip(cols, week):
            if day == 0:
                continue
            d = date(year, month, day)
            with c.container(border=True):
                st.markdown(f"**{day}**" + (" 🔵" if d == today else ""))
                for i, event in enumerate(events_by_date.get(d.isoformat(), [])):
                    label = event.get("label", "Workout")
                    render_detail = event.get("render_detail")
                    on_select = event.get("on_select")
                    event_id = event.get("event_id", f"{d.isoformat()}_{i}")

                    if on_select is not None:
                        cb_col, content_col = st.columns([0.2, 0.8])
                        cb_key = f"{key_prefix}_cb_{event_id}"
                        with cb_col:
                            st.checkbox(
                                "select",
                                value=bool(event.get("selected")),
                                key=cb_key,
                                on_change=_run_on_select,
                                args=(cb_key, on_select),
                                label_visibility="collapsed",
                            )
                    else:
                        content_col = st.container()

                    with content_col:
                        _render_calendar_event(label, render_detail, lazy, key_prefix, event_id)


def _render_calendar_event(
    label: str, render_detail, lazy: bool, key_prefix: str, event_id: str
) -> None:
    if render_detail is None:
        st.caption(label)
        return
    if not lazy:
        with st.popover(label, use_container_width=True):
            render_detail()
        return
    popover = st.popover(
        label,
        use_container_width=True,
        key=f"{key_prefix}_pop_{event_id}",
        on_change="rerun",
    )
    with popover:
        if popover.open:
            render_detail()


def _flatten_steps(steps: list[CardioStep]) -> list[dict]:
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
            rows.extend(_flatten_steps(s.repeat_steps))
    return rows


def render_workout_editor(workout: Workout, key_prefix: str) -> Workout:
    """Render the editable name/date/exercises-or-steps/notes/raw-payload UI
    for one workout, mutating it in place. Returns the same object.

    `key_prefix` must be unique per workout instance on the page (e.g.
    f"draft_{idx}" or f"garmin_{workout_id}") so widget keys don't collide
    when several workouts are rendered in the same page/loop.
    """
    new_name = st.text_input("Name", value=workout.name, key=f"{key_prefix}_name")
    new_date = st.date_input(
        "Date to schedule on Garmin (leave blank to leave unscheduled)",
        value=date.fromisoformat(workout.date) if workout.date else None,
        key=f"{key_prefix}_date",
    )
    workout.name = new_name
    # value=None round-trips as None until the user actually picks a date -
    # don't silently default an unscheduled workout to today() just because
    # it was rendered in the editor (it would then wrongly show up as
    # "scheduled" on calendar views and bulk-push-by-date actions).
    workout.date = new_date.isoformat() if new_date else None

    if workout.sport in EXERCISE_SPORTS:
        if workout.exercises:
            df = pd.DataFrame([e.model_dump() for e in workout.exercises])
            edited = st.data_editor(df, num_rows="dynamic", key=f"{key_prefix}_ex")
            workout.exercises = [Exercise(**row) for row in edited.to_dict("records")]
        else:
            st.warning("No exercises on this workout.")
    else:
        if workout.steps:
            df = pd.DataFrame(_flatten_steps(workout.steps))
            st.dataframe(df, width="stretch")
            st.caption(
                "Repeat-group steps are flattened here for readability. "
                "For structural changes (more/fewer intervals etc.), it's "
                "easiest to redraft the workout rather than hand-edit."
            )

            st.markdown("**As it will appear in Garmin Connect:**")
            render_step_blocks(workout.steps)
        else:
            st.warning("No steps on this workout.")

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

    return workout
