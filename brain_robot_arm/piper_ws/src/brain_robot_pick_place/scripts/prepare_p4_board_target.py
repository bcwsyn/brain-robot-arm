#!/usr/bin/env python3
"""Export an explicitly reviewed static board/RGB hypothesis, never control ROS.

Input is review_fixed_board_plane.py's immutable report plus its observer.jsonl.
This does not acquire live data, validate TCP, or make an archived scene current.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

import yaml


def make_target(review_path, capture_path, cube_edge_m=0.029):
    review_bytes = Path(review_path).read_bytes()
    capture_bytes = Path(capture_path).read_bytes()
    review = json.loads(review_bytes)
    captures = [json.loads(line) for line in capture_bytes.splitlines() if line.strip()]
    frames = review['frames']
    if not frames or len(frames) != len(captures):
        raise ValueError('Need all matched static review/capture frames')
    if not math.isfinite(cube_edge_m) or cube_edge_m <= 0:
        raise ValueError('Invalid nominal cube edge')
    points = []
    for frame in frames:
        top = [p for p in frame['nominal_height_ray_intersections']
               if abs(p['height_m'] - cube_edge_m) < 1e-9]
        if len(top) != 1 or len(top[0]['base_m']) != 3 or not all(
                math.isfinite(x) for x in top[0]['base_m']):
            raise ValueError('No matching finite TOP SURFACE hypothesis; never use center as surface')
        points.append(top[0]['base_m'])
    digest = hashlib.sha256(review_bytes).hexdigest()
    return {
        'schema': 'p4_board_surface_v1', 'frame_id': 'base_link',
        'surface_base_m': [statistics.median(p[i] for p in points) for i in range(3)],
        'cube_edge_m': cube_edge_m,
        'provenance': f'board_RGB_nominal_top_surface; review_SHA256={digest}',
        'source_review': str(Path(review_path).resolve()),
        'source_review_sha256': digest,
        'source_capture_sha256': hashlib.sha256(capture_bytes).hexdigest(),
        'source_rgb_stamps_ns': [row['stamps_ns']['rgb'] for row in captures],
        'source_q_rad': [row['q_rad'] for row in captures],
        'assumptions': [
            'STATIC SNAPSHOT, not a live measurement. Cube and support must remain unchanged.',
            '32mm nominal planar board and 29mm nominal cube, not external metrology.',
            'Whole RGB silhouette centroid ray is not a verified top-face-center ray.',
            'Top surface input for ORIGINAL insertion geometry; do not add half edge again.',
            'Existing model TCP is not an independently measured physical grasp center.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    target = make_target(args.review, args.capture)
    # Never overwrite an input or a prior attempt's frozen snapshot.
    with args.output.open('x', encoding='utf-8') as stream:
        yaml.safe_dump(target, stream, allow_unicode=True, sort_keys=False)
    print(json.dumps({'output': str(args.output), 'surface_base_m': target['surface_base_m'],
                      'read_only_export_no_ROS_or_motion': True}))


if __name__ == '__main__':
    main()
