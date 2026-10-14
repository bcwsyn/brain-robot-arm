#!/usr/bin/env python3
"""Archive selected stage sessions/training/evidence with per-file SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

WS = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def split_archive(path, maximum_bytes=45*1024*1024):
    parts = []
    with path.open('rb') as source:
        index = 1
        while True:
            payload = source.read(maximum_bytes)
            if not payload:
                break
            part = path.with_name(path.name+f'.part{index:03d}')
            with part.open('xb') as target:
                target.write(payload)
            parts.append(dict(file=part.name, size=part.stat().st_size, sha256=digest(part)))
            index += 1
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    paths = []
    roots = [*args.session, WS/'artifacts/cup_rl', WS/'validation/stage6_random_rl']
    for root in roots:
        root = root.resolve()
        if not root.is_relative_to(WS) or not root.is_dir():
            raise ValueError('Archive inputs must be existing workspace directories')
        for path in root.rglob('*'):
            if path.is_relative_to(output) or '__pycache__' in path.parts:
                continue
            if path.is_symlink():
                raise ValueError('Do not archive symlinks')
            if path.is_file():
                paths.append(path)
    paths = sorted(set(paths))
    records = []
    archive_path = output/'stage6_data.tar.gz'
    with tarfile.open(archive_path, 'w:gz') as archive:
        for path in paths:
            name = path.relative_to(WS).as_posix()
            records.append(dict(path=name, size=path.stat().st_size, sha256=digest(path)))
            archive.add(path, arcname=name, recursive=False)
    manifest = dict(schema_version=1, file_count=len(records), files=records,
                    archive=archive_path.name, archive_size=archive_path.stat().st_size,
                    archive_sha256=digest(archive_path),
                    scope='all selected failed/successful sessions, prototypes, frozen training, replay and evidence')
    manifest['parts'] = split_archive(archive_path)
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(f"{p['sha256']}  {p['file']}\n" for p in manifest['parts']))
    print('Archived', len(records), 'files;', manifest['archive_size'], 'bytes;', output)


if __name__ == '__main__':
    main()
