#!/usr/bin/env python3
"""Export measured force, opening and object-height traces from one saved trial."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--trial', type=int, default=1)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run = json.loads(args.session.read_text())['runs'][args.trial-1]
    forces = run['force_samples']
    models = run['model_samples']
    start = models[0]['sim_time_s']
    time = [s['sim_time_s']-start for s in forces]
    fig, axes = plt.subplots(3,1,figsize=(11,8),sharex=True,layout='constrained')
    for i,color in ((0,'#2274a5'),(1,'#e76f51')):
        axes[0].plot(time,[s['force_n'][i] for s in forces],color=color,label=('Left','Right')[i],lw=1.2)
    axes[0].axhspan(2.5,3.5,color='#2a9d8f',alpha=.15,label='Accepted holding band')
    axes[0].axhline(5,color='red',ls='--',lw=1,label='Hard limit')
    axes[0].set_ylabel('Jaw-axis force (N)'); axes[0].legend(ncol=4,fontsize=8)
    for key,label in (('command_opening_m','Commanded'),('measured_opening_m','Measured')):
        axes[1].plot(time,[s[key]*1000 for s in forces],label=label,lw=1.2)
    axes[1].set_ylabel('Opening (mm)');axes[1].legend()
    axes[2].plot([s['sim_time_s']-start for s in models],
                 [(s['xyz'][2]-run['initial_xyz'][2])*1000 for s in models],color='#264653')
    axes[2].axhline(50,color='#2a9d8f',ls='--',lw=1)
    axes[2].set_ylabel('Physical cup lift (mm)');axes[2].set_xlabel('Simulation time since task start (s)')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('Camera-sized cup: measured force, opening and physical retention')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.output,dpi=150)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
