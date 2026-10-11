#!/usr/bin/env python3
"""Own one isolated detector, replay both real captures, then ALWAYS stop it.

Camera topics only in domain 78. No actual driver, MoveIt or motion interface.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--detector-bin', type=Path, required=True)
    parser.add_argument('--capture-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('ROS_DOMAIN_ID') != '78' or args.output.exists():
        parser.error('Requires isolated domain 78 and new output directory')
    args.output.mkdir()
    package = Path(__file__).parents[1]
    config = package.parent / 'brain_robot_ball_pick/config/cube_detector.yaml'
    with (args.output / 'detector.log').open('w') as log:
        child = subprocess.Popen([str(args.detector_bin), '--ros-args', '--log-level', 'WARN',
                                  '-r', '__node:=cube_detector', '--params-file', str(config)],
                                 stdout=log, stderr=log)
        try:
            for stage in ('image_aim_after', 'image_forward_after'):
                command = [sys.executable, str(package / 'test/review_rgbd_shape_replay.py'),
                           '--capture', str(args.capture_root / stage),
                           '--output', str(args.output / stage)]
                if stage == 'image_aim_after':
                    command.append('--negative-cases')
                subprocess.run(command, check=True, timeout=75)
                assert child.poll() is None
                report = json.loads((args.output / stage / 'summary.json').read_text())
                outcome = report['outcomes']['captured']
                expected = stage == 'image_aim_after'
                for topic in ('target_valid', 'depth_valid'):
                    assert outcome[topic] and all(x == expected for x in outcome[topic])
                assert outcome['qualified_color_bbox'] and all(
                    len(x['corners']) == 4 for x in outcome['qualified_color_bbox'])
                if not expected:
                    assert not outcome['target_point_camera']
                    assert not outcome['raw_target_projection']
            print('NEAR_DETECTOR_REPLAY: real pre-depth valid; real post-depth false; RGB shape retained')
        finally:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)
            print('ISOLATED_DETECTOR_EXITED', child.returncode)


if __name__ == '__main__':
    main()
