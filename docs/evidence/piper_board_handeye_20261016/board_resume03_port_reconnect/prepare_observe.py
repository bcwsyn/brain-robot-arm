"""Repoint the previously audited original observation invocation only."""
from pathlib import Path
import ast
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
BASE=REPO/'docs/evidence/piper_board_handeye_20261016/board_resume02_host_reconnect/observe_after_host_reconnect'
OUT=ROOT/'observe'
pre=json.loads((ROOT/'port_preflight.json').read_text())
assert pre['passive_frames_5s']>0 and all(n>0 for n in pre['per_second_frames']) and not pre.get('error')
OUT.mkdir(exist_ok=False)
source=(BASE/'executed_return.py').read_text()
oldroot='/home/johnwick/brain_robot_logs/board_resume_20261016.SUhpfy/observe_after_host_reconnect'
assert source.count(oldroot)==2
source=source.replace(oldroot,str(OUT))
ast.parse(source)
(OUT/'executed_return.py').write_text(source)
shutil.copyfile(BASE/'original_observe_launch.py',OUT/'original_observe_launch.py')
(ROOT/'authorization.json').write_text(json.dumps({'operator_quote':'已完成','context':'Confirmed requested host physical USB port change/reconnect; continue previously authorized observation and board workflow',
    'scope':'Original current-to-fixed-observe, stop before SEARCH. Original approved board9fit1heldout only after actual observe and fresh image checks.',
    'not_authorized':'Production TF, grasp/search/detection logic or thresholds, limits, firmware, reset, hardware disable',
    'invocation_change':'ROOT/LAUNCH paths only; original SDK static check and fault recognition retained',
    'source_reference':str(BASE/'executed_return.py'),'reference_SHA256':hashlib.sha256((BASE/'executed_return.py').read_bytes()).hexdigest(),'executed_SHA256':hashlib.sha256(source.encode()).hexdigest()},indent=2,ensure_ascii=False)+'\n')
print(OUT/'executed_return.py')
