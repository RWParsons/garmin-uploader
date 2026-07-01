# Claude → Garmin workout planner

A small local Streamlit app:

1. You draft a plan with Claude Desktop and export it as a CSV - running /
   cycling / stairs / gym.
2. You upload that CSV here and review/tweak it in a table.
3. You push it straight to your Garmin Connect account (and optionally
   schedule it on a date), so it shows up on your watch next sync.

## Drafting a plan

Ask Claude Desktop (or claude.ai) to draft your plan as a CSV matching the
column format below, download the CSV it creates, and upload it in the app -
no Anthropic API key or API credits needed. There's also a downloadable
starter template with worked examples (including a repeated-interval block
and a strength session) in the "Need a starting template instead?" expander
in the app.

### CSV column format

Columns, in order:

```
workout_name,sport,date,workout_notes,item_order,repeat_group,repeat_count,step_type,duration_type,duration_value,target_type,target_low,target_high,item_note,exercise_name,sets,reps,weight_kg,rest_seconds
```

- One row = one cardio step OR one strength exercise.
- `sport` is one of: `running`, `cycling`, `stairs`, `strength`.
- `date` is `YYYY-MM-DD` or blank (blank = schedule it yourself later).
- `item_order` is an integer giving the order of items within a workout
  (1, 2, 3, ...).
- For running/cycling/stairs rows, fill: `step_type`
  (warmup/interval/recovery/cooldown/rest), `duration_type` (time/distance),
  `duration_value` (seconds if time, meters if distance), `target_type`
  (none/pace/power/heart_rate/cadence), `target_low`, `target_high`. Leave
  `exercise_name`/`sets`/`reps`/`weight_kg`/`rest_seconds` blank on these rows.
- For strength rows, fill: `exercise_name`, `sets`, `reps`, `weight_kg` (blank
  if bodyweight), `rest_seconds`. Leave
  `step_type`/`duration_type`/`duration_value`/`target_type`/`target_low`/`target_high`
  blank on these rows.
- To make a set of steps repeat (e.g. 6x400m intervals), give those rows the
  same `repeat_group` value (any short label, unique per repeated block) and
  put the number of repeats in `repeat_count` on each of those rows. Leave
  `repeat_group` blank for steps that don't repeat.
- Pace targets are in seconds-per-km. Power in watts. Heart rate in bpm.
  Cadence in rpm (bike) or steps/min (stairs).
- Put a short description of the whole workout in `workout_notes` (repeat it
  on every row for that workout, or just the first row).

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
  recovery/cooldown/repeat, with duration + target) or strength `exercises`
  (name/sets/reps/weight).
- **`prompt_templates.py`** - a starter CSV template matching the format
  documented above.
- **`csv_import.py`** - parses that CSV export into the model above.
- **`garmin_client.py`** - logs into Garmin Connect via the unofficial
  [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
  library, converts the plan into Garmin's typed workout objects, uploads,
  and optionally schedules them on your calendar.
- **`app.py`** - the Streamlit UI tying it together, with an editable table
  so you can fix anything before it goes anywhere near your account.

## Important caveats (read before relying on this)

- **This uses an unofficial, reverse-engineered Garmin Connect API.**
  It isn't Garmin's public developer API - it works by mimicking Garmin's own
  apps. It can break when Garmin changes something server-side, and it's not
  officially sanctioned, so use at your own judgment.
- **On Python 3.11, every workout type is pushed as a hand-built raw JSON
  payload**, not just strength. The step-type / end-condition / target-type
  numeric IDs in `garmin_client.py` (`WORKOUT_STEP_TYPE`, `END_CONDITION`,
  `TARGET_TYPE`) are best-effort values seen across community
  reverse-engineering projects, not something Garmin publishes or guarantees.
  Use the **"Show raw Garmin payload (debug)"** panel in the app before
  pushing anything important, and check the actual workout in Garmin Connect
  afterward to confirm steps/targets came through as expected. If a value
  looks wrong, the README section above on `garmin_client.py`'s docstring
  explains how to fetch a known-good workout back from Garmin Connect and
  correct the constant tables for your account.
- **If a push fails outright or looks wrong**, use the **Download draft as
  JSON** button to see exactly what was planned, and enter it by hand into
  Garmin Connect's own workout builder (Training > Workouts > Create a
  Workout) - that path always works regardless of any issues here.
- **"Stairs"** is mapped to Garmin's "fitness equipment" sport type (there's
  no dedicated stair-machine type), targeted by heart rate or cadence.
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

## Deploying (GitHub + share.streamlit.io)

The app has no server-side secrets of its own - Garmin credentials are typed
into the sidebar each session, not baked into the deployment - so putting it
on [Streamlit Community Cloud](https://share.streamlit.io) is mostly just
"push to GitHub, point Streamlit at it."

1. **Push this repo to GitHub** (`.gitignore` already excludes `.env`,
   `.venv/`, and other local-only files - double check `git status` doesn't
   show `.env` before your first commit/push regardless).
2. Go to [share.streamlit.io](https://share.streamlit.io), **New app**, and
   pick this repo/branch with `app.py` as the main file.
3. **Python version:** this app targets Python 3.11 (see above) - a
   `.python-version` file is included so Streamlit Cloud should pick it up
   automatically; otherwise select 3.11 explicitly in the app's Advanced
   settings.
4. **Secrets:** leave the Secrets box empty. There's nothing required for the
   app to boot, and see the warning below on why you shouldn't add Garmin
   credentials there.

### Read this before sharing the deployed URL with anyone

- **Do not add `GARMIN_EMAIL` / `GARMIN_PASSWORD` as Streamlit Cloud
  secrets on a shared deployment.** Locally, those env vars just prefill the
  sidebar fields for your own convenience. On a public deployment, that
  prefill would show up for *every visitor* - anyone who opens the URL would
  see your Garmin email and a filled-in password field, and could click
  "Log in to Garmin" and push workouts to (or otherwise act on) **your**
  Garmin account without ever knowing the password themselves. Leave those
  two secrets unset on Streamlit Cloud; have each person type in their own
  Garmin credentials in the sidebar every session instead.
- **Garmin login tokens are cached per browser session, not shared.** All
  visitors to a Streamlit Community Cloud app share the same server process
  and filesystem, so a naive fixed token-cache path (the `garminconnect`
  library's own default, `~/.garminconnect/`) would let one visitor's cached
  Garmin login leak into another visitor's session. `app.py` works around
  this by giving each browser session its own temporary token directory -
  don't reintroduce a shared fixed path if you modify the login code.
- **This is an unofficial, reverse-engineered Garmin integration**, not
  Garmin's sanctioned OAuth flow - treat a public deployment as something to
  share with people you trust (training partners, a coach, etc.), not as a
  fully public, anonymous-friendly tool.

## Extending it

- Want a multi-week plan pushed in one go? Just ask Claude for several
  workouts with different `date` values in one CSV - the app already loops
  over `plan.workouts` and has a "Push ALL" button.
- Want pace/power auto-computed from a goal race time or FTP test? Mention
  that when you prompt Claude Desktop, referencing the column format above.
