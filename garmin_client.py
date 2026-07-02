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
Garmin uses for sport types / step types / end conditions / target types
below are the values consistently seen across several independent community
reverse-engineering projects, but Garmin has never published them, so treat
them as "best effort, verify before trusting for real training." Confidence
varies by table - running/cycling/strength and the core step/target types
are cross-confirmed by multiple independent sources; swimming, cardio,
yoga, pilates, and hiit rest on thinner evidence (see the comments next to
each entry below). Two ways to verify/correct them for your account if a
push looks wrong in Garmin Connect:

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

from models import EXERCISE_SPORTS, CardioStep, Exercise, Workout

# --- Best-effort, community-sourced constant tables -----------------------
# id/key pairs Garmin's own web + mobile clients send. See module docstring.

SPORT_TYPE = {
    "running": {"sportTypeId": 1, "sportTypeKey": "running"},
    "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling"},
    "swimming": {"sportTypeId": 4, "sportTypeKey": "swimming"},
    "strength": {"sportTypeId": 5, "sportTypeKey": "strength_training"},
    "cardio": {"sportTypeId": 6, "sportTypeKey": "cardio_training"},
    # "stairs" is a legacy alias for "cardio" - Garmin has no dedicated
    # stair-machine/stepper sport type, so cardio_training is the closest
    # verified match (lower confidence than running/cycling/strength).
    "stairs": {"sportTypeId": 6, "sportTypeKey": "cardio_training"},
    "yoga": {"sportTypeId": 7, "sportTypeKey": "yoga"},  # lower confidence
    "pilates": {"sportTypeId": 8, "sportTypeKey": "pilates"},  # lower confidence
    "hiit": {"sportTypeId": 9, "sportTypeKey": "hiit"},  # lower confidence
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
    "calories": {"conditionTypeId": 4, "conditionTypeKey": "calories"},
}

