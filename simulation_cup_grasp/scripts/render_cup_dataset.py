#!/usr/bin/env python3
"""Render grouped cup geometry splits in Gazebo; preserve raw data and annotations."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

import cv2
import numpy as np
import yaml

from probe_cup_rgbd import WS, CupSpec, make_world, capture


GROUPS = {
    'train': [(55, 120, 44, 25), (60, 150, 48, 30), (65, 180, 53, 40), (70, 155, 58, 35),
              (78, 175, 67, 38), (82, 145, 66, 32), (85, 185, 70, 35), (88, 160, 75, 40)],
    'val': [(58, 170, 46, 28), (80, 165, 64, 37)],
    'test': [(62, 160, 51, 33), (86, 175, 71, 38)],
}


def annotate(raw, destination, split, group, rng, manifest):
    palette = [(210, 45, 35), (35, 125, 210), (190, 160, 35), (90, 170, 65), (195, 110, 165), (200, 200, 190)]
    for image in sorted((raw/'images').glob('*.png')):
        bgr = cv2.imread(str(image))
        mask = ((bgr[:, :, 2] > 20) & (bgr[:, :, 2] > 1.5*bgr[:, :, 1].astype(float)) &
                (bgr[:, :, 2] > 1.5*bgr[:, :, 0].astype(float))).astype(np.uint8)*255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise RuntimeError('fixture annotation missing: '+str(image))
        contour = max(contours, key=cv2.contourArea)
        polygon = cv2.approxPolyDP(contour, .8, True).reshape(-1, 2)
        if cv2.contourArea(contour) < 800 or len(polygon) < 6:
            raise RuntimeError('insufficient mask area: '+str(image))
        normalized = polygon/np.array([bgr.shape[1], bgr.shape[0]])
        label = '0 '+' '.join(f'{x:.7f}' for x in normalized.flat)+'\n'
        for variant in range(3 if split == 'train' else 1):
            output = bgr.copy()
            color = np.array(palette[int(rng.integers(len(palette)))][::-1])
            shading = bgr[:, :, 2].astype(float)/180
            output[mask > 0] = np.clip(shading[mask > 0, None]*color, 0, 255).astype(np.uint8)
            if split == 'train':
                gamma = float(rng.uniform(.8, 1.2))
                output = np.clip(255*(output.astype(float)/255)**gamma, 0, 255).astype(np.uint8)
            stem = f'{group}_{image.stem}_{variant}'
            target = destination/'images'/split/f'{stem}.png'
            cv2.imwrite(str(target), output)
            (destination/'labels'/split/f'{stem}.txt').write_text(label)
            manifest.append(dict(split=split, group=group, source=str(image.relative_to(destination)),
                image=str(target.relative_to(destination)), sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                target_count=1, annotation='Gazebo red-fixture contour before recoloring; includes dark connecting neck'))
    # Empty-table images are negative examples generated from each source
    # background. They stay in the same geometry split as their source.
    template = cv2.imread(str(next((raw/'images').glob('*.png'))))
    for index in range(3):
        negative = template.copy()
        sky, table, horizon = int(rng.integers(120, 190)), int(rng.integers(45, 105)), int(rng.integers(190, 270))
        negative[:] = (sky, sky, sky)
        cv2.rectangle(negative, (0, horizon), (640, 480), (table, table, table), -1)
        # Simple non-cup distractors are documented synthetic negatives.
        if index:
            center = (int(rng.integers(160, 480)), int(rng.integers(270, 360)))
            color = tuple(int(x) for x in rng.integers(40, 230, 3))
            if index == 1:
                cv2.circle(negative, center, 35, color, -1)
            else:
                cv2.rectangle(negative, center, (center[0]+65, center[1]+45), color, -1)
        stem = f'{group}_negative_{index}'
        target = destination/'images'/split/f'{stem}.png'
        cv2.imwrite(str(target), negative)
        (destination/'labels'/split/f'{stem}.txt').write_text('')
        manifest.append(dict(split=split, group=group, source='synthetic background/distractor',
            image=str(target.relative_to(destination)), sha256=hashlib.sha256(target.read_bytes()).hexdigest(), target_count=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--views', type=int, default=10)
    parser.add_argument('--final-test-only', action='store_true',
                        help='Fresh geometries for frozen-model evaluation; do not train on this output')
    args = parser.parse_args()
    if not 5 <= args.views <= 20 or args.output.exists():
        parser.error('views must be 5..20 and output must be new')
    if os.environ.get('ROS_DOMAIN_ID') != '84' or os.environ.get('GAZEBO_MASTER_URI') != 'http://127.0.0.1:11484':
        parser.error('Use ROS domain 84 / Gazebo port 11484')
    destination = args.output.resolve()
    rng = np.random.default_rng(20261015 if args.final_test_only else 20261014)
    groups_to_render = {'test': [(59, 148, 49, 31), (84, 172, 68, 39)]} if args.final_test_only else GROUPS
    manifest, groups = [], []
    (WS/'log').mkdir(exist_ok=True)
    with (WS/'log/cup_probe.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 11484))
        for split in GROUPS:
            for stem in ('images', 'labels'):
                (destination/stem/split).mkdir(parents=True, exist_ok=True)
        for split, geometries in groups_to_render.items():
            for index, (body, height, mouth, neck) in enumerate(geometries):
                group = f'{split}_{index:02d}'
                raw = destination/'raw'/group
                (raw/'images').mkdir(parents=True)
                spec = CupSpec(body/1000, height/1000, mouth/1000, neck/1000)
                cameras = []
                for _ in range(args.views):
                    angle, distance = rng.uniform(-math.pi, math.pi), rng.uniform(.24, .46)
                    cameras.append((.4+distance*math.cos(angle), distance*math.sin(angle), float(rng.uniform(.23, .44))))
                world, views = make_world(raw, spec, cameras)
                with (raw/'gazebo.log').open('w') as log:
                    process = subprocess.Popen(['gzserver', '--verbose', str(world), '-s', 'libgazebo_ros_init.so'],
                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    try:
                        capture(raw, views, process, fit_geometry=False)
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGINT)
                            try:
                                process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                os.killpg(process.pid, signal.SIGKILL)
                                process.wait(timeout=5)
                annotate(raw, destination, split, group, rng, manifest)
                groups.append(dict(group=group, split=split, spec=spec.__dict__, views=len(views)))
                print(f'Finished {group}: {len(manifest)} labelled images so far', flush=True)
        config = dict(train='images/test' if args.final_test_only else 'images/train',
            val='images/test' if args.final_test_only else 'images/val', test='images/test', names={0: 'cup'})
        (destination/'data.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
        (destination/'manifest.json').write_text(json.dumps(dict(seed=20261015 if args.final_test_only else 20261014,
            scope='synthetic Gazebo cups; no claim of real-camera accuracy', split_unit='cup geometry; before color augmentation',
            final_evaluation_only=args.final_test_only,
            user_specimen_75_160_63_40_is_held_out=True, groups=groups, images=manifest), indent=2)+'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
