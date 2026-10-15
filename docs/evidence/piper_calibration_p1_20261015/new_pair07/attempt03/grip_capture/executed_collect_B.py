"""Reuse the exact successful five-frame passive capture; no robot controls."""
from pathlib import Path
import hashlib,json,subprocess,tempfile,time
repo=Path('/mnt/hgfs/ub')
root=Path(tempfile.mkdtemp(prefix='new_pair07_attempt03_B.',dir='/home/johnwick/brain_robot_logs'))
source=repo/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt01/grip_capture/executed_preview.py'
baseline=json.loads((repo/'docs/evidence/piper_calibration_p1_20261015/new_pair07/attempt03/observe_capture/production_SHA_before.json').read_text())
def hashes():return {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in baseline}
before=hashes();assert before==baseline, 'Production changed; stop before device access'
(root/'production_SHA_before.json').write_text(json.dumps(before,indent=2))
print(root,flush=True)
with (root/'capture_stdout.log').open('xb') as stream:
 start=time.time()
 result=subprocess.run(['/usr/bin/python3',str(source)],stdout=stream,stderr=subprocess.STDOUT,timeout=55)
text=(root/'capture_stdout.log').read_text()
runtime=Path(text.splitlines()[0]);assert runtime.is_dir() and runtime.parent==root.parent
after=hashes()
(root/'production_SHA_after.json').write_text(json.dumps(after,indent=2))
record={'runtime':str(runtime),'returncode':result.returncode,'elapsed_s':time.time()-start,
 'executed_source':str(source),'executed_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'production_unchanged':before==after,'actual_role':'new_pair07_attempt03_grip_B',
 'source_labels_preserved':'Original reusable wrapper says preview/Afalse/Bfalse; actual B role comes from current workflow and operator contact/same-point confirmation, not those old labels'}
(root/'B_execution.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record),flush=True)
raise SystemExit(result.returncode)
