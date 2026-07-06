# Claude → Garmin workout planner

A small local Streamlit app:

1. You draft a plan with Claude Desktop and export it as a CSV - running,
   cycling, swimming, cardio equipment, HIIT, strength, yoga, or pilates.
2. You upload that CSV here and review/tweak it in a table.
3. You push it straight to your Garmin Connect account (and optionally
   schedule it on a date), so it shows up on your watch next sync.
4. On the **Manage Garmin Workouts** page, you can pull back workouts
   already sitting in your Garmin Connect workout library, edit and
   re-send them, or delete them (one at a time or in bulk).

## Drafting a plan

Ask Claude Desktop (or your preferred LLM) to draft your plan as a CSV matching the
column format below, download the CSV it creates, and upload it in the app. There's a ready-made prompt
template further down to paste in as-is.

### CSV column format

Columns, in order:

```
workout_name,sport,date,workout_notes,item_order,repeat_group,repeat_count,step_type,duration_type,duration_value,target_type,target_low,target_high,item_note,exercise_name,sets,reps,weight_kg,rest_seconds
```

- One row = one cardio step OR one named exercise.
- `sport` is one of: `running`, `cycling`, `swimming`, `cardio` (general
  cardio equipment - stair-stepper, elliptical, rower, etc.; `stairs` also
  works as an alias), `hiit`, `strength`, `yoga`, `pilates`.
  `strength`/`yoga`/`pilates` are exercise-based (see below); every other
  sport is step-based.
- `date` is `YYYY-MM-DD` or blank (blank = schedule it yourself later).
- `item_order` is an integer giving the order of items within a workout
  (1, 2, 3, ...).
- For step-based sports (running/cycling/swimming/cardio/stairs/hiit), fill:
  `step_type` (warmup/interval/recovery/cooldown/rest), `duration_type`
  (time/distance/calories), `duration_value` (seconds if time, meters if
  distance, kcal if calories), `target_type`
  (none/pace/speed/power/heart_rate/cadence), `target_low`, `target_high`.
  Leave `exercise_name`/`sets`/`reps`/`weight_kg`/`rest_seconds` blank on
  these rows.
- For exercise-based sports (strength/yoga/pilates), fill: `exercise_name`,
  `sets`, `reps`, `weight_kg` (blank if bodyweight), `rest_seconds`. Leave
  `step_type`/`duration_type`/`duration_value`/`target_type`/`target_low`/`target_high`
  blank on these rows. For yoga/pilates, `reps` is usually `1` per pose/hold
  and the hold duration goes in `item_note` (e.g. "Hold 45s") since there's
  no dedicated duration field for exercise rows.
- To make a set of steps repeat (e.g. 6x400m intervals), give those rows the
  same `repeat_group` value (any short label, unique per repeated block) and
  put the number of repeats in `repeat_count` on each of those rows. Leave
  `repeat_group` blank for steps that don't repeat.
- Target units: pace in seconds-per-km, speed in km/h, power in watts, heart
  rate in bpm, cadence in rpm (bike) or steps/min (cardio equipment).
- Put a short description of the whole workout in `workout_notes` (repeat it
  on every row for that workout, or just the first row).

### Prompt template

Paste this into Claude Desktop, claude.ai, or any other LLM chat, filling in
the athlete profile and request at the bottom, to get a CSV in the right
format:

```
You are drafting a training plan as a CSV file for me to upload to a workout-planning app. Create the file (don't just print it in chat) with EXACTLY these column headers, in this order:

workout_name,sport,date,workout_notes,item_order,repeat_group,repeat_count,step_type,duration_type,duration_value,target_type,target_low,target_high,item_note,exercise_name,sets,reps,weight_kg,rest_seconds

Rules:
- One row = one cardio step OR one named exercise.
- sport is one of: running, cycling, swimming, cardio (general cardio equipment - stair-stepper, elliptical, rower, etc.), hiit, strength, yoga, pilates
- strength/yoga/pilates are exercise-based sports; every other sport is step-based
- date is YYYY-MM-DD or blank (blank = I'll schedule it myself later)
- item_order is an integer giving the order of items within a workout (1, 2, 3, ...)
- For step-based sports, fill: step_type (warmup/interval/recovery/cooldown/rest), duration_type (time/distance/calories), duration_value (seconds if time, meters if distance, kcal if calories), target_type (none/pace/speed/power/heart_rate/cadence), target_low, target_high. Leave exercise_name/sets/reps/weight_kg/rest_seconds blank on these rows.
- For exercise-based sports, fill: exercise_name, sets, reps, weight_kg (blank if bodyweight), rest_seconds. Leave step_type/duration_type/duration_value/target_type/target_low/target_high blank on these rows. For yoga/pilates, reps is usually 1 per pose/hold and the hold duration goes in item_note (e.g. "Hold 45s").
- To make a set of steps repeat (e.g. 6x400m intervals), give those rows the same repeat_group value (any short label, unique per repeated block) and put the number of repeats in repeat_count on each of those rows. Leave repeat_group blank for steps that don't repeat.
- Target units: pace in seconds-per-km, speed in km/h, power in watts, heart rate in bpm, cadence in rpm (bike) or steps/min (cardio equipment).
- Put a short description of the whole workout in workout_notes (repeat it on every row for that workout, or just the first row).

My athlete profile:
[e.g. running threshold pace, cycling FTP, swim pace per 100m, comfortable cardio-equipment cadence, strength/yoga/pilates experience and injuries]

Now draft: [describe the workout(s) you want]
```

