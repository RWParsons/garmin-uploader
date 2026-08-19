"""Local MCP server exposing read-only Garmin Connect training history.

Lets Claude Desktop look up your recent activities / training load before
drafting a plan with the `training-plan-writer` skill (see skills/), instead
of drafting blind or relying on whatever you type into the athlete-profile
prompt by hand. This is a local stdio MCP server - Claude Desktop launches it
as a subprocess and talks to it directly, so using it costs nothing beyond
your existing Claude subscription (no Anthropic API key involved).

It reuses GarminClient from garmin_client.py - the exact same login code the
Streamlit app uses - so it's subject to the same "unofficial, reverse-
engineered API" caveat as the rest of this project (see README.md). This
server is READ-ONLY: it never calls push_workout/delete_workout/etc., only
the history-lookup methods on the underlying `garminconnect` client.

Setup
-----
1. `pip install -r requirements.txt` in this repo (already includes `mcp`).
2. Make sure `.env` (copied from .env.example) has GARMIN_EMAIL/GARMIN_PASSWORD.
3. Add this server to Claude Desktop's MCP config (Settings > Developer >
   Edit Config), e.g.:

   {
     "mcpServers": {
       "garmin-training-history": {
         "command": "C:\\path\\to\\garmin-uploader\\.venv\\Scripts\\python.exe",
         "args": ["C:\\path\\to\\garmin-uploader\\garmin_mcp_server.py"]
       }
     }
   }

4. Restart Claude Desktop. The tools below become available in chat, and the
   training-plan-writer skill will use them automatically when asked to plan
   around your recent training.

Session tokens are cached at ~/.garmin_mcp_tokens so you don't need to log in
(or re-enter an MFA code) every time Claude Desktop restarts this server -
unlike the Streamlit app, which deliberately uses a fresh per-session temp
dir (see garmin_session.py), this is a single-user local tool where a
persistent cache is the right tradeoff.

Athlete goals set via get_athlete_goals/set_athlete_goals are stored
separately at ~/.garmin_mcp_training_goals.json - plain local JSON, not
Garmin data and not tied to any one chat session, so a returning athlete
doesn't have to re-explain their goals every time (see
skills/training-plan-writer/SKILL.md for how the skill uses this).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from garmin_client import GarminClient  # noqa: E402  (needs the sys.path insert above)

load_dotenv(Path(__file__).resolve().parent / ".env")

from mcp.server.fastmcp import FastMCP  # noqa: E402

TOKEN_STORE = os.path.expanduser("~/.garmin_mcp_tokens")
# Deliberately outside TOKEN_STORE - that directory's contents are managed by
# garth's own login cache, not something we want to mix our own file into.
GOALS_STORE = os.path.expanduser("~/.garmin_mcp_training_goals.json")

mcp = FastMCP("garmin-training-history")

_client: Optional[GarminClient] = None


def _mfa_callback() -> str:
    code = os.getenv("GARMIN_MFA_CODE")
    if not code:
        raise RuntimeError(
            "Garmin is asking for an MFA code and none is available. Log in once "
            "through the Streamlit app (or set GARMIN_MFA_CODE=<code> in .env after "
            "requesting a code), then restart Claude Desktop to relaunch this server - "
            "after one successful login the session is cached in ~/.garmin_mcp_tokens "
            "and you won't need to do this again."
        )
    return code


def _get_client() -> GarminClient:
    """Lazily log in on first tool call, then reuse the session for the rest
    of this server process's lifetime (it lives as long as Claude Desktop
    keeps it running, not just one chat turn)."""
    global _client
    if _client is not None:
        return _client
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "GARMIN_EMAIL / GARMIN_PASSWORD not set. Copy .env.example to .env in the "
            "garmin-uploader repo root and fill in your Garmin Connect credentials."
        )
    gc = GarminClient(email, password, token_store=TOKEN_STORE)
    gc.login(mfa_callback=_mfa_callback)
    _client = gc
    return _client


def _num(d: dict, *keys: str) -> Optional[float]:
    """First present, non-null value among keys - Garmin's activity schema
    isn't officially documented and field names have drifted across API
    versions, so summaries below probe a couple of likely names rather than
    assuming one."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


