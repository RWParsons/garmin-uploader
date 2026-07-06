"""A starter CSV template matching csv_import.py's expected column format,
plus the ready-made prompt for getting an LLM to draft one.

See README.md for the full CSV column spec. Keep LLM_PROMPT_TEMPLATE in sync
with the "Prompt template" section there - it's the same text, just also
served from the app's own "How to" page so users don't need to go find the
README to draft a plan.
"""

LLM_PROMPT_TEMPLATE = """You are drafting a training plan as a CSV file for me to upload to a workout-planning app. Create the file (don't just print it in chat) with EXACTLY these column headers, in this order:

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
"""

CSV_TEMPLATE = """workout_name,sport,date,workout_notes,item_order,repeat_group,repeat_count,step_type,duration_type,duration_value,target_type,target_low,target_high,item_note,exercise_name,sets,reps,weight_kg,rest_seconds
Easy Run,running,,Easy 30 min Zone 2 run,1,,,warmup,time,300,heart_rate,120,140,,,,,,
Easy Run,running,,Easy 30 min Zone 2 run,2,,,interval,time,1800,heart_rate,130,150,,,,,,
Easy Run,running,,Easy 30 min Zone 2 run,3,,,cooldown,time,300,heart_rate,110,130,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,1,,,warmup,time,600,heart_rate,120,140,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,2,intervals,6,interval,distance,400,pace,195,205,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,3,intervals,6,recovery,time,90,none,,,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,4,,,cooldown,time,600,heart_rate,110,130,,,,,,
FTP Intervals,cycling,,4x8min @ FTP,1,,,warmup,time,600,none,,,,,,,,
FTP Intervals,cycling,,4x8min @ FTP,2,intervals,4,interval,time,480,power,200,220,,,,,,
FTP Intervals,cycling,,4x8min @ FTP,3,intervals,4,recovery,time,240,power,100,120,,,,,,
FTP Intervals,cycling,,4x8min @ FTP,4,,,cooldown,time,600,none,,,,,,,,
Swim Endurance,swimming,,10x100m steady,1,,,warmup,distance,200,none,,,,,,,,
Swim Endurance,swimming,,10x100m steady,2,lengths,10,interval,distance,100,pace,90,95,,,,,,
Swim Endurance,swimming,,10x100m steady,3,lengths,10,recovery,time,20,none,,,,,,,,
Swim Endurance,swimming,,10x100m steady,4,,,cooldown,distance,200,none,,,,,,,,
HIIT Circuit,hiit,,8x30s max effort,1,,,warmup,time,300,heart_rate,110,130,,,,,,
HIIT Circuit,hiit,,8x30s max effort,2,rounds,8,interval,time,30,heart_rate,160,180,,,,,,
HIIT Circuit,hiit,,8x30s max effort,3,rounds,8,recovery,time,90,heart_rate,110,130,,,,,,
HIIT Circuit,hiit,,8x30s max effort,4,,,cooldown,time,300,none,,,,,,,,
Full Body Strength,strength,,45 min full body,1,,,,,,,,,,Back Squat,4,8,60,120
Full Body Strength,strength,,45 min full body,2,,,,,,,,,,Bench Press,4,8,40,120
Full Body Strength,strength,,45 min full body,3,,,,,,,,,,Barbell Row,3,10,35,90
Morning Yoga Flow,yoga,,20 min flexibility flow,1,,,,,,,,,Hold 45s each side,Warrior II,2,1,,
Morning Yoga Flow,yoga,,20 min flexibility flow,2,,,,,,,,,Hold 60s,Downward Dog,1,1,,
"""
