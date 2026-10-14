#!/usr/bin/env python3
"""Run predeclared Gazebo-only trials, with scene resets within each position."""
import argparse
import itertools
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--plan', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
plan = json.loads(args.plan.read_text())
(args.output / 'trial_plan.json').write_text(json.dumps(plan, indent=2)+'\n')
results = []
for (_, profile), group_iterator in itertools.groupby(plan['trials'], key=lambda t:(t['task'],t['scene_profile'])):
    group = list(group_iterator)
    trial = group[0]
    destination = args.output / trial['id'].rsplit('-r', 1)[0]
    command = [sys.executable, '-s', str(Path(__file__).with_name('validate_sim_grasp.py')),
               trial['task'], '--timeout', '170', '--scene-params-file', profile,
               '--repetitions', str(len(group)), '--output', str(destination)]
    print('START_GROUP ' + str(destination.name), flush=True)
    with (args.output / (destination.name + '.console.log')).open('w') as log:
        status = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
    result_path = destination / 'result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() else {'passed':False,'error':'validator did not save result'}
    completed = result.get('trial_results', [])
    for metadata, measured in zip(group, completed):
        row = {**metadata, **{key: measured.get(key) for key in ['passed','elapsed_s','final_xyz','placement_error_m',
            'peak_lift_height_m','home_error_rad','nonzero_jogs_while_owned','error']}, 'evidence':str(destination / ('trial_%02d.json' % measured['repetition']))}
        results.append(row)
        print(json.dumps(row, ensure_ascii=False),flush=True)
    if len(completed) < len(group):
        results.append({**group[len(completed)], 'passed':False,'error':result.get('error','Incomplete group'), 'evidence':str(result_path)})
    (args.output / 'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    if status or not result['passed']:
        raise SystemExit(1)
print('All predeclared trials passed.',flush=True)
