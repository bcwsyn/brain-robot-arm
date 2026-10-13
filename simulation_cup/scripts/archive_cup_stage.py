#!/usr/bin/env python3
"""Preserve all dataset/training revisions, splitting archives below GitHub's file limit."""
import hashlib
import json
from pathlib import Path
import tarfile


def main():
    workspace = Path(__file__).resolve().parents[1]
    destination = workspace/'validation/cup_vision/archives'
    if destination.exists():
        raise RuntimeError('archive destination already exists; preserve it and choose a new revision')
    destination.mkdir()
    backups = workspace/'artifacts/cup_training_backups'
    backups.mkdir(exist_ok=True)
    entries = []
    for name in ['dataset_v1', 'dataset_v2', 'final_test_v2', 'train_v1', 'train_v2']:
        source = workspace/'artifacts/cup_training'/name
        archive = backups/f'{name}.tar.gz'
        if archive.exists():
            raise RuntimeError('backup already exists: '+str(archive))
        with tarfile.open(archive, 'w:gz', compresslevel=6) as target:
            target.add(source, arcname=name)
        parts = []
        with archive.open('rb') as stream:
            index = 0
            while True:
                content = stream.read(45*1024*1024)
                if not content:
                    break
                path = destination/f'{name}.tar.gz.part{index:03d}'
                path.write_bytes(content)
                parts.append(dict(file=path.name, bytes=len(content), sha256=hashlib.sha256(content).hexdigest()))
                index += 1
        entries.append(dict(bundle=name, top_directory=name,
            archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), parts=parts))
        print(name, archive.stat().st_size, 'bytes,', len(parts), 'parts', flush=True)
    sessions = workspace/'artifacts/cup_training_backups/physics_sessions.tar.gz'
    regression = json.loads((workspace/'validation/cup_vision/gripper_alignment/regression_results.json').read_text())
    with tarfile.open(sessions, 'w:gz') as archive:
        for trial in regression['trials']:
            source = workspace.parent/trial['session_path']
            archive.add(source, arcname='physics_sessions/'+source.name)
    path = destination/'physics_sessions.tar.gz.part000'
    path.write_bytes(sessions.read_bytes())
    entries.append(dict(bundle='physics_sessions', top_directory='physics_sessions',
        archive_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        parts=[dict(file=path.name, bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())]))
    (destination/'archive_manifest.json').write_text(json.dumps(dict(version=1,
        description='All raw datasets, annotations, training revisions, checkpoints, metrics and physical regression sessions',
        entries=entries), indent=2)+'\n')
    (destination/'SHA256SUMS').write_text(''.join(f"{part['sha256']}  {part['file']}\n" for entry in entries for part in entry['parts']))


if __name__ == '__main__':
    main()
