#!/usr/bin/env python3
"""Validate API, throughput and solvability with a SCRIPTED controller, not RL."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS/'rl'))
from piper_cup_rl.env import PiperCupEnv


def scripted_episode(env, seed):
    obs, info = env.reset(seed=seed)
    trace, transitions, phases, ended = [], [], [], False

    def action_step(action):
        nonlocal obs, info, ended
        previous = {key: value.copy() for key, value in obs.items()}
        obs, reward, terminated, truncated, info = env.step(action)
        trace.append(np.r_[action, env.data.qpos, obs['achieved_goal'], reward])
        transitions.append((previous, {key: value.copy() for key, value in obs.items()},
                            np.asarray(action), reward, terminated, truncated))
        ended = terminated or truncated
        return not ended

    def move(target, grip):
        phases.append(dict(phase='move', target=target, step=env.steps))
        for _ in range(700):
            delta = np.asarray(target)-env.data.site_xpos[env.tcp_id]
            if np.linalg.norm(delta) < .002:
                return True
            if not action_step(np.r_[np.clip(delta/.004, -.3, .3), grip]):
                return False
        return False

    start, goal = env.task['start_xy'], env.task['goal_xy']
    ok = move([*start, .12], 0.)
    phases.append(dict(phase='close', step=env.steps))
    stable = 0
    if ok:
        for _ in range(140):
            if not action_step([0, 0, 0, 1]):
                ok = False
                break
            stable = stable+1 if all(2.5 <= f <= 3.5 for f in info['force_n']) else 0
            if stable >= 10:
                break
        ok &= stable >= 10
    if ok:
        ok = move([*start, .27], 1.)
    if ok:
        phases.append(dict(phase='hold', step=env.steps))
        for _ in range(75):
            if not action_step([0, 0, 0, 1]):
                ok = False
                break
    if ok:
        ok = move([*goal, .27], 1.) and move([*goal, .125], 1.)
    if ok:
        phases.append(dict(phase='release', step=env.steps))
        for _ in range(100):
            if not action_step([0, 0, 0, -1]):
                break
    return dict(seed=seed, steps=env.steps, phases=phases,
                scripted_success=bool(info['is_success']), **info), np.array(trace), transitions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--episodes', type=int, default=3)
    parser.add_argument('--seed', type=int, default=100)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from stable_baselines3.common.env_checker import check_env
    env = PiperCupEnv()
    try:
        check_env(env, warn=True)
        env.reset(seed=10)
        before = time.monotonic()
        for _ in range(200):
            env.step(np.zeros(4))
        elapsed = time.monotonic()-before
        report = dict(api_check_passed=True, zero_action_steps=200, wall_s=elapsed,
                      steps_per_wall_second=200/elapsed, sim_seconds_per_wall_second=8/elapsed,
                      controller='scripted geometric controller, not a learned policy', episodes=[])
        report['model_sha256'] = hashlib.sha256((WS/'rl/assets/piper_cup.xml').read_bytes()).hexdigest()
        report['env_sha256'] = hashlib.sha256((WS/'rl/piper_cup_rl/env.py').read_bytes()).hexdigest()
        traces, demonstrations = {}, {}
        for index in range(args.episodes):
            result, trace, transitions = scripted_episode(env, args.seed+index)
            report['episodes'].append(result)
            traces['episode_'+str(index+1)] = trace
            prefix = 'episode_'+str(index+1)
            for key in ('observation', 'achieved_goal', 'desired_goal'):
                demonstrations[prefix+'_obs_'+key] = np.array([t[0][key] for t in transitions])
                demonstrations[prefix+'_next_'+key] = np.array([t[1][key] for t in transitions])
            demonstrations[prefix+'_action'] = np.array([t[2] for t in transitions])
            demonstrations[prefix+'_reward'] = np.array([t[3] for t in transitions])
            demonstrations[prefix+'_terminated'] = np.array([t[4] for t in transitions])
            demonstrations[prefix+'_truncated'] = np.array([t[5] for t in transitions])
            print('Scripted environment validation:', index+1, result['scripted_success'], result['hard_fault'], flush=True)
        report['scripted_passed'] = sum(e['scripted_success'] for e in report['episodes'])
        (args.output/'environment_validation.json').write_text(json.dumps(report, indent=2)+'\n')
        np.savez_compressed(args.output/'scripted_trajectories.npz', **traces)
        np.savez_compressed(args.output/'scripted_transitions.npz', **demonstrations)
        if report['scripted_passed'] != args.episodes:
            raise SystemExit(1)
    finally:
        env.close()


if __name__ == '__main__':
    main()
