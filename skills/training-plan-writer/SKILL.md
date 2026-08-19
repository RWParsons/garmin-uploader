---
name: training-plan-writer
description: Draft running, cycling, swimming, cardio-equipment, HIIT, strength, yoga, or pilates workouts as a CSV file formatted for the Garmin workout uploader app (garmin-uploader), with an optional week-by-week HTML calendar preview. Use whenever the user asks for a workout, training session, or training plan/program they intend to upload to Garmin Connect via that app, or asks to see a plan laid out on a calendar.
---

# Training plan writer

Draft training plans as a CSV file matching the schema the **garmin-uploader**
app expects (`csv_import.py` / `models.py` in that repo), so the user can
upload it directly and push it to Garmin Connect. This runs entirely in
chat — no API key or credits needed, since the app's CSV importer is the
thing doing the real work, not this skill.

## Goal comes first — Garmin metrics are context, not the target

The athlete's stated goal decides what kind of training goes into the
plan — not Garmin's own scoring or "balance" nudges. Garmin's training
metrics (aerobic/anaerobic training effect, training load balance,
VO2max, endurance/hill scores, etc.) describe what recent training *has*
produced; they don't prescribe what future training *should* be.
Everything from `get_training_status`, `get_recovery_signals`,
`get_endurance_score`, etc. is **read-only context** for judging capacity,
recent volume, and recovery/safety — never a target to optimize toward.

Concretely: if the goal is half marathon pace, prioritize
threshold/tempo/race-pace-specific running even if Garmin's training
status shows "low anaerobic load" or nudges toward more high-intensity
work for a "balanced" profile — chasing that balance would work against a
half-marathon-specific goal, not toward it. The same logic runs both ways:
if the goal genuinely *is* VO2max or anaerobic capacity, build toward
that, regardless of what Garmin's current load balance shows.

The one place Garmin data should override or reshape what the goal alone
would suggest is **safety, not optimization**: low training readiness, an
"overreaching" training status, or a resting-HR/HRV trend pointing at
under-recovery are reasons to ease off or delay a hard session (see
**Training history** below) — flag this to the athlete rather than
silently deferring to either the stated goal or the metric.

## Before drafting

### 1. Goals — check memory first, then ask

If the `garmin-training-history` MCP connector is available, it also exposes
`get_athlete_goals` / `set_athlete_goals` — a small local memory of this
athlete's goals that persists between chat sessions (it's a JSON file on
their machine, not tied to any particular conversation).

**At the very start of a planning conversation**, before asking the athlete
anything:

1. Call `get_athlete_goals`.
2. **If it returns saved goals**, summarize them back briefly and ask what's
   changed rather than starting from scratch — e.g. "Last time your goal was
   a sub-3:30 marathon on 2027-03-01, training 5 days/week, currently in a
   12-week build phase with a deload every 4th week. Still the plan, or has
   anything changed (goal, event date, days available, phase, injuries)?"
   Treat a stale-looking `target_date` (already passed) as a cue to ask
   whether they hit the goal and what's next, not to silently reuse it.
   Likewise, if a saved `current_phase`/block timeline looks like it should
   have moved on by now (e.g. a 12-week build started 14 weeks ago), ask
   rather than assuming the athlete is still in the same phase.
3. **If it returns `{}`** (first time, or nothing saved yet), ask the
   goal-setting questions below.
4. Whenever the athlete states a new or changed goal, call
   `set_athlete_goals` with the **full** updated object (it overwrites, not
   merges) so the next session picks it up. Do this even mid-conversation —
   don't wait until the end in case the session is interrupted.

**Goal-setting questions** (skip any already answered by saved goals or by
what the athlete already told you):

