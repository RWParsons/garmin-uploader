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
