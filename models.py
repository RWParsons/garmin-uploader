"""Data models shared between the Claude planner and the Garmin pusher.

These are intentionally simple, JSON-friendly shapes. Claude is prompted to
return data matching this schema; garmin_client.py then translates it into
the (unofficial) garminconnect typed-workout objects.
"""
from __future__ import annotations

from typing import List, Optional, Literal

from pydantic import BaseModel, Field

Sport = Literal["running", "cycling", "stairs", "strength"]
StepType = Literal["warmup", "interval", "recovery", "cooldown", "repeat", "rest"]
DurationType = Literal["time", "distance", "lap_button"]
TargetType = Literal["none", "pace", "power", "heart_rate", "cadence"]


class CardioStep(BaseModel):
    type: StepType
    duration_type: DurationType = "time"
    duration_value: Optional[float] = None  # seconds if "time", meters if "distance"
    target_type: TargetType = "none"
    target_low: Optional[float] = None
    target_high: Optional[float] = None
    note: Optional[str] = None
    # only used when type == "repeat"
    repeat_count: Optional[int] = None
    repeat_steps: Optional[List["CardioStep"]] = None


CardioStep.model_rebuild()


class Exercise(BaseModel):
    name: str
    sets: int
    reps: int
    weight_kg: Optional[float] = None
    rest_seconds: Optional[float] = None
    note: Optional[str] = None


class Workout(BaseModel):
    name: str
    sport: Sport
    date: Optional[str] = None  # "YYYY-MM-DD"; leave unset to push without scheduling
    notes: Optional[str] = None
    steps: Optional[List[CardioStep]] = None  # running / cycling / stairs
    exercises: Optional[List[Exercise]] = None  # strength


class WorkoutPlan(BaseModel):
    workouts: List[Workout] = Field(default_factory=list)
