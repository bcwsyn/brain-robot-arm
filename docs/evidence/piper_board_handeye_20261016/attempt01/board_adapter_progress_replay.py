"""Replay the unchanged deployed adapter endpoint method; no robot imports."""
import ast,hashlib,json,math,types
from pathlib import Path
ROOT=Path('/home/johnwick/brain_robot_logs/board_handeye_20261016.2dE1Aj')
source=Path('/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/piper_jog_adapter.py')
text=source.read_text();module=ast.parse(text)
cls=next(n for n in module.body if isinstance(n,ast.ClassDef) and n.name=='PiperJogAdapter')
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_apply_trajectory')
space={};exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),str(source),'exec'),space)
trajectory=types.SimpleNamespace(joint_names=['joint4'],points=[types.SimpleNamespace(positions=[-.074293996],time_from_start=types.SimpleNamespace(sec=0,nanosec=0))])
dummy=types.SimpleNamespace(trajectory=trajectory,trajectory_start=0.,max_velocity=.189,
    joint_names=['joint4'],joint_min=[-.8],joint_max=[.8],positions={'joint4':0.},targets={'joint4':0.})
outputs=[]
for i in range(50):
    active=space['_apply_trajectory'](dummy,100+i*.02,.02)
    outputs.append(dummy.targets['joint4'])
assert all(abs(v+.00378)<1e-12 for v in outputs) and active
report={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'adapter_modified':False,
    'deployed_adapter_SHA256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'exact_deployed_method_AST_reused':True,'synthetic_feedback_stays_zero_NOT_hardware_deadband_measurement':True,
    'desired_J4_rad':-.074293996,'simulated_dt_s':.02,'original_max_velocity_rad_s':.189,
    'calls':50,'output_min_rad':min(outputs),'output_max_rad':max(outputs),
    'output_at_50th_tick_rad':outputs[-1],'goal_still_unreached':active,
    'conclusion':'With unchanged feedback the existing method reanchors every tick and never accumulates command beyond one step; actual actuator response to those small steps is not diagnosed by this replay.',
    'proposed_next_work':'Request narrowly scoped adapter progress exception: offline compare bounded accumulation only during fresh feedback, preserve velocity/limits and reset the command anchor across feedback gaps; no deployment or motion yet.'}
with (ROOT/'adapter_endpoint_replay.json').open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(report))
