#!/usr/bin/env python3
"""Restore and verify a complete stage archive into a NEW directory only."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.archive_directory/'manifest.json').read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    archive_path = args.archive_directory/manifest['archive']
    if not archive_path.is_file():
        archive_path = args.output/'combined-stage6.tar.gz'
        with archive_path.open('xb') as target:
            for part in manifest['parts']:
                name = PurePosixPath(part['file'])
                if name.is_absolute() or len(name.parts) != 1:
                    raise ValueError('Invalid archive part name')
                source_path = args.archive_directory/part['file']
                if source_path.stat().st_size != part['size'] or digest(source_path) != part['sha256']:
                    raise ValueError('Archive part SHA-256 mismatch')
                with source_path.open('rb') as source:
                    shutil.copyfileobj(source, target)
    if digest(archive_path) != manifest['archive_sha256']:
        raise ValueError('Archive SHA-256 mismatch')
    expected = {f['path']: f for f in manifest['files']}
    if len(expected) != manifest['file_count']:
        raise ValueError('Duplicate manifest paths')
    found = set()
    with tarfile.open(archive_path, 'r:gz') as archive:
        for member in archive:
            relative = PurePosixPath(member.name)
            if (not member.isfile() or relative.is_absolute() or '..' in relative.parts
                    or member.name not in expected or member.name in found):
                raise ValueError('Unsafe or unexpected archive member')
            destination = args.output.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, destination.open('xb') as target:
                shutil.copyfileobj(source, target)
            record = expected[member.name]
            if destination.stat().st_size != record['size'] or digest(destination) != record['sha256']:
                raise ValueError('Restored file mismatch: '+member.name)
            found.add(member.name)
    if found != set(expected):
        raise ValueError('Missing archive files')
    result = dict(passed=True, restored_files=len(found), archive_sha256=manifest['archive_sha256'])
    (args.output/'RESTORE_VERIFIED.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Restored and verified', len(found), 'files:', args.output)


if __name__ == '__main__':
    main()
