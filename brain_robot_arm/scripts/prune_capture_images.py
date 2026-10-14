#!/usr/bin/env python3
"""Prune only old runtime PNGs; protect references, recent captures and samples."""
import argparse
import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path

ROOT = Path('/home/johnwick/brain_robot_logs')
REPO = Path('/mnt/hgfs/ub')


def image_kind(name):
    for kind in ('rgb', 'debug', 'depth'):
        if name.startswith(kind + '_') or name.endswith('_' + kind + '.png'):
            return kind
    return 'depth' if name.endswith('_depth_raw.png') else 'other'


def choose_deletions(rows, referenced_names, limit_bytes, now):
    """Pure retention policy: total budget, >=24h old, first/last and samples."""
    groups = {}
    for row in rows:
        groups.setdefault((str(Path(row['path']).parent), image_kind(Path(row['path']).name)), []).append(row)
    protected = {r['path'] for r in rows if Path(r['path']).name in referenced_names}
    for group in groups.values():
        ordered = sorted(group, key=lambda r: (r['mtime_ns'], r['path']))
        protected.update(r['path'] for r in ordered[:3] + ordered[-3:] + ordered[::1000])
    remaining = sum(r['size'] for r in rows)
    selected = []
    for row in sorted(rows, key=lambda r: (r['mtime_ns'], r['path'])):
        if remaining <= limit_bytes:
            break
        if row['path'] not in protected and now - row['mtime_ns'] / 1e9 >= 86400:
            selected.append(row)
            remaining -= row['size']
    return selected, remaining


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit-mb', type=int, default=8192)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.limit_mb <= 16384:
        parser.error('Image budget must be within 1..16384 MiB')
    if ROOT.is_symlink() or not ROOT.is_dir() or ROOT.resolve() != ROOT:
        raise RuntimeError('Runtime log root must be the exact existing non-symlink directory')
    result = subprocess.run(['git', '-C', str(REPO), 'grep', '-I', '-h', '-E', r'\.png',
                             '--', '*.md', '*.json', '*.py', '*.yaml'], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError('Cannot read canonical image references; refusing deletion')
    refs = set(re.findall(r'([A-Za-z0-9_.-]+\.png)', result.stdout))
    rows = []
    for directory, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
        for filename in files:
            if not filename.endswith('.png'):
                continue
            path = Path(directory) / filename
            info = path.stat(follow_symlinks=False)
            if stat.S_ISREG(info.st_mode):
                rows.append({'path': str(path), 'size': info.st_size, 'mtime_ns': info.st_mtime_ns,
                             'inode': info.st_ino, 'device': info.st_dev})
    selected, projected = choose_deletions(rows, refs, args.limit_mb * 1048576, time.time())
    removed = removed_bytes = 0
    if args.apply:
        for row in selected:
            path = Path(row['path'])
            if not path.is_relative_to(ROOT) or path.suffix != '.png' or path.is_symlink():
                raise RuntimeError('Invalid deletion target')
            info = path.stat(follow_symlinks=False)
            if (info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns) != (
                    row['inode'], row['device'], row['size'], row['mtime_ns']):
                raise RuntimeError('Image changed since inventory; refusing deletion')
            path.unlink()
            removed += 1
            removed_bytes += row['size']
    print(json.dumps({'scope': str(ROOT), 'apply': args.apply, 'png_count': len(rows),
                      'png_bytes_before': sum(r['size'] for r in rows), 'limit_mb': args.limit_mb,
                      'planned_count': len(selected), 'projected_bytes': projected,
                      'deleted_count': removed, 'deleted_bytes': removed_bytes,
                      'protected': 'Canonical referenced basenames, <24h files, first/last3 and every1000th per stream',
                      'warning': 'Budget may remain exceeded when all remaining images are protected'}))


if __name__ == '__main__':
    main()