- **Primary goal** — a race/event time, a fitness metric (e.g. "get cycling
  FTP to 280W"), general fitness, return-to-training after a break/injury,
  or something else?
- **Target event and date**, if any — this drives periodization (base →
  build → peak → taper) and how aggressive to be with load.
- **Days per week and typical session length** available to train.
- **Sport focus** — which of running/cycling/swimming/cardio/hiit/strength/
  yoga/pilates should the plan prioritize?
- **Constraints** — injuries, equipment access, hard scheduling limits.

**If the athlete is asking for a multi-week block** (not just a single
workout or one week), also ask:

- **Block length and phase** — how many weeks should this block cover, and
  what phase is it (base/build/peak/taper — or "just keep me consistent"
  if there's no target event)? This drives periodization: progressive
  overload during base/build, reduced volume/intensity during a taper.
- **Deload cadence** — how often should there be an easier recovery week
  (e.g. every 3rd or 4th week) to manage fatigue across the block? Don't
  assume a default (e.g. "every 4th week") without confirming — deload
  frequency should match the athlete's own recovery capacity, which you
  don't know without asking.
- **Weekly scheduling constraints** — which days are fixed due to
  work/travel/preference (e.g. long run must be Saturday, no hard sessions
  Monday, rest day is always Wednesday)?
- **Multi-sport priority balance** — if the block trains more than one
  sport (e.g. triathlon-style, or run+strength together), which is the
  priority, and how should volume/intensity be weighted across them so
  they don't compete for the same recovery?

If the connector *isn't* available, there's nowhere to persist goals between
sessions — just ask the questions above each time and proceed without the
memory step.

### 2. Training history

**If the `garmin-training-history` MCP connector is available** (tools named
`get_recent_activities`, `get_activity_splits`, `get_cycling_ftp`,
`get_activity_zones`, `get_training_status`, `get_training_readiness`,
`get_race_predictions`, `get_recovery_signals`, `get_personal_records`,
`get_running_threshold`, `get_athlete_goals`, `set_athlete_goals`), use it
before asking the user anything else — real training history beats a
hand-typed profile:

1. Call `get_recent_activities` (default last 28 days is usually enough;
   widen to 56-90 days for a multi-week block so you can see the training
   trend, not just one snapshot) to see recent volume, frequency, and
   intensity by sport.
2. Call `get_training_status` and `get_training_readiness` for today to
   gauge current load/fatigue — don't stack another hard block on top of
   "overreaching" or low readiness without flagging it to the user.
3. For running, `get_race_predictions` gives you Garmin's current pace
   estimates — use these as a sanity check on target paces instead of
   guessing.
4. For cycling, call `get_cycling_ftp` and set power targets as a
   percentage of it (sweet spot ~88-94% FTP, threshold ~95-105% FTP, VO2max
   ~106-120% FTP, recovery/endurance <75% FTP) instead of guessing watts.
5. Only pull `get_activity_splits` or `get_activity_zones` for a specific
   recent session if you need lap-level or time-in-zone detail — e.g.
   checking whether the athlete actually held target power/pace on their
   last interval or FTP session, to calibrate the next one.
   `get_activity_splits` breaks a *structured* session down by
   `intensityType` (WARMUP/ACTIVE/RECOVERY/COOLDOWN) with per-lap
   HR/power/cadence; `get_activity_zones` gives whole-session time-in-zone
   totals instead.
6. For running, `get_running_threshold` gives a threshold heart rate (the
   run equivalent of FTP) to set HR-based tempo/threshold targets.
7. Call `get_recovery_signals` alongside `get_training_readiness` when you
   want the underlying numbers (HRV, resting HR, stress, body battery,
   weekly intensity minutes) rather than just the blended score — e.g. to
   explain *why* readiness is low, or to spot a resting-HR trend across a
   few days.
8. `get_personal_records` gives PR times/distances (5K, 10K, half, marathon,
   longest run/ride, etc.) — useful for sanity-checking that a goal or
   target pace is realistic relative to what the athlete has actually done.

State briefly what the history showed (e.g. "I see ~25km/week running over
the last month, mostly easy pace, last hard session 9 days ago") so the
athlete can correct you if it's misleading (illness, a device swap, etc.).

**If the connector isn't available**, there's no training history or saved
goals to pull — ask for an athlete profile instead: the goal-setting
questions from step 1, plus running threshold pace, cycling FTP, swim pace
per 100m, comfortable cardio-equipment cadence, and strength/yoga/pilates
experience level.

### 3. What they want this time

Ask (if not already obvious from the goals/history above): a single
workout, a week, or a multi-week block; which sport(s) today's request is
for; target dates if they want it scheduled (leave blank if not).

Don't guess at zones/paces/FTP if you don't have enough to compute them from
either the connector or what the athlete told you — ask rather than
inventing numbers that could end up on someone's watch.

## Output requirement

**Always create the CSV as an actual file for the user to download — never
just print it in the chat window as text.** The app needs a real `.csv` file
to upload.

## CSV format

Exact column headers, in this order:

```
workout_name,sport,date,workout_notes,item_order,repeat_group,repeat_count,step_type,duration_type,duration_value,target_type,target_low,target_high,item_note,exercise_name,sets,reps,weight_kg,rest_seconds
```

Rules:

- **One row = one cardio step OR one named exercise.** Rows are grouped into
  a workout by matching `(workout_name, sport, date)`.
- `sport` is one of: `running`, `cycling`, `swimming`, `cardio` (general
  cardio equipment — stair-stepper, elliptical, rower, etc.; `stairs` also
  works as an alias), `hiit`, `strength`, `yoga`, `pilates`.
- `strength`, `yoga`, `pilates` are **exercise-based** sports; every other
  sport is **step-based**. Don't mix the two row shapes within one workout.
- `date` is `YYYY-MM-DD` or blank (blank = the user schedules it themselves
  later in the app).
- `item_order` is an integer giving the order of items within a workout
  (1, 2, 3, ...).
- **For step-based sports**, fill: `step_type`
  (`warmup`/`interval`/`recovery`/`cooldown`/`rest`), `duration_type`
  (`time`/`distance`/`calories`), `duration_value` (seconds if `time`,
  meters if `distance`, kcal if `calories`), `target_type`
  (`none`/`pace`/`speed`/`power`/`heart_rate`/`cadence`), `target_low`,
  `target_high`. Leave `exercise_name`/`sets`/`reps`/`weight_kg`/
  `rest_seconds` blank on these rows.
- **For exercise-based sports**, fill: `exercise_name`, `sets`, `reps`,
  `weight_kg` (blank if bodyweight), `rest_seconds`. Leave
  `step_type`/`duration_type`/`duration_value`/`target_type`/`target_low`/
  `target_high` blank on these rows. For yoga/pilates, `reps` is usually `1`
  per pose/hold and the hold duration goes in `item_note` (e.g.
  `"Hold 45s"`) since there's no dedicated duration field on exercise rows.
- **Repeating blocks** (e.g. 6x400m intervals): give those rows the same
  `repeat_group` value (any short label, unique per repeated block within
  that workout) and put the repeat count in `repeat_count` on each of those
  rows. Leave `repeat_group` blank for steps that don't repeat.
- **Target units**: pace in **seconds-per-km**, speed in km/h, power in
  watts, heart rate in bpm, cadence in rpm (bike) or steps/min (cardio
  equipment). Convert whatever pace/speed the user gives you (e.g. min/km,
  min/mile, mph) into these units before writing the row.
- Put a short description of the whole workout in `workout_notes` (repeat it
  on every row for that workout, or just put it on the first row — the app
  takes the first non-blank value it finds per workout).

## Worked example

```csv
workout_name,sport,date,workout_notes,item_order,repeat_group,repeat_count,step_type,duration_type,duration_value,target_type,target_low,target_high,item_note,exercise_name,sets,reps,weight_kg,rest_seconds
VO2 Intervals,running,,6x400m @ VO2max pace,1,,,warmup,time,600,heart_rate,120,140,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,2,intervals,6,interval,distance,400,pace,195,205,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,3,intervals,6,recovery,time,90,none,,,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,4,,,cooldown,time,600,heart_rate,110,130,,,,,,
Full Body Strength,strength,,45 min full body,1,,,,,,,,,,Back Squat,4,8,60,120
Full Body Strength,strength,,45 min full body,2,,,,,,,,,,Bench Press,4,8,40,120
Morning Yoga Flow,yoga,,20 min flexibility flow,1,,,,,,,,,Hold 45s each side,Warrior II,2,1,,
```

Note the `intervals` repeat group: the warmup/cooldown rows have no
`repeat_group`/`repeat_count`, but the two rows inside the 6x block share
`repeat_group=intervals` and both carry `repeat_count=6`.

## Multi-workout / multi-week plans

Just add more rows with a different `workout_name`/`sport`/`date` — the
importer groups automatically. There's no limit enforced here; for a full
week or training block, give every workout its own `workout_name` and set
`date` if the user wants it scheduled on specific days.

## Visual calendar preview (optional)

If Artifacts are available in this conversation (claude.ai or Claude
Desktop) and the drafted plan has more than a couple of dated workouts,
offer to also render a self-contained HTML artifact showing the plan
week-by-week — styled like the garmin-uploader app's own "Calendar view"
(`render_month_grid` in `workout_ui.py`), so the athlete can see the whole
block at a glance before downloading the CSV. This is a bonus
visualization on top of the CSV, never a replacement for it — always still
produce the CSV file per **Output requirement** above regardless of
whether a calendar preview is also built. Skip it for a single one-off
workout; it's not worth the extra artifact.

**Layout**: one section per calendar week (Monday–Sunday) that contains at
least one dated workout — don't pad out a full month grid with empty
leading/trailing weeks. Within each week, 7 day columns (including empty
days), each labeled with its date and weekday name.

**Per workout, mirror the app's own visual language** so it's recognizable
to someone who's used the app:

- Sport icon prefix on the workout name: 🏃 running, 🚴 cycling, 🏊 swimming,
  🏋️ cardio/stairs, 🔥 hiit, 🏋️ strength, 🧘 yoga/pilates.
- Make each workout expandable to reveal its steps — a native
  `<details><summary>` element is enough, no JS required — matching the
  app's own step display:
  - **Step-based sports**: one line per step with a type icon (🟠 warmup,
    🟢 interval, ⚪ recovery, 🔵 cooldown, ⏸️ rest), formatted duration
    (`mm:ss` for time, km/m for distance, `N cal` for calories), and target
    if set, e.g. `Pace 5:47/km (5:30–6:00/km)`, `Power 220W (200–240)`,
    `HR 150bpm (140–160)`. A repeat block shows as `🔁 Repeat 6×` wrapping
    its child steps (indent or nest them visually).
  - **Exercise-based sports** (strength/yoga/pilates): one line per
    exercise, e.g. `🏋️ Back Squat — 4×8 @ 60kg`.
- Keep it self-contained (inline CSS, no external requests/fonts) and
  legible in both light and dark viewing, since artifacts can render in
  either.

Don't spend excessive effort matching exact colors/fonts pixel-for-pixel —
the goal is a recognizable, readable weekly layout, not a clone of the
app's CSS.

## After drafting

Tell the user to upload the file on the app's **Upload workouts** page,
where they can review/edit it in a table and push it to Garmin — and that
the app's **How to** page has the same spec if they need to hand-edit
anything later.
