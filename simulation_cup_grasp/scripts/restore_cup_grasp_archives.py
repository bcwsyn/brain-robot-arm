#!/usr/bin/env python3
"""Verify and restore stage 5 archives without overwriting existing files."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, default=Path(__file__).resolve().parents[1]/'validation/cup_grasp/archives')
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists():
        parser.error('Choose a new destination; existing data will not be overwritten')
    manifest = json.loads((args.archives/'manifest.json').read_text())
    with tempfile.TemporaryFile() as combined:
        for part in manifest['parts']:
            data = (args.archives/part['file']).read_bytes()
            if hashlib.sha256(data).hexdigest() != part['sha256']:
                raise RuntimeError('Part checksum mismatch: '+part['file'])
            combined.write(data)
        combined.seek(0)
        digest = hashlib.sha256()
        while chunk := combined.read(1024*1024):
            digest.update(chunk)
        if digest.hexdigest() != manifest['archive_sha256']:
            raise RuntimeError('Combined archive checksum mismatch')
        combined.seek(0)
        with tarfile.open(fileobj=combined, mode='r:gz') as archive:
            for member in archive.getmembers():
                name = Path(member.name)
                if name.is_absolute() or '..' in name.parts or member.issym() or member.islnk():
                    raise RuntimeError('Unsafe archive member: '+member.name)
            args.destination.mkdir(parents=True)
            archive.extractall(args.destination)
    mismatches = []
    for name, expected in manifest['files_sha256'].items():
        path = args.destination/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            mismatches.append(name)
    if mismatches:
        raise RuntimeError('Restored file mismatch: '+str(mismatches[:5]))
    print('Restored and verified',len(manifest['files_sha256']),'files in',args.destination)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