# Best-effort typeId -> (label, unit) map for get_personal_record(). Garmin
# doesn't publish what these IDs mean - this mapping is cross-checked against
# real values on a live account (e.g. typeId 3's value of ~1165 seconds lines
# up with an actual 19:25 5K on the same date), the same "best-effort,
# verify against real data" approach garmin_client.py takes for its own
# undocumented constant tables. Unmapped ids are left unlabeled rather than
# guessed at.
PERSONAL_RECORD_TYPES = {
    1: ("Fastest 1km", "seconds"),
    2: ("Fastest 1 mile", "seconds"),
    3: ("Fastest 5K", "seconds"),
    4: ("Fastest 10K", "seconds"),
    5: ("Fastest half marathon", "seconds"),
    6: ("Fastest marathon", "seconds"),
    7: ("Longest run", "meters"),
    8: ("Longest ride", "meters"),
    9: ("Most elevation gain - single ride", "elevation_meters"),
}


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _summarize_personal_record(raw: dict) -> dict[str, Any]:
    type_id = raw.get("typeId")
    label, unit = PERSONAL_RECORD_TYPES.get(type_id, (None, "raw"))
    value = raw.get("value")
    entry: dict[str, Any] = {
        "record": label or f"unmapped record type {type_id}",
        "value": value,
        "unit": unit,
        "activity_name": raw.get("activityName"),
        "date": raw.get("activityStartDateTimeLocalFormatted"),
    }
    if value is not None:
        if unit == "seconds":
            entry["formatted"] = _format_duration(value)
        elif unit == "meters":
            entry["formatted"] = f"{value / 1000:.2f} km"
        elif unit == "elevation_meters":
            entry["formatted"] = f"{value:.0f} m"
    return entry


def _summarize_activity(raw: dict) -> dict[str, Any]:
    """Compact view of one Garmin activity - the raw payload carries dozens
    of rarely-useful fields (device info, gear, per-lap arrays elsewhere,
    etc.); this keeps just what's useful for reasoning about training
    history, and converts units to match what the training-plan-writer
    skill/CSV format already uses (km, minutes, km/h, seconds-per-km pace).
    """
    activity_type = (raw.get("activityType") or {}).get("typeKey", "unknown")
    distance_m = _num(raw, "distance")
    duration_s = _num(raw, "duration")
    avg_speed_mps = _num(raw, "averageSpeed")

    summary: dict[str, Any] = {
        "activity_id": raw.get("activityId"),
        "name": raw.get("activityName"),
        "type": activity_type,
        "date": raw.get("startTimeLocal"),
        "distance_km": round(distance_m / 1000, 2) if distance_m else None,
        "duration_min": round(duration_s / 60, 1) if duration_s else None,
        "avg_hr": _num(raw, "averageHR"),
        "max_hr": _num(raw, "maxHR"),
        "calories": _num(raw, "calories"),
        "elevation_gain_m": _num(raw, "elevationGain"),
        "aerobic_training_effect": _num(raw, "aerobicTrainingEffect"),
        "anaerobic_training_effect": _num(raw, "anaerobicTrainingEffect"),
    }
    if avg_speed_mps:
        if activity_type in ("running", "walking", "hiking", "trail_running"):
            summary["avg_pace_sec_per_km"] = round(1000 / avg_speed_mps)
        else:
            summary["avg_speed_kmh"] = round(avg_speed_mps * 3.6, 1)
    return summary


@mcp.tool()
def get_recent_activities(
    days: int = 28, activity_type: Optional[str] = None, limit: int = 50
) -> list[dict[str, Any]]:
    """List recent completed Garmin activities (actual training history, not
    planned workouts) as compact summaries - date, type, distance, duration,
    HR, pace/speed, training effect.

    Use this before drafting a plan to see what the athlete has actually
    been doing: recent volume, intensity distribution, and how long ago
    their last hard session was.

    Args:
        days: how many days back from today to look (default 28, i.e. ~4 weeks).
        activity_type: optional Garmin type key to filter to one sport, e.g.
            "running", "cycling", "swimming", "strength_training". Leave
            unset to get everything.
        limit: max number of activities to return (most recent first).
    """
    from datetime import date, timedelta

    client = _get_client()
    end = date.today()
    start = end - timedelta(days=days)
    activities = client.client.get_activities_by_date(
        start.isoformat(), end.isoformat(), activitytype=activity_type
    )
    activities = sorted(activities, key=lambda a: a.get("startTimeLocal") or "", reverse=True)
    return [_summarize_activity(a) for a in activities[:limit]]


@mcp.tool()
def get_activity_splits(activity_id: str) -> dict[str, Any]:
    """Lap/split-level detail for one activity - pace, power, cadence, and
    heart rate per lap. For a *structured* session (e.g. one built from
    warmup/interval/recovery/cooldown steps, like the ones this app itself
    pushes to Garmin), each lap carries an `intensityType`
    (WARMUP/ACTIVE/RECOVERY/COOLDOWN/etc.) plus that lap's averageHR,
    maxHR, averagePower, and averageBikeCadence - i.e. exactly what heart
    rate/power the athlete produced against each programmed step, not just
    a whole-session average. Use this to check pacing/power consistency or
    interval execution on a specific session returned by
    get_recent_activities (e.g. deciding whether the athlete actually held
    target power on their last FTP interval session).

    Args:
        activity_id: the activity_id from a get_recent_activities result.
    """
    client = _get_client()
    return client.client.get_activity_splits(activity_id)


