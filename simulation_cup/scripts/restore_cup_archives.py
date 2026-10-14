#!/usr/bin/env python3
"""Verify archive parts and restore requested immutable cup-training bundles."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-dir', type=Path, default=Path('validation/cup_vision/archives'))
    parser.add_argument('--destination', type=Path, default=Path('artifacts/cup_training'))
    parser.add_argument('--bundle', action='append', help='Repeat to select bundles; default restores all')
    args = parser.parse_args()
    manifest = json.loads((args.archive_dir/'archive_manifest.json').read_text())
    entries = [entry for entry in manifest['entries'] if not args.bundle or entry['bundle'] in args.bundle]
    if args.bundle and set(args.bundle)-{entry['bundle'] for entry in entries}:
        parser.error('unknown bundle name')
    for entry in entries:
        target = args.destination/entry['top_directory']
        if target.exists():
            parser.error('refusing to overwrite existing bundle: '+str(target))
    args.destination.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        with tempfile.TemporaryFile() as stream:
            total = hashlib.sha256()
            for part in entry['parts']:
                content = (args.archive_dir/part['file']).read_bytes()
                if len(content) != part['bytes'] or hashlib.sha256(content).hexdigest() != part['sha256']:
                    raise RuntimeError('archive part hash mismatch: '+part['file'])
                stream.write(content)
                total.update(content)
            if total.hexdigest() != entry['archive_sha256']:
                raise RuntimeError('joined archive checksum mismatch')
            stream.seek(0)
            with tarfile.open(fileobj=stream, mode='r:gz') as archive:
                destination = args.destination.resolve()
                for member in archive.getmembers():
                    path = (destination/member.name).resolve()
                    if not path.is_relative_to(destination) or member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                        raise RuntimeError('unsafe member: '+member.name)
                archive.extractall(destination)
        print('Restored', entry['bundle'], flush=True)


if __name__ == '__main__':
    main()
