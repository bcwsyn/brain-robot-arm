"""Archive this closed run with per-member SHA-256 and bounded Git objects.

No original is removed. Raw logs and failed attempts retain their bytes.
"""
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path('/mnt/hgfs/ub')
DEST = REPO/'docs/evidence/piper_p4_real_20261016/attempt01'
DEST.mkdir(exist_ok=True, parents=True)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

old = json.loads((REPO/'docs/evidence/piper_p4_open_loop_20261016/optin01/verification.json').read_text())
checks = []
for pair in old['synchronized_sources']:
    canonical, active = REPO/pair['canonical'], Path(pair['active'])
    current = sha(active)
    is_launch = canonical.name == 'cube_visual_search.launch.py'
    assert sha(canonical) == current
    assert is_launch or current == pair['sha256']
    checks.append({'canonical': str(canonical), 'active': str(active), 'sha256': current,
        'identical_to_681a715': not is_launch,
        'approved_node_scoped_parameter_fix_64f878c': is_launch})
for path, expected in old['unchanged_protected_files'].items():
    assert sha(Path(path)) == expected
assert sha(Path('/home/johnwick/ros2_ws/src/astra_camera/src/ob_camera_node.cpp')) == old['unchanged_astra_source_sha256']
assert sha(Path('/home/johnwick/ros2_ws/install/astra_camera/lib/libastra_camera.so')) == old['unchanged_astra_library_sha256']
assert sha(Path(old['installed_executor_resolves_to'])) == old['new_executor_binary_sha256']
assert json.loads((ROOT/'real_finished.json').read_text())['entry_rc'] == 0
verification = {'code_baseline': '64f878c', 'synchronized_sources': checks,
    'protected_files_unchanged': old['unchanged_protected_files'],
    'astra_source_and_library_unchanged': True, 'executor_binary_unchanged_since_681a715': True,
    'complete_actual_entry_rc': 0, 'physical_grasp_succeeded': False,
    'closure_0p4mm_and_cube_remains_on_board': True,
    'further_motion_after_user_gripper_research_request': False,
    'production_speed_force_contact_offset_changes_adopted': False,
    'pure_offline_tests': 30, 'test_result': 'verification_pytest.xml',
    'git_publication': 'local only; existing shared-main divergence/history review unchanged'}
with (ROOT/'final_verification.json').open('x') as f:
    json.dump(verification, f, indent=2)

# Snapshot before creating archives; outputs live elsewhere, never recurse.
paths = sorted(p for p in ROOT.rglob('*') if p.is_file() and
    '__pycache__' not in p.parts and p.suffix != '.pyc')
parts = [[]]
size = 0
for path in paths:
    n = path.stat().st_size
    if parts[-1] and size+n > 32 << 20:
        parts.append([]); size = 0
    parts[-1].append(path); size += n
members = []
archives = []
for number, group in enumerate(parts, 1):
    target = DEST/f'runtime_{number:02d}.tar.gz'
    with tarfile.open(target, 'x:gz', compresslevel=6) as tf:
        for path in group:
            relative = str(path.relative_to(ROOT))
            tf.add(path, arcname=relative, recursive=False)
            members.append({'path': relative, 'bytes': path.stat().st_size,
                'sha256': sha(path), 'archive': target.name})
    by_name = {m['path']: m for m in members if m['archive'] == target.name}
    with tarfile.open(target, 'r:gz') as tf:
        assert len(tf.getmembers()) == len(group)
        for item in tf:
            data = tf.extractfile(item).read()
            assert len(data) == by_name[item.name]['bytes']
            assert hashlib.sha256(data).hexdigest() == by_name[item.name]['sha256']
    archives.append({'path': target.name, 'bytes': target.stat().st_size,
        'sha256': sha(target), 'verified_members': len(group)})

names = ['real_finished.json', 'final_verification.json', 'final_sdk.json', 'final_can.json',
    'frozen_target.yaml', 'fixed_board_plane_review.json', 'launch_parameter_probe.json',
    'actual_landing_review.json', 'manual_pair_geometry_review.json',
    'top_reference_and_board_replay.json', 'top_reference_and_board_replay_opening_seed.json',
    'gripper_trace_review_v2.json', 'verification_pytest.xml',
    'run_real.py', 'record_p4.py', 'verify_launch.py', 'refresh_fixed_target.py',
    'review_actual_landing.py', 'review_manual_pairs.py', 'review_top_and_landing.py',
    'review_gripper_trace.py', 'finalize_real_record.py', 'real_record/summary.json']
names += ['capture/evidence/0003_rgb.png', 'capture/evidence/0003_depth.png', '0003_debug_image.png']
for snapshot in [55, 61, 62, 64, 73]:
    for suffix in ['rgb', 'depth', 'color_debug', 'debug']:
        name = f'real_record/{snapshot:04d}_{suffix}.png'
        if (ROOT/name).exists():
            names.append(name)
loose = []
for name in names:
    source, target = ROOT/name, DEST/name
    target.parent.mkdir(parents=True, exist_ok=True)
    assert not target.exists()
    shutil.copy2(source, target)
    assert sha(source) == sha(target)
    loose.append({'path': name, 'bytes': target.stat().st_size, 'sha256': sha(target)})
manifest = {'runtime_root': str(ROOT), 'source_files': len(members),
    'source_bytes': sum(m['bytes'] for m in members), 'members': members,
    'archives': archives, 'loose_originals': loose,
    'originals_deleted': False, 'raw_images_or_logs_modified': False,
    'all_archive_members_read_back_and_SHA256_verified': True}
with (DEST/'runtime_manifest.json').open('x') as f:
    json.dump(manifest, f, indent=2)
print(json.dumps({'source_files': len(members), 'source_bytes': manifest['source_bytes'],
    'archive_bytes': sum(a['bytes'] for a in archives), 'archives': archives,
    'loose_originals': len(loose), 'all_readback_verified': True}))
