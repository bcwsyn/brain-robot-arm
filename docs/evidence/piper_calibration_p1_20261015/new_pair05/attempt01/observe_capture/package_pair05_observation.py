"""Offline evidence packaging only. Does not import or connect hardware interfaces."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile

BASE = Path('/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015')
CAP = BASE / 'new_pair05_A_batch60.3MFdVm'
TEST = Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test')
OUT = BASE / 'new_pair05_published_observation'
OUT.mkdir(exist_ok=False)
config = '/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'

def run(name, args):
    result = subprocess.run(['/usr/bin/python3', str(TEST / name), *map(str,args)], capture_output=True, text=True)
    print(name, result.returncode, result.stdout[-1200:], result.stderr[-1500:], flush=True)
    if result.returncode:
        raise RuntimeError(name)

run('review_calibration_capture.py', ['--capture', CAP/'observation/batch_01', '--config', config, '--output', OUT/'review.json'])
run('export_calibration_bundle.py', ['--output', OUT/'portable', '--capture', CAP/'observation/batch_01', '--sample-id', 'new_pair05_attempt01_observe', '--observation-capture', 'batch_01', '--sdk', CAP/'sdk_static.json', '--camera-metadata', CAP/'A_factory.json', '--review', OUT/'review.json', '--detector-config', config, '--cube-edge-mm', '29'])
run('calibration_p0_quality.py', ['--bundle', OUT/'portable', '--capture-dir', 'batch_01', '--output', OUT/'quality'])
for source, target in [(CAP/'observation/p0_report.json','p0_report.json'),(CAP/'A_execution.json','capture_execution.json'),(BASE/'new_pair05_serialized_return.eaPC4t/execution_session.json','return_execution.json')]:
    shutil.copyfile(source, OUT/target)
sys.path.insert(0, str(TEST))
from export_calibration_bundle import verify_bundle
verify_bundle(OUT/'portable', json.loads((OUT/'portable/manifest.json').read_text()))
roots = [BASE/'new_pair05_recovered_readonly.nCsypV', BASE/'new_pair05_serialized_return.eaPC4t', BASE/'new_pair05_A_formal.gupm4v', CAP]
assets = []
with tarfile.open(OUT/'runtime_closed.tar.gz', 'w:gz') as archive:
    for root in roots:
        for source in sorted(root.rglob('*')):
            if source.is_file():
                if source.is_symlink():
                    raise ValueError(source)
                path = source.relative_to(BASE).as_posix()
                assets.append({'path':path,'bytes':source.stat().st_size,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
                archive.add(source, arcname=path, recursive=False)
with tarfile.open(OUT/'runtime_closed.tar.gz', 'r:gz') as archive:
    assert len(archive.getmembers()) == len(assets)
    for entry in assets:
        assert hashlib.sha256(archive.extractfile(entry['path']).read()).hexdigest() == entry['sha256']
manifest = {'schema':'piper_runtime_closed_archive_v1','files':assets,'archive_sha256':hashlib.sha256((OUT/'runtime_closed.tar.gz').read_bytes()).hexdigest(),'all_original_and_archived_SHA_verified':True}
(OUT/'runtime_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('VERIFIED', len(assets), 'raw files; exported assets',len(json.loads((OUT/'portable/manifest.json').read_text())['files']),flush=True)
