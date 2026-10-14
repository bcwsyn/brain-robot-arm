#!/usr/bin/env python3
"""Plot measured random-task errors and frozen-training episode returns."""
import argparse
import json
from pathlib import Path
import pickle

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--training', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    baseline = json.loads(args.baseline.read_text())
    trials = baseline['trials']
    start = np.array([t['start_xy'] for t in trials])*1000
    goal = np.array([t['goal_xy'] for t in trials])*1000
    error = np.array([t['placement_error_m'] for t in trials])*1000
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), constrained_layout=True)
    for ax, points, title in zip(axes[:2], [start, goal], ['Random cup origins', 'Random destinations']):
        ax.scatter(points[:, 0], points[:, 1], c=np.arange(len(points)), cmap='viridis', s=36)
        ax.set(xlabel='World X (mm)', ylabel='World Y (mm)', title=title)
        ax.grid(alpha=.2)
    axes[2].bar(np.arange(1, len(error)+1), error, color='#309b79')
    axes[2].set(xlabel='Trial', ylabel='Measured 3D error (mm)',
                title=f"Gazebo baseline: {baseline['passed']}/{baseline['planned']}")
    axes[2].text(.04, .94, 'Acceptance gate: 30 mm', transform=axes[2].transAxes, va='top')
    axes[2].set_ylim(0, max(error)*1.3)
    axes[2].grid(axis='y', alpha=.2)
    fig.savefig(args.output/'random_baseline.png', dpi=180)
    plt.close(fig)
    # Read only this project's own trusted replay buffer.
    with (args.training/'replay_buffer.pkl').open('rb') as stream:
        replay = pickle.load(stream)
    if replay.full:
        raise ValueError('This plot expects an unwrapped, non-full frozen smoke buffer')
    reward = replay.rewards[:replay.pos, 0]
    ends = np.flatnonzero(replay.dones[:replay.pos, 0])
    beginnings = np.r_[0, ends[:-1]+1]
    returns = [float(reward[first:last+1].sum()) for first, last in zip(beginnings, ends)]
    fig, ax = plt.subplots(figsize=(7, 3.5), constrained_layout=True)
    ax.plot(ends+1, returns, 'o-', color='#586ba4')
    ax.set(xlabel='Collected training steps', ylabel='Undiscounted episode return',
           title='SAC+HER short run: zero successful training episodes')
    ax.grid(alpha=.25)
    fig.savefig(args.output/'training_curve.png', dpi=180)
    plt.close(fig)
    (args.output/'plot_data.json').write_text(json.dumps(dict(
        baseline=baseline['session'], episode_end_steps=(ends+1).tolist(), returns=returns,
        interpretation='Training returns are not held-out success; frozen policy evaluation is separate'), indent=2)+'\n')


if __name__ == '__main__':
    main()
