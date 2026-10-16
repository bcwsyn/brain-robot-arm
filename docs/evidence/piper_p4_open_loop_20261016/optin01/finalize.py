"""Verify scoped deployment/evidence and copy only this attempt's text records."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent
repo = Path('/mnt/hgfs/ub')
dest = repo / 'docs/evidence/piper_p4_open_loop_20261016/optin01'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


preview = json.loads((root / 'preview_result.json').read_text())
assert preview['passed'] and preview['execute_after_estop_rejected']
assert preview['legacy_state_matched_subscribers'] >= 1
assert not any(preview['planning_commands_before_test_estop'].values())
assert all(preview['commands'][k] == 0 for k in ('arm', 'gripper', 'joint_commands'))
assert '128 passed' in (root / 'pytest_final.log').read_text()
assert '[  PASSED  ] 13 tests.' in (root / 'geometry_gtest.log').read_text()
pairs = [
    ('brain_robot_arm/scripts/start_brain_robot_cube_real.sh', '/home/johnwick/start_brain_robot_cube_real.sh'),
    ('brain_robot_arm/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp', '/home/johnwick/piper_ws/src/brain_robot_pick_place/src/grasp_lift_executor.cpp'),
    ('brain_robot_arm/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py', '/home/johnwick/piper_ws/src/brain_robot_ball_pick/launch/cube_visual_search.launch.py'),
    ('brain_robot_arm/piper_ws/src/brain_robot_pick_place/CMakeLists.txt', '/home/johnwick/piper_ws/src/brain_robot_pick_place/CMakeLists.txt'),
    ('brain_robot_arm/piper_ws/src/brain_robot_pick_place/scripts/prepare_p4_board_target.py', '/home/johnwick/piper_ws/src/brain_robot_pick_place/scripts/prepare_p4_board_target.py'),
]
deployed = []
for canonical, active in pairs:
    assert sha(repo / canonical) == sha(active), (canonical, active)
    deployed.append({'canonical': canonical, 'active': active, 'sha256': sha(active)})
baseline = json.loads((repo / 'docs/evidence/piper_board_handeye_20261016/internal_tf_pair01/production_SHA_after.json').read_text())
unchanged = {p: digest for p, digest in baseline.items()
             if p.endswith(('cube_task_real.yaml', 'cube_detector.yaml', 'piper_jog_adapter.py'))}
for path, digest in unchanged.items():
    assert sha(path) == digest, path
astra_src = '/home/johnwick/ros2_ws/src/astra_camera/src/ob_camera_node.cpp'
astra_lib = '/home/johnwick/ros2_ws/install/astra_camera/lib/libastra_camera.so'
assert sha(astra_src) == 'e916a45172dd6fc413a9652b61a438fe20049eda73ea5fbfd26865f5a080969b'
assert sha(astra_lib) == '7dfeab6f3d61e27355abb5fdeebcde4d84f59c463ac54d23201deab8ac384911'
before = {p.name: sha(p) for p in root.iterdir() if '.before.' in p.name}
installed = Path('/home/johnwick/piper_ws/install/brain_robot_pick_place/lib/brain_robot_pick_place/grasp_lift_executor')
verification = {
    'baseline_commit': '8a90b00', 'implementation_approved': True,
    'real_arm_executed': False, 'actual_new_executor_isolated_preview_passed': True,
    'python_tests': 128, 'original_geometry_tests': 13,
    'synchronized_sources': deployed, 'unchanged_protected_files': unchanged,
    'unchanged_astra_source_sha256': sha(astra_src), 'unchanged_astra_library_sha256': sha(astra_lib),
    'installed_executor_resolves_to': str(installed.resolve()),
    'new_executor_binary_sha256': sha(installed), 'local_before_backups': before,
    'rollback_baseline': '8a90b00, preserving the approved paired Astra/mount fix',
    'raw_nominal_target_source_is_static_snapshot_not_fresh_hardware_data': True,
    'git_publication': 'local only, existing divergence/review blocker unchanged',
}
for name in ('build.log', 'build_final.log', 'build_final_estop.log', 'pytest.log',
             'pytest_final.log', 'geometry_gtest.log', 'frozen_target.yaml', 'preview_result.json',
             'fixture.log', 'nodes.log', 'execution.json', 'run_preview.py', 'finalize.py'):
    shutil.copy2(root / name, dest / name)
for name in ('initial_preview_qos_mismatch', 'preview_before_estop_check'):
    shutil.copytree(root / name, dest / name, dirs_exist_ok=True)
(dest / 'verification.json').write_text(json.dumps(verification, indent=2) + '\n')
assets = [{'path': str(p.relative_to(dest)), 'bytes': p.stat().st_size, 'sha256': sha(p)}
          for p in sorted(dest.rglob('*')) if p.is_file() and p.name != 'manifest.json']
(dest / 'manifest.json').write_text(json.dumps({'files': assets, 'no_binary_artifacts': True}, indent=2) + '\n')
print(json.dumps({'files': len(assets), 'bytes': sum(a['bytes'] for a in assets),
                  'executor_sha256': sha(installed), 'unchanged_files': len(unchanged),
                  'evidence': str(dest)}))