## Managing workouts already on Garmin

The **Manage Garmin Workouts** page (in the sidebar page nav, or
`pages/1_Manage_Workouts.py`) lets you work with what's already in your
Garmin Connect **workout library** - this is the library of saved workout
templates, not the calendar, so a workout shows up here whether or not it's
scheduled on any date:

- **View** - "🔄 Refresh from Garmin" lists up to 100 of your most recent
  workouts. Click "✏️ Load for editing" on one to fetch its full detail and
  open the same editable table/preview used on the CSV-import page.
- **Modify and re-send** - edit the loaded workout, then "💾 Update on
  Garmin (replace)". Garmin's workout API has no in-place edit, so this
  uploads your edited version as a new workout and then deletes the old one
  - the workout gets a **new workout ID** as a result. If you want it
  scheduled on a date, set that in the date picker before updating; the page
  doesn't try to auto-detect or preserve a workout's prior calendar
  scheduling.
- **Delete** - one at a time via the "🗑️ Delete" button inside a workout, or
  in bulk: tick the checkboxes next to workouts (or "☑️ Select all"), then
  "🗑️ Delete selected".

Turning a workout fetched from Garmin back into the app's editable format is
the reverse of building the upload payload (`parse_garmin_workout()` in
`garmin_client.py`), so it's subject to the same "best effort,
reverse-engineered" caveat as everything else here - see below. It only
reconstructs fields the app itself sends (per-exercise rest time isn't
round-tripped, for instance, since the app never sends it in the first
place), and workouts built by hand in Garmin Connect's own UI (rather than
by this app) may not round-trip perfectly.

## Python version

This build targets **Python 3.11**. That matters because the `garminconnect`
library added its typed workout API in version 0.3.3, and that release also
requires Python 3.12+. On 3.11 you're capped at `garminconnect==0.3.2` (pinned
in `requirements.txt`), which predates typed workouts - so `garmin_client.py`
builds raw Garmin Connect JSON payloads directly instead of using typed
model classes. See the big comment at the top of `garmin_client.py` for the
details and its limits.

