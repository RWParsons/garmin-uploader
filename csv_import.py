"""Parse a Claude-Desktop-drafted CSV into a WorkoutPlan.

This exists so you can draft workouts by chatting with Claude in the desktop
app (which uses your Pro/Max plan, not API credits) and export a CSV, rather
than needing a funded Anthropic API key just to draft plans.

See the "Prompt for Claude Desktop" box in the app (or README.md) for the
exact column spec Claude is asked to produce. One row = one cardio step OR
one strength exercise. Rows are grouped into workouts by
(workout_name, sport, date).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from models import CardioStep, Exercise, Workout, WorkoutPlan

REQUIRED_COLUMNS = [
    "workout_name",
    "sport",
    "date",
    "workout_notes",
    "item_order",
    "repeat_group",
    "repeat_count",
    "step_type",
    "duration_type",
    "duration_value",
    "target_type",
    "target_low",
    "target_high",
    "item_note",
    "exercise_name",
    "sets",
    "reps",
    "weight_kg",
    "rest_seconds",
]


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def parse_csv_to_plan(file) -> WorkoutPlan:
    df = pd.read_csv(file)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "CSV is missing required columns: " + ", ".join(missing) +
            ". Use the template / Claude Desktop prompt in the app to regenerate it."
        )

    # Keep a stable row order within each workout.
    df["_row"] = range(len(df))
    df = df.sort_values(["workout_name", "sport", "date", "item_order", "_row"], na_position="last")

    workouts: List[Workout] = []
    group_cols = ["workout_name", "sport", "date"]
    for (name, sport, date), group in df.groupby(group_cols, dropna=False, sort=False):
        notes = None
        for v in group["workout_notes"]:
            if _clean(v) is not None:
                notes = str(v)
                break

        workout = Workout(
            name=str(name),
            sport=str(sport).strip().lower(),
            date=str(date) if _clean(date) is not None else None,
            notes=notes,
        )

        if workout.sport == "strength":
            workout.exercises = _build_exercises(group)
        else:
            workout.steps = _build_steps(group)

        workouts.append(workout)

    return WorkoutPlan(workouts=workouts)


def _build_exercises(group: pd.DataFrame) -> List[Exercise]:
    exercises = []
    for _, row in group.iterrows():
        if _clean(row.get("exercise_name")) is None:
            continue
        exercises.append(
            Exercise(
                name=str(row["exercise_name"]),
                sets=int(row["sets"]) if _clean(row.get("sets")) is not None else 0,
                reps=int(row["reps"]) if _clean(row.get("reps")) is not None else 0,
                weight_kg=float(row["weight_kg"]) if _clean(row.get("weight_kg")) is not None else None,
                rest_seconds=float(row["rest_seconds"]) if _clean(row.get("rest_seconds")) is not None else None,
                note=str(row["item_note"]) if _clean(row.get("item_note")) is not None else None,
            )
        )
    return exercises


def _row_to_step(row) -> CardioStep:
    return CardioStep(
        type=str(row["step_type"]).strip().lower() if _clean(row.get("step_type")) is not None else "interval",
        duration_type=str(row["duration_type"]).strip().lower() if _clean(row.get("duration_type")) is not None else "time",
        duration_value=float(row["duration_value"]) if _clean(row.get("duration_value")) is not None else None,
        target_type=str(row["target_type"]).strip().lower() if _clean(row.get("target_type")) is not None else "none",
        target_low=float(row["target_low"]) if _clean(row.get("target_low")) is not None else None,
        target_high=float(row["target_high"]) if _clean(row.get("target_high")) is not None else None,
        note=str(row["item_note"]) if _clean(row.get("item_note")) is not None else None,
    )


def _build_steps(group: pd.DataFrame) -> List[CardioStep]:
    steps: List[CardioStep] = []
    seen_groups: Dict[str, int] = {}  # repeat_group value -> index of its repeat step in `steps`

    for _, row in group.iterrows():
        rgroup = _clean(row.get("repeat_group"))
        if rgroup is not None:
            rgroup = str(rgroup)
            if rgroup not in seen_groups:
                rcount = int(row["repeat_count"]) if _clean(row.get("repeat_count")) is not None else 1
                steps.append(CardioStep(type="repeat", repeat_count=rcount, repeat_steps=[]))
                seen_groups[rgroup] = len(steps) - 1
            idx = seen_groups[rgroup]
            steps[idx].repeat_steps.append(_row_to_step(row))
        else:
            steps.append(_row_to_step(row))

    return steps