@mcp.tool()
def get_cycling_ftp() -> dict[str, Any]:
    """Current cycling Functional Threshold Power (FTP) in watts, as
    recorded in Garmin Connect (`functionalThresholdPower`) - either
    auto-detected from rides or manually set by the athlete. Use this as
    the basis for power-based cycling zones/targets when drafting cycling
    workouts (e.g. sweet-spot ~88-94% FTP, threshold ~95-105% FTP, VO2max
    ~106-120% FTP).
    """
    client = _get_client()
    return client.client.get_cycling_ftp()


@mcp.tool()
def get_activity_zones(activity_id: str) -> dict[str, Any]:
    """Time-in-zone breakdown for one activity: how many seconds were spent
    in each heart-rate zone and (if the activity recorded power, e.g. a
    trainer/power-meter ride) each power zone. Complements
    get_activity_splits - splits show per-lap averages against the
    programmed steps, this shows the overall intensity distribution across
    the whole session. power_zones is null if the activity has no power
    data (e.g. a run with no power meter, or an indoor session without a
    smart trainer).

    Args:
        activity_id: the activity_id from a get_recent_activities result.
    """
    client = _get_client()
    try:
        hr_zones = client.client.get_activity_hr_in_timezones(activity_id)
    except Exception:
        hr_zones = None
    try:
        power_zones = client.client.get_activity_power_in_timezones(activity_id)
    except Exception:
        power_zones = None
    return {"heart_rate_zones": hr_zones, "power_zones": power_zones}


@mcp.tool()
def get_training_status(on_date: Optional[str] = None) -> dict[str, Any]:
    """Garmin's own training status snapshot for a date: training load
    (acute/chronic workload), VO2max, and training status label (e.g.
    "productive", "unproductive", "detraining"). Pass-through of Garmin's
    endpoint - field names aren't officially documented, so treat this as
    directional context, not exact figures.

    Args:
        on_date: "YYYY-MM-DD"; defaults to today.
    """
    from datetime import date

    client = _get_client()
    cdate = on_date or date.today().isoformat()
    return client.client.get_training_status(cdate)


@mcp.tool()
def get_training_readiness(on_date: Optional[str] = None) -> dict[str, Any]:
    """Garmin's training-readiness score for a date (0-100, blends recovery
    signals like sleep, HRV status, and recent training load). Useful for
    judging whether to schedule something hard soon or prioritize recovery.

    Args:
        on_date: "YYYY-MM-DD"; defaults to today.
    """
    from datetime import date

    client = _get_client()
    cdate = on_date or date.today().isoformat()
    return client.client.get_training_readiness(cdate)


@mcp.tool()
def get_race_predictions() -> dict[str, Any]:
    """Garmin's current predicted race times (5K/10K/half/full marathon),
    derived from recent training and fitness trends. Useful as a sanity
    check on running paces/targets when drafting a plan.
    """
    client = _get_client()
    return client.client.get_race_predictions()


@mcp.tool()
def get_recovery_signals(on_date: Optional[str] = None) -> dict[str, Any]:
    """Bundled recovery/readiness signals for a date: HRV status, resting
    heart rate, all-day stress, body battery, and weekly intensity minutes.
    Complements get_training_readiness (which blends most of these into one
    score) by exposing the underlying numbers - useful for explaining *why*
    readiness is low, or spotting a trend the single score alone wouldn't
    (e.g. resting HR creeping up over several days you check individually).
    Any signal Garmin doesn't have data for on this date comes back null
    rather than failing the whole call.

    Args:
        on_date: "YYYY-MM-DD"; defaults to today.
    """
    from datetime import date

    client = _get_client()
    cdate = on_date or date.today().isoformat()

    def _safe(fn):
        try:
            return fn()
        except Exception:
            return None

    hrv = _safe(lambda: client.client.get_hrv_data(cdate))
    rhr = _safe(lambda: client.client.get_rhr_day(cdate))
    stress = _safe(lambda: client.client.get_all_day_stress(cdate))
    battery = _safe(lambda: client.client.get_body_battery(cdate))
    intensity = _safe(lambda: client.client.get_intensity_minutes_data(cdate))

    hrv_summary = (hrv or {}).get("hrvSummary") if isinstance(hrv, dict) else None
    rhr_value = None
    if isinstance(rhr, dict):
        try:
            rhr_value = rhr["allMetrics"]["metricsMap"]["WELLNESS_RESTING_HEART_RATE"][0]["value"]
        except (KeyError, IndexError, TypeError):
            rhr_value = None
    battery_today = battery[0] if isinstance(battery, list) and battery else {}

    return {
        "date": cdate,
        "resting_hr": rhr_value,
        "hrv_status": (hrv_summary or {}).get("status"),
        "hrv_weekly_avg_ms": (hrv_summary or {}).get("weeklyAvg"),
        "hrv_last_night_avg_ms": (hrv_summary or {}).get("lastNightAvg"),
        "avg_stress": (stress or {}).get("avgStressLevel"),
        "max_stress": (stress or {}).get("maxStressLevel"),
        "body_battery_charged": battery_today.get("charged"),
        "body_battery_drained": battery_today.get("drained"),
        "weekly_intensity_moderate_min": (intensity or {}).get("weeklyModerate"),
        "weekly_intensity_vigorous_min": (intensity or {}).get("weeklyVigorous"),
        "weekly_intensity_goal_min": (intensity or {}).get("weekGoal"),
    }


