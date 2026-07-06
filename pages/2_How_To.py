"""Streamlit page: a user-facing walkthrough of how to use this app, plus
the ready-made LLM prompt for drafting a workout CSV.

For repo/dev-facing documentation (file layout, setup, deploying), see
README.md instead - this page is deliberately narrower, aimed at someone
using the running app rather than maintaining its code.
"""
from __future__ import annotations

import streamlit as st

from garmin_session import render_garmin_login_sidebar
from prompt_templates import CSV_TEMPLATE, LLM_PROMPT_TEMPLATE

render_garmin_login_sidebar()

st.title("❓ How to use this app")
st.caption(
    "Draft a plan with an LLM, upload it, review/push to Garmin, then manage what's "
    "already on your Garmin calendar - all from the two other pages in the sidebar."
)

st.subheader("1. Draft a plan with an LLM")
st.markdown(
    "Paste the prompt below into Claude Desktop, claude.ai, ChatGPT, or any other LLM "
    "chat, filling in your athlete profile and what you want at the bottom. Ask it to "
    "**create the CSV as a file** (not just print it in the chat), then download that "
    "file - you'll upload it in step 2."
)
st.download_button(
    "⬇️ Download this prompt as a text file",
    data=LLM_PROMPT_TEMPLATE,
    file_name="garmin_planner_prompt.txt",
    mime="text/plain",
)
st.code(LLM_PROMPT_TEMPLATE, language="text")

with st.expander("📋 CSV column format (if you're writing or editing a CSV by hand)"):
    st.markdown(
        """
Columns, in order:

```
workout_name,sport,date,workout_notes,item_order,repeat_group,repeat_count,step_type,duration_type,duration_value,target_type,target_low,target_high,item_note,exercise_name,sets,reps,weight_kg,rest_seconds
```

- One row = one cardio step OR one named exercise.
- `sport` is one of: `running`, `cycling`, `swimming`, `cardio` (general
  cardio equipment - stair-stepper, elliptical, rower, etc.; `stairs` also
  works as an alias), `hiit`, `strength`, `yoga`, `pilates`.
  `strength`/`yoga`/`pilates` are exercise-based (named exercises with
  sets/reps/weight); every other sport is step-based (structured
  steps with a duration and target).
- `date` is `YYYY-MM-DD` or blank (blank = schedule it yourself later, from
  the calendar on the Upload workouts page or by hand in Garmin Connect).
- `item_order` is an integer giving the order of items within a workout
  (1, 2, 3, ...).
- For step-based sports, fill: `step_type` (warmup/interval/recovery/
  cooldown/rest), `duration_type` (time/distance/calories), `duration_value`
  (seconds if time, meters if distance, kcal if calories), `target_type`
  (none/pace/speed/power/heart_rate/cadence), `target_low`, `target_high`.
  Leave `exercise_name`/`sets`/`reps`/`weight_kg`/`rest_seconds` blank on
  these rows.
- For exercise-based sports, fill: `exercise_name`, `sets`, `reps`,
  `weight_kg` (blank if bodyweight), `rest_seconds`. Leave
  `step_type`/`duration_type`/`duration_value`/`target_type`/`target_low`/`target_high`
  blank on these rows. For yoga/pilates, `reps` is usually `1` per pose/hold
  and the hold duration goes in `item_note` (e.g. "Hold 45s").
- To make a set of steps repeat (e.g. 6x400m intervals), give those rows the
  same `repeat_group` value (any short label, unique per repeated block) and
  put the number of repeats in `repeat_count` on each of those rows. Leave
  `repeat_group` blank for steps that don't repeat.
- Target units: pace in **seconds-per-km**, speed in km/h, power in watts,
  heart rate in bpm, cadence in rpm (bike) or steps/min (cardio equipment).
- Put a short description of the whole workout in `workout_notes` (repeat it
  on every row for that workout, or just the first row).
"""
    )
    st.caption("Here's a full example CSV showing the format above in practice:")
    st.download_button(
        "⬇️ Download example CSV",
        data=CSV_TEMPLATE,
        file_name="workout_template.csv",
        mime="text/csv",
    )
    st.code(CSV_TEMPLATE, language="text")

st.divider()
st.subheader("2. Upload, review, and push (Upload workouts page)")
st.markdown(
    """
- **Upload the CSV** you got from the LLM (or edited by hand).
- **Calendar view** shows every workout in the draft that has a date set.
  Click a workout to see its steps and push just that one, tick checkboxes
  to select several, or use **Push ALL workouts on the calendar** /
  **Delete selected** to act on the whole batch at once. Selecting and
  deleting here only affects your local draft - nothing touches Garmin
  until you push.
- **Review / edit individual workouts** (collapsed by default) lets you
  tweak a workout's name, date, steps, or exercises before pushing, and has
  a **Push ALL workouts above** button that pushes everything in the draft
  (including workouts with no date set yet - they land in your Garmin
  workout library unscheduled).
- Use **⬇️ Download draft as JSON** any time to see exactly what would be
  sent, without pushing anything.
"""
)

st.divider()
st.subheader("3. Manage what's already on Garmin (Manage workouts page)")
st.markdown(
    """
**📅 Calendar tab** - what's actually scheduled on your Garmin Connect
calendar, month by month:
- Click a workout to view its steps (Garmin Coach / adaptive-training
  workouts show a note instead, since Garmin doesn't expose their step
  detail the same way as workouts built in the library).
- Tick checkboxes (or **Select all**) and **Delete selected** to unschedule
  workouts from the calendar - this only removes them from that date, it
  does **not** delete them from your workout library, and selections only
  ever apply to the month you're currently viewing.
- **Delete ALL future workouts** scans ahead (up to 12 months) and shows you
  exactly what it found before asking you to confirm - same "unschedule,
  don't delete" behavior, just across every future month at once.
- **🔄 Refresh from Garmin** re-fetches the currently viewed month, in case
  you changed something in the Garmin Connect app itself.

**📋 Library tab** - your saved workout templates, regardless of whether
they're scheduled anywhere:
- **✏️ Load for editing** fetches a workout's full detail into the same
  editor used on the Upload workouts page.
- **💾 Update on Garmin (replace)** uploads your edited version as a new
  workout, then deletes the old one - Garmin's API has no in-place edit, so
  the workout gets a new ID as a result.
- **🗑️ Delete** (one at a time, or select several with the checkboxes /
  **Select all** and **Delete selected**) removes a workout from your
  library entirely.
"""
)

st.divider()
st.subheader("Good to know")
st.markdown(
    """
- This uses an **unofficial, reverse-engineered** Garmin Connect API (there's
  no official public one for this) - it can occasionally break or behave
  oddly if Garmin changes something server-side. If a pushed workout looks
  wrong, check the **"🔍 Show raw Garmin payload (debug)"** panel before and
  after pushing, and compare against what actually shows up in Garmin
  Connect.
- If your Garmin account has **MFA**, the first login attempt will fail
  asking for a code - enter it in the sidebar field and click "Log in to
  Garmin" again.
- If a push ever fails outright or looks wrong, **⬇️ Download draft as
  JSON** on the Upload workouts page shows exactly what was planned, and you
  can always enter a workout by hand in Garmin Connect's own workout builder
  (Training > Workouts > Create a Workout) as a fallback.
"""
)
