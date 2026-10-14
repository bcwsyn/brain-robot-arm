#!/usr/bin/env python3
"""CPU SAC+HER training entry; saved checkpoints are not an accuracy claim."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import time

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS/'rl'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', type=int, default=200000)
    parser.add_argument('--seed', type=int, default=20261015)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', type=Path, help='Existing run directory, including replay_buffer.pkl')
    parser.add_argument('--randomize-dynamics', action='store_true')
    args = parser.parse_args()
    if args.steps < 3000:
        parser.error('Use at least 3000 steps to exercise complete-episode HER replay and updates')
    import torch
    from stable_baselines3 import SAC, HerReplayBuffer
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.env_checker import check_env
    from piper_cup_rl.env import PiperCupEnv
    torch.set_num_threads(2)
    output = args.output or WS/'artifacts/cup_rl'/datetime.now().strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True, exist_ok=False)
    env = PiperCupEnv(randomize_dynamics=args.randomize_dynamics)
    check_env(env, warn=True)
    config = dict(steps=args.steps, seed=args.seed, algorithm='SAC+HER',
                  observation='simulation truth, 33 state scalars and 7 goal scalars',
                  action='Cartesian XYZ increments and bounded force-limited jaw request; radial yaw prior',
                  randomize_dynamics=args.randomize_dynamics, camera_images_used=False,
                  backend='MuJoCo current-URDF-derived model; NOT validated Gazebo or real policy',
                  model_sha256=hashlib.sha256((WS/'rl/assets/piper_cup.xml').read_bytes()).hexdigest())
    (output/'training_config.json').write_text(json.dumps(config, indent=2)+'\n')
    source_paths = [*sorted((WS/'rl/piper_cup_rl').glob('*.py')), Path(__file__).resolve()]
    (output/'source_hashes.json').write_text(json.dumps({str(p.relative_to(WS)):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}, indent=2)+'\n')
    with tarfile.open(output/'source_snapshot.tar.gz', 'w:gz') as archive:
        for path in source_paths + [WS/'rl/assets/piper_cup.xml', WS/'rl/assets/model_provenance.json', WS/'config/cup_rl_requirements.txt']:
            archive.add(path, arcname=str(path.relative_to(WS)))

    class Recorder(BaseCallback):
        def __init__(self):
            super().__init__()
            self.completed, self.successful = 0, 0
            self.stream = (output/'episodes.jsonl').open('w')

        def _on_step(self):
            for done, info in zip(self.locals['dones'], self.locals['infos']):
                if done:
                    self.completed += 1
                    self.successful += int(info['is_success'])
                    record = {k: v for k, v in info.items() if k != 'terminal_observation'}
                    self.stream.write(json.dumps(dict(step=self.num_timesteps, **record),
                                                 default=lambda value: value.item())+'\n')
                    self.stream.flush()
            if self.num_timesteps % 10000 == 0:
                self.model.save(output/'checkpoint')
                self.model.save_replay_buffer(output/'checkpoint_replay.pkl')
                print('RL progress:', self.num_timesteps, 'steps;', self.completed, 'episodes', flush=True)
            return True

    recorder = Recorder()
    if args.resume:
        previous = json.loads((args.resume/'training_config.json').read_text())
        previous_sources = json.loads((args.resume/'source_hashes.json').read_text())
        env_path = 'rl/piper_cup_rl/env.py'
        env_sha = hashlib.sha256((WS/env_path).read_bytes()).hexdigest()
        if previous['model_sha256'] != config['model_sha256'] or previous['randomize_dynamics'] != config['randomize_dynamics']:
            raise ValueError('Resume requires the same model and dynamics-randomization setting')
        if previous_sources.get(env_path) != env_sha:
            raise ValueError('Resume requires the same environment source')
        model = SAC.load(args.resume/'model.zip', env=env, device='cpu')
        model.load_replay_buffer(args.resume/'replay_buffer.pkl')
    else:
        model = SAC('MultiInputPolicy', env, replay_buffer_class=HerReplayBuffer,
                    replay_buffer_kwargs=dict(n_sampled_goal=4, goal_selection_strategy='future', copy_info_dict=True),
                    learning_starts=2200, buffer_size=100000, batch_size=128,
                    policy_kwargs=dict(net_arch=[128, 128]), seed=args.seed,
                    device='cpu', verbose=0)
    started, finished = time.monotonic(), False
    try:
        model.learn(args.steps, callback=recorder, reset_num_timesteps=not bool(args.resume))
        finished = True
    except KeyboardInterrupt:
        print('Interrupted; preserving model and replay buffer.', flush=True)
    finally:
        model.save(output/'model')
        model.save_replay_buffer(output/'replay_buffer.pkl')
        elapsed = time.monotonic()-started
        (output/'training_result.json').write_text(json.dumps(dict(
            finished_requested_steps=finished, total_model_steps=model.num_timesteps,
            optimizer_updates=model._n_updates,
            elapsed_s=elapsed, steps_per_wall_second=args.steps/elapsed if finished else None,
            completed_episodes=recorder.completed, successful_training_episodes=recorder.successful,
            interpretation='Training execution only; use an independent evaluation before any performance claim'), indent=2)+'\n')
        recorder.stream.close()
        env.close()
        print('Saved model, replay buffer, episodes and configuration:', output, flush=True)


if __name__ == '__main__':
    main()