TARGET_TYPE = {
    "none": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
    "power": {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone"},
    "cadence": {"workoutTargetTypeId": 3, "workoutTargetTypeKey": "cadence.zone"},
    "heart_rate": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone"},
    "speed": {"workoutTargetTypeId": 5, "workoutTargetTypeKey": "speed.zone"},
    "pace": {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone"},
}

# --- Reverse lookups, for parsing workouts fetched back from Garmin --------
# SPORT_TYPE maps two keys ("cardio" and "stairs") onto the same id (6) -
# "cardio" is the canonical reverse-mapped name; "stairs" is only ever an
# input alias, never something we'd reconstruct from a fetched workout.
SPORT_ID_TO_KEY = {
    1: "running",
    2: "cycling",
    4: "swimming",
    5: "strength",
    6: "cardio",
    7: "yoga",
    8: "pilates",
    9: "hiit",
}
STEP_TYPE_BY_ID = {v["stepTypeId"]: k for k, v in WORKOUT_STEP_TYPE.items()}
END_CONDITION_BY_ID = {v["conditionTypeId"]: k for k, v in END_CONDITION.items()}
TARGET_TYPE_BY_ID = {v["workoutTargetTypeId"]: k for k, v in TARGET_TYPE.items()}

# Human-readable sport labels, prefixed onto the workout name sent to Garmin
# (see _garmin_workout_name below) so the sport is visible in Garmin
# Connect's planner/calendar, which otherwise just shows the bare workout
# name (e.g. "Base", "Threshold") with no indication of what it's for.
SPORT_LABEL = {
    "running": "Run",
    "cycling": "Bike",
    "swimming": "Swim",
    "cardio": "Cardio",
    "stairs": "Stairs",
    "hiit": "HIIT",
    "strength": "Strength",
    "yoga": "Yoga",
    "pilates": "Pilates",
}


def _garmin_workout_name(workout: Workout) -> str:
    label = SPORT_LABEL.get(workout.sport, workout.sport.title())
    return f"{label} - {workout.name}"


def _strip_sport_label(name: str) -> str:
    """Inverse of _garmin_workout_name(), for parsing a workout back from
    Garmin. Matches against any known label rather than the workout's own
    (reconstructed) sport, since e.g. "stairs" always reverse-maps to the
    canonical "cardio" (see SPORT_ID_TO_KEY) - matching only "Cardio - "
    would miss a "Stairs - " prefix and leave it to accumulate double
    prefixes on repeated edit/re-push cycles.
    """
    for label in SPORT_LABEL.values():
        prefix = f"{label} - "
        if name.startswith(prefix):
            return name[len(prefix):]
    return name

# Garmin's raw targetValueOne/targetValueTwo are ALWAYS meters/second, even
# for pace.zone targets - "pace" vs "speed" target type only changes how
# Garmin's own UI displays the value, not the unit it's stored in. The app's
# CSV/model layer uses seconds-per-km for pace (see README) and km/h for
# speed, so both need converting before/after the Garmin API boundary.


def _pace_to_speed(seconds_per_km: Optional[float]) -> Optional[float]:
    return 1000 / seconds_per_km if seconds_per_km else None


def _speed_to_pace(meters_per_second: Optional[float]) -> Optional[float]:
    return 1000 / meters_per_second if meters_per_second else None


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

    if step.target_type == "pace":
        # target_low/high are seconds-per-km with low = the *faster* end
        # (fewer seconds/km - see workout_ui.py). Speed moves the opposite
        # direction from pace, so the faster pace becomes the higher speed:
        # swap them so targetValueOne <= targetValueTwo in m/s, as Garmin expects.
        target_value_one = _pace_to_speed(step.target_high)
        target_value_two = _pace_to_speed(step.target_low)
    elif step.target_type == "speed":
        # target_low/high are km/h; same direction as m/s, so no swap needed.
        target_value_one = step.target_low / 3.6 if step.target_low is not None else None
        target_value_two = step.target_high / 3.6 if step.target_high is not None else None
    else:
        target_value_one = step.target_low
        target_value_two = step.target_high

    return (
        {
            "type": "ExecutableStepDTO",
            "stepOrder": step_order,
            "stepType": step_type,
            "endCondition": end_condition,
            "endConditionValue": step.duration_value,
            "targetType": target,
            "targetValueOne": target_value_one,
            "targetValueTwo": target_value_two,
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
        "workoutName": _garmin_workout_name(workout),
        "sportType": sport_type,
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": sport_type, "workoutSteps": steps}
        ],
        "description": workout.notes,
    }


def _raw_exercise_payload(workout: Workout) -> Dict[str, Any]:
    """Payload for exercise-based sports: strength, yoga, pilates.

    Garmin's exercise-catalog lookup (matching ex.name to a canonical
    exercise ID) isn't replicated here - exerciseName is sent as free text,
    which is what Garmin Connect's own workout builder falls back to when it
    doesn't recognize a name, so unrecognized exercises just show up as
    plain-text steps instead of catalog entries.
    """
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
    sport_type = SPORT_TYPE[workout.sport]
    return {
        "workoutName": _garmin_workout_name(workout),
        "sportType": sport_type,
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": sport_type, "workoutSteps": steps}
        ],
        "description": workout.notes,
    }


def build_raw_payload(workout: Workout) -> Dict[str, Any]:
    """Public helper so the UI can preview exactly what would be sent."""
    if workout.sport in EXERCISE_SPORTS:
        return _raw_exercise_payload(workout)
    return _raw_cardio_payload(workout)


def _parse_raw_step(raw: Dict[str, Any]) -> CardioStep:
    if raw.get("type") == "RepeatGroupDTO":
        return CardioStep(
            type="repeat",
            repeat_count=int(raw.get("numberOfIterations") or 1),
            repeat_steps=[_parse_raw_step(s) for s in raw.get("workoutSteps") or []],
        )
    step_type_id = (raw.get("stepType") or {}).get("stepTypeId")
    condition_id = (raw.get("endCondition") or {}).get("conditionTypeId")
    target_id = (raw.get("targetType") or {}).get("workoutTargetTypeId")
    target_type = TARGET_TYPE_BY_ID.get(target_id, "none")
    value_one, value_two = raw.get("targetValueOne"), raw.get("targetValueTwo")

    if target_type == "pace":
        # Inverse of the swap in _build_raw_step: value_two is the higher
        # speed (m/s), i.e. the faster pace, which is target_low here.
        target_low = _speed_to_pace(value_two)
        target_high = _speed_to_pace(value_one)
    elif target_type == "speed":
        target_low = value_one * 3.6 if value_one is not None else None
        target_high = value_two * 3.6 if value_two is not None else None
    else:
        target_low, target_high = value_one, value_two

    return CardioStep(
        type=STEP_TYPE_BY_ID.get(step_type_id, "interval"),
        duration_type=END_CONDITION_BY_ID.get(condition_id, "time"),
        duration_value=raw.get("endConditionValue"),
        target_type=target_type,
        target_low=target_low,
        target_high=target_high,
        note=raw.get("description"),
    )


def _parse_raw_exercise(raw: Dict[str, Any]) -> Exercise:
    return Exercise(
        name=raw.get("exerciseName") or "Unnamed exercise",
        sets=int(raw.get("sets") or 0),
        reps=int(raw.get("reps") or 0),
        weight_kg=raw.get("weightValue"),
        # Garmin's stored exercise steps don't carry rest time back the way
        # we send it (_raw_exercise_payload never transmits rest_seconds
        # either - see its docstring) - always None on the round trip.
        rest_seconds=None,
        note=raw.get("description"),
    )


def parse_garmin_workout(raw: Dict[str, Any]) -> Workout:
    """Best-effort inverse of build_raw_payload() - turns a workout fetched
    back from Garmin (via GarminClient.list_workouts/get_workout) into our
    Workout model, for editing in the same UI used to build one from a CSV.

    This only reconstructs what build_raw_payload() itself sends - fields
    Garmin's own workout builder can set that we never produce (per-exercise
    rest, exercise-catalog IDs, calendar scheduling) are dropped rather than
    guessed at. Workouts not originally created by this app may round-trip
    imperfectly for the same reason the forward direction is "best effort" -
    see the module docstring.
    """
    sport_id = (raw.get("sportType") or {}).get("sportTypeId")
    sport = SPORT_ID_TO_KEY.get(sport_id, "cardio")

    segments = raw.get("workoutSegments") or []
    raw_steps = segments[0].get("workoutSteps", []) if segments else []

    workout = Workout(
        name=_strip_sport_label(raw.get("workoutName") or "Untitled workout"),
        sport=sport,
        notes=raw.get("description"),
    )
    if sport in EXERCISE_SPORTS:
        workout.exercises = [
            _parse_raw_exercise(s) for s in raw_steps if "exerciseName" in s
        ]
    else:
        workout.steps = [_parse_raw_step(s) for s in raw_steps]
    return workout


def parse_calendar_workouts(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull the scheduled-workout entries out of a calendar month payload
    (GarminClient.get_scheduled_workouts()), normalized to
    {workout_id, title, date, sport, fetchable}.

    A calendar month carries several item types - confirmed against a real
    account: "workout" (scheduled from the workout library), "activity",
    "event", "nap", and "trainingPlan" (a plan's start marker, not an
    individual workout). Garmin Coach / adaptive training plans show up as
    their own itemType, e.g. "fbtAdaptiveWorkout" - matched here by "workout"
    appearing anywhere in the itemType (substring, not exact) since Garmin
    doesn't publish an exhaustive list and there may be other coach-plan
    variants. Coach items don't carry a workoutId the way library workouts
    do (their real reference is a separate workoutUuid on an
    adaptive-training endpoint this app doesn't call) - so workout_id here
    is only good for display/grouping, not for get_workout()/
    update_workout(). Sport comes from sportTypeKey (a plain string like
    "cycling") on both item types seen so far; the sportTypeId fallback
    below is for older/other calendar response shapes that may use it
    instead - check the raw payload debug panel if a scheduled workout
    doesn't show up or its sport is blank.

    "fetchable" is True only for exact itemType "workout" - those are real
    workout-library entries, so their workout_id works with get_workout().
    Coach/adaptive items (matched by the broader substring above) get
    False - their workout_id is calendar-display-only, since GET
    /workout-service/workout/<id> doesn't have anything at that id for them.
    """
    items = raw.get("calendarItems") or raw.get("items") or []
    workouts = []
    for item in items:
        item_type = str(item.get("itemType") or item.get("type") or "")
        if "workout" not in item_type.lower():
            continue
        workout_id = item.get("workoutId") or item.get("id")
        if workout_id is None:
            continue
        sport = item.get("sportTypeKey") or ""
        if not sport:
            sport_id = item.get("sportTypeId") or (item.get("sportType") or {}).get("sportTypeId")
            sport = SPORT_ID_TO_KEY.get(sport_id, "")
        workouts.append(
            {
                "workout_id": workout_id,
                "title": item.get("title") or item.get("workoutName") or "Untitled workout",
                "date": item.get("date"),
                "sport": sport,
                "fetchable": item_type.lower() == "workout",
            }
        )
    return workouts


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

    def list_workouts(self, start: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """List workouts saved in the Garmin Connect workout library.

        This is the library of workout templates, not the calendar - a
        workout can exist here whether or not it's scheduled on any date.
        """
        return self.client.get_workouts(start=start, limit=limit)

    def get_scheduled_workouts(self, year: int, month: int) -> Dict[str, Any]:
        """Raw Garmin calendar payload for one month (month is 1-12) -
        includes workouts scheduled on the calendar, alongside activities/
        races/events. Use parse_calendar_workouts() to pull just the
        workout entries out of it. Backed by the garminconnect library's own
        get_scheduled_workouts(), not a hand-rolled endpoint.
        """
        return self.client.get_scheduled_workouts(year, month)

    def get_workout(self, workout_id: Any) -> Dict[str, Any]:
        """Fetch full detail (including steps) for one workout by ID.

        list_workouts() results are summaries and don't include
        workoutSegments - call this before editing a workout in the UI.
        """
        return self.client.get_workout_by_id(workout_id)

    def delete_workout(self, workout_id: Any) -> Any:
        return self.client.delete_workout(workout_id)

    def update_workout(self, old_workout_id: Any, workout: Workout) -> Dict[str, Any]:
        """Replace an existing workout: upload the edited version first, and
        only delete the old one once the new upload has succeeded - so a
        failed update never leaves you with neither copy. Garmin's workout
        API has no in-place edit, so "update" is really "create new, then
        remove old"; the workout gets a new ID as a result.
        """
        result = self.push_workout(workout)
        self.delete_workout(old_workout_id)
        return result
