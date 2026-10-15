"""Run the existing passive5-frame capture for a newly placed board."""
from pathlib import Path
import hashlib,json,subprocess,tempfile,time
repo=Path('/mnt/hgfs/ub')
root=Path(tempfile.mkdtemp(prefix='piper_board_full_observation.',dir='/home/johnwick/brain_robot_logs'))
source=repo/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt01/grip_capture/executed_preview.py'
baseline=json.loads((repo/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt03/observe_capture/production_SHA_before.json').read_text())
def hashes():return {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in baseline}
before=hashes();assert before==baseline, 'Production changed; stop before device access'
(root/'production_SHA_before.json').write_text(json.dumps(before,indent=2))
print(root,flush=True)
with (root/'capture_stdout.log').open('xb') as stream:
 started=time.time();result=subprocess.run(['/usr/bin/python3',str(source)],stdout=stream,stderr=subprocess.STDOUT,timeout=55)
lines=(root/'capture_stdout.log').read_text().splitlines()
runtime=Path(lines[0]);assert runtime.is_dir() and runtime.parent==root.parent
after=hashes();(root/'production_SHA_after.json').write_text(json.dumps(after,indent=2))
record={'runtime':str(runtime),'returncode':result.returncode,'elapsed_s':time.time()-started,
 'actual_role':'stationary_board_after_authorized_observe_not_A_or_B_or_hand_eye_calibration',
 'executed_source':str(source),'executed_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'production_unchanged':before==after,'user_board_laid_confirmed':True,'user_cube_removed_confirmed':True,
 'user_square_size_mm':32,'board_type_and_full_grid_dimensions_not_yet_confirmed':True,
 'original_preview_labels_preserved':True,'robot_motion_or_gripper_commands_sent':False}
(root/'board_execution.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record),flush=True)
raise SystemExit(result.returncode)