@mcp.tool()
def get_personal_records() -> list[dict[str, Any]]:
    """Personal records (fastest times / longest distances) saved in Garmin
    Connect - fastest 1km/1mile/5K/10K/half/marathon, longest run, longest
    ride, most elevation gained on a single ride. Useful context for
    goal-setting and sanity-checking target paces/distances against what
    the athlete has actually done before. Record-type labels for the ids
    above are a best-effort mapping (see PERSONAL_RECORD_TYPES) since Garmin
    doesn't publish them; any other record type comes back unlabeled with
    its raw type id rather than a guessed-at name.
    """
    client = _get_client()
    raw = client.client.get_personal_record()
    return [_summarize_personal_record(r) for r in raw]


@mcp.tool()
def get_running_threshold() -> dict[str, Any]:
    """Current running lactate-threshold heart rate from Garmin Connect -
    the run-training equivalent of get_cycling_ftp, useful for setting
    HR-based threshold/tempo targets. Deliberately returns heart rate only:
    this same Garmin endpoint also reports a threshold pace and running
    power, but on inspection those values don't pass a basic unit sanity
    check (the pace implies an implausibly slow threshold effort) and
    aren't corroborated elsewhere in this project, so they're omitted
    rather than risk feeding a wrong pace into a plan - cross-check running
    pace targets against get_race_predictions and get_recent_activities
    instead.
    """
    client = _get_client()
    raw = client.client.get_lactate_threshold(latest=True)
    speed_hr = raw.get("speed_and_heart_rate") or {}
    return {
        "threshold_heart_rate": speed_hr.get("heartRate"),
        "as_of": speed_hr.get("calendarDate"),
    }


@mcp.tool()
def get_athlete_goals() -> dict[str, Any]:
    """Previously saved training goals/context for this athlete, if any -
    call this at the start of a planning conversation, before asking the
    athlete anything, so a returning athlete doesn't have to re-explain
    their goals every session. Returns {} if nothing has been saved yet
    (first-ever session, or a goals file that was manually deleted) - in
    that case, ask the standard goal-setting questions and call
    set_athlete_goals to save the answers for next time.

    This is local storage tied to this machine/account, not Anthropic
    account memory - it lives in a JSON file at ~/.garmin_mcp_training_goals.json.
    """
    if not os.path.exists(GOALS_STORE):
        return {}
    with open(GOALS_STORE, "r", encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def set_athlete_goals(goals: dict[str, Any]) -> dict[str, Any]:
    """Save (or overwrite) this athlete's training goals/context, so the
    next session's get_athlete_goals call picks them up. Pass the FULL
    updated goals object each time, not just the fields that changed - this
    replaces whatever was saved before rather than merging. Call this any
    time the athlete states or changes a goal, not just at the start of a
    conversation.

    There's no fixed schema (Garmin has nothing to do with this data - it's
    just a JSON file this server manages), but a useful shape is:
    {
      "primary_goal": "e.g. sub-3:30 marathon, build cycling FTP to 280W, general fitness",
      "target_event": "e.g. City Marathon" (optional),
      "target_date": "YYYY-MM-DD" (optional),
      "sports_focus": ["running", "cycling", ...],
      "days_per_week": 5,
      "constraints": "injuries, time limits, equipment access, etc.",
      "block_length_weeks": 12 (optional - for a multi-week training block),
      "current_phase": "e.g. base / build / peak / taper" (optional),
      "deload_cadence": "e.g. every 4th week" (optional),
      "schedule_constraints": "e.g. long run must be Saturday, no hard sessions Monday" (optional),
      "sports_priority": "e.g. run is priority, cycling/strength are supplementary" (optional, for multi-sport blocks),
      "notes": "anything else worth remembering"
    }

    Args:
        goals: the full goals object to save (see shape above - all keys optional/freeform).
    """
    from datetime import datetime, timezone

    goals = dict(goals)
    goals["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(GOALS_STORE, "w", encoding="utf-8") as f:
        json.dump(goals, f, indent=2)
    return goals


if __name__ == "__main__":
    mcp.run()
