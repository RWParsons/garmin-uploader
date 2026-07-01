"""Garmin Connect wrapper (3.11-compatible, raw-payload version).

PYTHON 3.11 COMPATIBILITY NOTE
------------------------------
`garminconnect` added a typed workout API (RunningWorkout, CyclingWorkout,
etc.) in version 0.3.3 - and that release also raised the minimum Python
version to 3.12. On Python 3.11 you're capped at garminconnect==0.3.2, which
predates typed workouts entirely.

So on 3.11, every workout type in this file - not just strength - is built
as a raw Garmin Connect JSON payload and posted through the library's
low-level `garth.connectapi()` call (the same authenticated HTTP client the
typed API would have used under the hood).

This is more experimental than the typed-model path: the exact numeric IDs
Garmin uses for step types / end conditions / target types below are the
values consistently seen across several independent community
reverse-engineering projects, but Garmin has never published them, so treat
them as "best effort, verify before trusting for real training." Two ways to
verify/correct them for your account if a push looks wrong in Garmin Connect:

1. Build one sample workout by hand in Garmin Connect's web workout builder,
   then use `client.garth.connectapi("/workout-service/workout/<id>")` (GET)
   to fetch it back and compare field values against WORKOUT_STEP_TYPE etc.
   below.
2. The app's "show raw payload" panel lets you inspect exactly what would be
   sent before you push, so you can sanity-check or hand-edit it.

If you can move to Python 3.12+, switch back to garminconnect>=0.3.4 and a
typed-model version of this file - it's the more reliable path.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from garminconnect import Garmin

from models import CardioStep, Workout

# --- Best-effort, community-sourced constant tables -----------------------
# id/key pairs Garmin's own web + mobile clients send. See module docstring.

SPORT_TYPE = {
    "running": {"sportTypeId": 1, "sportTypeKey": "running"},
    "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling"},
    "stairs": {"sportTypeId": 4, "sportTypeKey": "fitness_equipment"},
    "strength": {"sportTypeId": 5, "sportTypeKey": "strength_training"},
}

WORKOUT_STEP_TYPE = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup"},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery"},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest"},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat"},
}

END_CONDITION = {
    "lap_button": {"conditionTypeId": 1, "conditionTypeKey": "lap.button"},
    "time": {"conditionTypeId": 2, "conditionTypeKey": "time"},
    "distance": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
}

TARGET_TYPE = {
    "none": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
    "power": {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone"},
    "cadence": {"workoutTargetTypeId": 3, "workoutTargetTypeKey": "cadence"},
    "heart_rate": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone"},
    "pace": {"workoutTargetTypeId": 5, "workoutTargetTypeKey": "pace.zone"},
}


def _build_raw_step(step: CardioStep, step_order: int) -> Tuple[Dict[str, Any], int]:
    """Returns (step_dict, next_step_order)."""
    if step.type == "repeat":
        child_steps = []
        order = 1
        for child in step.repeat_steps or []:
            child_dict, order = _build_raw_step(child, order)
            child_steps.append(child_dict)
        return (
            {
                "type": "RepeatGroupDTO",
                "stepOrder": step_order,
                "stepType": WORKOUT_STEP_TYPE["repeat"],
                "numberOfIterations": step.repeat_count or 1,
                "workoutSteps": child_steps,
            },
            step_order + 1,
        )

    step_type = WORKOUT_STEP_TYPE.get(step.type, WORKOUT_STEP_TYPE["interval"])
    end_condition = END_CONDITION.get(step.duration_type, END_CONDITION["time"])
    target = TARGET_TYPE.get(step.target_type, TARGET_TYPE["none"])

    return (
        {
            "type": "ExecutableStepDTO",
            "stepOrder": step_order,
            "stepType": step_type,
            "endCondition": end_condition,
            "endConditionValue": step.duration_value,
            "targetType": target,
            "targetValueOne": step.target_low,
            "targetValueTwo": step.target_high,
            "description": step.note,
        },
        step_order + 1,
    )


def _raw_cardio_payload(workout: Workout) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    order = 1
    for s in workout.steps or []:
        step_dict, order = _build_raw_step(s, order)
        steps.append(step_dict)

    sport_type = SPORT_TYPE[workout.sport]
    return {
        "workoutName": workout.name,
        "sportType": sport_type,
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": sport_type, "workoutSteps": steps}
        ],
        "description": workout.notes,
    }


def _raw_strength_payload(workout: Workout) -> Dict[str, Any]:
    exercises = workout.exercises or []
    steps = []
    for i, ex in enumerate(exercises, start=1):
        steps.append(
            {
                "type": "ExecutableStepDTO",
                "stepOrder": i,
                "stepType": WORKOUT_STEP_TYPE["interval"],
                "exerciseName": ex.name,
                "reps": ex.reps,
                "sets": ex.sets,
                "weightValue": ex.weight_kg,
                "weightUnit": "kilogram" if ex.weight_kg else None,
                "description": ex.note,
            }
        )
    sport_type = SPORT_TYPE["strength"]
    return {
        "workoutName": workout.name,
        "sportType": sport_type,
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": sport_type, "workoutSteps": steps}
        ],
        "description": workout.notes,
    }


def build_raw_payload(workout: Workout) -> Dict[str, Any]:
    """Public helper so the UI can preview exactly what would be sent."""
    if workout.sport == "strength":
        return _raw_strength_payload(workout)
    return _raw_cardio_payload(workout)


class GarminClient:
    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        token_store: str = "~/.garminconnect",
    ):
        self.email = email or os.getenv("GARMIN_EMAIL")
        self.password = password or os.getenv("GARMIN_PASSWORD")
        self.token_store = os.path.expanduser(token_store)
        self._client: Optional[Garmin] = None

    def login(self, mfa_callback=None) -> "GarminClient":
        self._client = Garmin(self.email, self.password, prompt_mfa=mfa_callback)
        self._client.login(self.token_store)
        return self

    @property
    def client(self) -> Garmin:
        if self._client is None:
            raise RuntimeError("Call .login() before using the Garmin client.")
        return self._client

    def _connectapi(self):
        """Locate the raw authenticated-request method across library versions."""
        connectapi = getattr(self.client, "connectapi", None)
        if connectapi is None:
            garth = getattr(self.client, "garth", None)
            connectapi = getattr(garth, "connectapi", None)
        if connectapi is None:
            raise RuntimeError(
                "Couldn't find a raw connectapi() call on this garminconnect "
                "version. Check https://github.com/cyberjunky/python-garminconnect "
                "for how to make authenticated raw requests in your installed "
                "version, and update GarminClient._connectapi() accordingly."
            )
        return connectapi

    def push_workout(self, workout: Workout) -> Dict[str, Any]:
        payload = build_raw_payload(workout)

        # Prefer the library's own upload_workout() when present - some
        # installed versions' connectapi() is hardcoded to GET internally, so
        # passing method="POST" through it raises a "multiple values for
        # argument 'method'" TypeError. upload_workout() POSTs correctly
        # without that footgun.
        upload_workout = getattr(self.client, "upload_workout", None)
        if upload_workout is not None:
            result = upload_workout(payload)
        else:
            connectapi = self._connectapi()
            result = connectapi("/workout-service/workout", method="POST", json=payload)

        if workout.date and result and isinstance(result, dict) and "workoutId" in result:
            self.client.schedule_workout(result["workoutId"], workout.date)
        return result
