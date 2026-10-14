#!/usr/bin/env python3
"""Visualize SAVED state trajectories; replay is not a new physical validation."""
import argparse
import json
from pathlib import Path
import sys
import time

import mujoco
import numpy as np

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS/'rl'))
from piper_cup_rl.env import PiperCupEnv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Environment verification or learned-policy evaluation directory')
    parser.add_argument('--episode', type=int, default=1)
    parser.add_argument('--speed', type=float, default=1.)
    parser.add_argument('--video', type=Path, help='Write MP4 instead of opening the viewer')
    parser.add_argument('--wrist', action='store_true', help='Use the wrist view for video (state policy still has no images)')
    args = parser.parse_args()
    if args.speed <= 0 or args.episode < 1:
        parser.error('Positive speed and episode required')
    scripted = (args.directory/'environment_validation.json').is_file()
    report = json.loads((args.directory/('environment_validation.json' if scripted else 'evaluation.json')).read_text())
    trial = report['episodes' if scripted else 'trials'][args.episode-1]
    filename = 'scripted_trajectories.npz' if scripted else 'trajectories.npz'
    with np.load(args.directory/filename) as traces:
        trajectory = traces['episode_'+str(args.episode)].copy()
    # Four action values precede the complete 15-value generalized position.
    env = PiperCupEnv()
    env.reset(seed=trial['seed'], options=trial['task'])
    print('Recorded trajectory replay; controller:', 'SCRIPTED' if scripted else 'LEARNED',
          'recorded success:', trial['is_success'], flush=True)
    try:
        if args.video:
            import cv2
            args.video.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(args.video), cv2.VideoWriter_fourcc(*'mp4v'), 25., (640, 480))
            if not writer.isOpened():
                raise RuntimeError('Video writer unavailable')
            renderer = mujoco.Renderer(env.model, height=480, width=640) if args.wrist else None
            try:
                for row in trajectory:
                    env.data.qpos[:] = row[4:19]
                    mujoco.mj_forward(env.model, env.data)
                    if args.wrist:
                        renderer.update_scene(env.data, camera='wrist_rgb')
                        frame = renderer.render()
                    else:
                        frame = env.render()
                    writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            finally:
                writer.release()
                if renderer:
                    renderer.close()
            print('Saved recorded trajectory:', args.video)
        else:
            from mujoco import viewer as mujoco_viewer
            with mujoco_viewer.launch_passive(env.model, env.data) as viewer:
                viewer.cam.lookat[:] = [.3, 0., .15]
                viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = 1., 130., -25.
                for row in trajectory:
                    if not viewer.is_running():
                        break
                    env.data.qpos[:] = row[4:19]
                    mujoco.mj_forward(env.model, env.data)
                    viewer.sync()
                    time.sleep(.04/args.speed)
    finally:
        env.close()


if __name__ == '__main__':
    main()
