#!/usr/bin/env python3
"""Frozen-policy held-out evaluation; failures count in the denominator."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS/'rl'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--episodes', type=int, default=20)
    parser.add_argument('--seed', type=int, default=2026101600)
    parser.add_argument('--render', action='store_true', help='Save first-frame and final-frame PNGs')
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error('Positive evaluation episode count required')
    import torch
    import numpy as np
    from stable_baselines3 import SAC
    from piper_cup_rl.env import PiperCupEnv
    torch.set_num_threads(2)
    args.output.mkdir(parents=True, exist_ok=False)
    config = json.loads((args.run/'training_config.json').read_text())
    sources = json.loads((args.run/'source_hashes.json').read_text())
    if config['model_sha256'] != hashlib.sha256((WS/'rl/assets/piper_cup.xml').read_bytes()).hexdigest():
        raise ValueError('Environment model differs from the trained model')
    if sources['rl/piper_cup_rl/env.py'] != hashlib.sha256((WS/'rl/piper_cup_rl/env.py').read_bytes()).hexdigest():
        raise ValueError('Environment source differs from the trained environment')
    env = PiperCupEnv(render_mode='rgb_array' if args.render else None,
                      randomize_dynamics=config['randomize_dynamics'])
    model = SAC.load(args.run/'model.zip', env=env, device='cpu')
    episodes, trajectories = [], {}
    started = time.monotonic()
    try:
        for index in range(args.episodes):
            obs, info = env.reset(seed=args.seed+index)
            trace = []
            if args.render and index == 0:
                from PIL import Image
                Image.fromarray(env.render()).save(args.output/'initial.png')
            for step in range(env.max_episode_steps):
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = env.step(action)
                trace.append(np.r_[action, env.data.qpos, obs['achieved_goal'], reward])
                if terminated or truncated:
                    break
            episodes.append(dict(episode=index+1, seed=args.seed+index, steps=step+1,
                                 terminated=terminated, truncated=truncated, **info))
            trajectories['episode_'+str(index+1)] = np.array(trace)
            if args.render and index == 0:
                Image.fromarray(env.render()).save(args.output/'final.png')
        np.savez_compressed(args.output/'trajectories.npz', **trajectories)
        passed = sum(e['is_success'] for e in episodes)
        result = dict(episodes=args.episodes, passed=passed, success_rate=passed/args.episodes,
                      policy_sha256=hashlib.sha256((args.run/'model.zip').read_bytes()).hexdigest(),
                      observation_source='simulation_truth_state_not_wrist_vision',
                      elapsed_s=time.monotonic()-started, trials=episodes,
                      trajectory_columns='action[4], qpos[15], achieved_goal[7], reward[1]')
        (args.output/'evaluation.json').write_text(json.dumps(result, indent=2)+'\n')
        print(f'Independent state-policy evaluation: {passed}/{args.episodes}; {args.output}')
    finally:
        env.close()


if __name__ == '__main__':
    main()
