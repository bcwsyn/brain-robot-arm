"""Generate original bounded invocations with current paths/hash baselines only."""
from pathlib import Path
import ast
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
observe = ROOT/'observe'
observe.mkdir(exist_ok=False)
original = REPO/'docs/evidence/piper_calibration_p1_20261015/board_observe'
baseline = json.loads((REPO/'docs/evidence/piper_board_handeye_20261016/j4_roundtrip01/production_SHA_after.json').read_text())
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == value for p, value in baseline.items())
(ROOT/'approved_baseline.json').write_text(json.dumps(baseline, indent=2)+'\n')
shutil.copyfile(original/'original_observe_launch.py', observe/'original_observe_launch.py')
source = (original/'piper_board_return_observe.py').read_text()
replacements = {
    "ROOT=Path(tempfile.mkdtemp(prefix='piper_board_return_observe.',dir='/home/johnwick/brain_robot_logs'))": f'ROOT=Path({str(observe)!r})',
    "FROZEN=Path('/mnt/hgfs/ub/docs/evidence/piper_calibration_p1_20261015/board_open_only/production_SHA_before.json')": f'FROZEN=Path({str(ROOT/"approved_baseline.json")!r})',
    "LAUNCH=Path('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015/new_pair06_after_manual_reset.NBs3LK/original_observe_launch.py')": f'LAUNCH=Path({str(observe/"original_observe_launch.py")!r})',
    "assert report['adapter_sha256']=='a5074c614fcc1b7f57854e2693e689337577567dde0ca7765470df52fa1347d8'": "assert report['adapter_sha256']=='5c1c1be24b4519705ae1e58a31e26085a9c1832cdd7626e93f6c6392b621a172'",
    "'candidate_deployed':False": "'candidate_deployed':True",
    "'operator_quote':'允许：沿已有轨迹返回观测姿态，只拍完整棋盘格，并在SEARCH前停止；不再开闭夹爪、不搜索或抓取'": "'operator_quote':'好，你自行完成，等真的需要我实机操作的时候再叫我；承接恢复观测与已批准棋盘格采样，不抓取/不改生产TF'",
}
for old, new in replacements.items():
    assert source.count(old) == 1, old
    source = source.replace(old, new)
ast.parse(source)
(observe/'executed_return.py').write_text(source)
(ROOT/'authorization.json').write_text(json.dumps({
    'operator_quote': '好，你自行完成，等真的需要我实机操作的时候再叫我',
    'prior_route_approval': '121d1ef board9fit1heldout proposal already approved',
    'new_instruction_context': 'After J4 success, resume existing observation and board sampling workflow autonomously.',
    'motion_scope': 'Existing current-to-fixed-observation trajectory, stop before SEARCH; approved bounded board9fit1heldout wrist poses only after fresh board/plan checks.',
    'frozen': 'Production TF/TCP, limits, detector/grasp/search code and parameters unchanged.',
    'not_authorized': 'Firmware, MasterSlaveConfig, ResetPiper, hardware disable, search/grasp, TF deployment.',
    'invocation_changes': replacements,
    'original_observe_source': str(original/'piper_board_return_observe.py'),
    'source_SHA256': hashlib.sha256(source.encode()).hexdigest()
}, indent=2, ensure_ascii=False)+'\n')
print(observe/'executed_return.py')
