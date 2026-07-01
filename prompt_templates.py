"""A starter CSV template matching csv_import.py's expected column format.

See README.md for the full CSV column spec.
"""

CSV_TEMPLATE = """workout_name,sport,date,workout_notes,item_order,repeat_group,repeat_count,step_type,duration_type,duration_value,target_type,target_low,target_high,item_note,exercise_name,sets,reps,weight_kg,rest_seconds
Easy Run,running,,Easy 30 min Zone 2 run,1,,,warmup,time,300,heart_rate,120,140,,,,,,
Easy Run,running,,Easy 30 min Zone 2 run,2,,,interval,time,1800,heart_rate,130,150,,,,,,
Easy Run,running,,Easy 30 min Zone 2 run,3,,,cooldown,time,300,heart_rate,110,130,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,1,,,warmup,time,600,heart_rate,120,140,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,2,intervals,6,interval,distance,400,pace,195,205,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,3,intervals,6,recovery,time,90,none,,,,,,,,
VO2 Intervals,running,,6x400m @ VO2max pace,4,,,cooldown,time,600,heart_rate,110,130,,,,,,
Full Body Strength,strength,,45 min full body,1,,,,,,,,,,Back Squat,4,8,60,120
Full Body Strength,strength,,45 min full body,2,,,,,,,,,,Bench Press,4,8,40,120
Full Body Strength,strength,,45 min full body,3,,,,,,,,,,Barbell Row,3,10,35,90
"""