**If you can use Python 3.12+ instead, do that.** It lets you use
`garminconnect>=0.3.4`'s typed workout API, which is the more reliable,
actively-maintained path (running/cycling/stairs go through a proper typed
model rather than a hand-built payload with best-effort field IDs). This
3.11 build is for cases where you're genuinely locked to 3.11.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env with your Garmin email/password
```

Run it:

```bash
streamlit run app.py
```

This opens a local web page (usually http://localhost:8501). Nothing here is
deployed anywhere - it's just your machine talking to Garmin Connect.

## How it works

- **`models.py`** - the JSON shape both Claude and the Garmin pusher agree on:
  a list of workouts, each with either cardio `steps` (warmup/interval/
  recovery/cooldown/repeat, with duration + target - running/cycling/
  swimming/cardio/stairs/hiit) or named `exercises` (name/sets/reps/weight -
  strength/yoga/pilates). See `EXERCISE_SPORTS` for which sports use which.
- **`prompt_templates.py`** - a starter CSV template matching the format
  documented above.
- **`csv_import.py`** - parses that CSV export into the model above.
- **`garmin_client.py`** - logs into Garmin Connect via the unofficial
  [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
  library; builds the raw upload payload (`build_raw_payload`) and its
  inverse for reading workouts back (`parse_garmin_workout`); wraps
  list/get/delete/update on the Garmin workout library.
- **`workout_ui.py`** - the editable workout UI (name/date, exercise or step
  table, Garmin-style step preview, raw-payload debug panel) shared by both
  pages, so edits behave identically whether the workout came from a CSV or
  from Garmin.
- **`garmin_session.py`** - the Garmin Connect login sidebar, shared by both
  pages (Streamlit re-runs only the active page's script on navigation, so
  this can't just live inline in one of them).
- **`app.py`** - entry point. Declares the pages via `st.navigation()` with
  explicit titles ("Upload workouts" / "Manage workouts" / "How to") and
  runs whichever one is selected - run this with `streamlit run app.py`.
- **`upload_workouts_page.py`** - page 1 ("Upload workouts"): import a CSV,
  review/edit, push to Garmin.
- **`pages/1_Manage_Workouts.py`** - page 2 ("Manage workouts"): view/edit/
  delete workouts already in your Garmin workout library. See **Managing
  workouts already on Garmin** above.
- **`pages/2_How_To.py`** - page 3 ("How to"): an in-app, user-facing
  walkthrough of the same drafting/uploading/managing flow documented here,
  plus the ready-made LLM prompt (`LLM_PROMPT_TEMPLATE` in
  `prompt_templates.py`) so users don't need to come back to this README
  just to draft a plan.

## Important caveats (read before relying on this)

- **This uses an unofficial, reverse-engineered Garmin Connect API.**
  It isn't Garmin's public developer API - it works by mimicking Garmin's own
  apps. It can break when Garmin changes something server-side, and it's not
  officially sanctioned, so use at your own judgment.
- **On Python 3.11, every workout type is pushed as a hand-built raw JSON
  payload**, not just strength. The sport-type / step-type / end-condition /
  target-type numeric IDs in `garmin_client.py` (`SPORT_TYPE`,
  `WORKOUT_STEP_TYPE`, `END_CONDITION`, `TARGET_TYPE`) are best-effort values
  seen across community reverse-engineering projects, not something Garmin
  publishes or guarantees. Use the **"Show raw Garmin payload (debug)"**
  panel in the app before pushing anything important, and check the actual
  workout in Garmin Connect afterward to confirm steps/targets came through
  as expected. If a value looks wrong, the README section above on
  `garmin_client.py`'s docstring explains how to fetch a known-good workout
  back from Garmin Connect and correct the constant tables for your account.
- **Confidence varies by sport/target.** `running`, `cycling`, `strength`,
  and the `none`/`power`/`cadence`/`heart_rate` targets are cross-confirmed
  by multiple independent sources and have been used successfully. `swimming`,
  `cardio`/`stairs`, `hiit`, `yoga`, and `pilates` sport IDs, and the
  `speed`/`pace` targets, rest on thinner evidence (fewer independent
  sources agreeing) - double-check these against the raw payload panel and
  the actual pushed workout the first few times you use them.
- **If a push fails outright or looks wrong**, use the **Download draft as
  JSON** button to see exactly what was planned, and enter it by hand into
  Garmin Connect's own workout builder (Training > Workouts > Create a
  Workout) - that path always works regardless of any issues here.
- **"Stairs"** is an alias for the `cardio` sport (Garmin's "Cardio
  Training" category - there's no dedicated stair-machine type), typically
  targeted by heart rate or cadence.
- **Credentials.** Run locally, `.env` never leaves your machine, and the app
  doesn't send your Garmin password anywhere except to Garmin's own login
  endpoint. Garmin auth tokens are cached in a per-session temporary
  directory (not a fixed path) so you won't have to re-login within the same
  browser session - see the **Deploying** section below for why this matters
  once the app isn't just running on your own machine.
- **MFA:** if your Garmin account has multi-factor auth, the first login
  attempt will fail asking for a code - enter it in the sidebar field and
  click "Log in to Garmin" again. After that, cached tokens keep you logged
  in for the rest of that browser session.
- **Library API drift:** the Garmin wrapper library used here (`garminconnect`)
  is actively maintained but unofficial, so its exact function signatures can
  change between releases. `garmin_client.py` calls things defensively
  (dropping unsupported keyword arguments rather than crashing) to absorb
  small changes, but if a whole method disappears you may need to check
  https://github.com/cyberjunky/python-garminconnect for the current API and
  adjust `garmin_client.py` accordingly.

## Deploying

This is written to run locally, but if you do host it somewhere (e.g.
Streamlit Community Cloud):

- **Never commit `.env`.** It's already gitignored, and only
  `.env.example` (a placeholder template) is tracked - keep it that way.
  Don't hardcode credentials in any `.py` file as a workaround for a
  deployment not picking up `.env`.
- **Set secrets through the platform's secrets manager, not env vars on
  disk.** Streamlit Community Cloud has a Secrets panel (Settings > Secrets)
  that works like a `.streamlit/secrets.toml` file (also gitignored here).
  Add `GARMIN_EMAIL` and `GARMIN_PASSWORD` there as root-level keys (not
  nested under a `[section]`) - Streamlit exposes root-level secrets as
  regular environment variables too, so the existing `os.getenv(...)` calls
  in `garmin_session.py` pick them up with no code changes needed.
- **Per-session token isolation matters more once it's not just you.** The
  per-session temp directory noted above (rather than the shared
  `~/.garminconnect` default) exists specifically so concurrent users on a
  shared deployment can't end up reusing each other's cached Garmin login.
  If you ever change `garmin_session.py` to pass a fixed `token_store` path,
  that guarantee goes away.
- **Anyone who can reach the app can push/delete workouts on whichever
  Garmin account is logged in during their session.** There's no
  per-visitor authentication layer beyond the Garmin login form itself -
  don't deploy this somewhere with unauthenticated public access unless
  that's genuinely fine for your account.

## Extending it

- Want a multi-week plan pushed in one go? Just ask Claude for several
  workouts with different `date` values in one CSV - the app already loops
  over `plan.workouts` and has a "Push ALL" button.
- Want pace/power auto-computed from a goal race time or FTP test? Mention
  that when you prompt Claude Desktop, referencing the column format above.
