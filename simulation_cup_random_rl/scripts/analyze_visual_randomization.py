#!/usr/bin/env python3
"""Export independent trial and camera-surface localization tables (stdlib only)."""
import argparse
import csv
import json
import math
from pathlib import Path


def summarize(errors):
    values = sorted(errors)
    if not values:
        return {'count': 0}
    return dict(count=len(values), mean_m=sum(values)/len(values),
                median_m=(values[(len(values)-1)//2]+values[len(values)//2])/2,
                p95_m=values[math.ceil(.95*len(values))-1], maximum_m=values[-1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sessions', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    trials, measurements = [], []
    for directory in args.sessions:
        session = json.loads((directory / 'session.json').read_text())
        for index, run in enumerate(session['runs'], 1):
            row = dict(session=directory.name, task=session['task'], seed=session['seed'], trial=index,
                       scene_index=run['scene_index'], zone=run['zone'],
                       completed=run.get('completed', False), passed=run.get('passed', False),
                       elapsed_s=run['elapsed_s'], peak_lift_m=run.get('peak_lift_m', ''),
                       placement_error_m=run.get('placement_error_m', ''),
                       home_error_rad=run.get('home_error_rad', ''),
                       failure_reason=run.get('failure_reason', run.get('interrupted_in', '')),
                       localization_count=len(run.get('localization_samples', [])))
            for prefix, key in [('initial', 'initial_xyz'), ('destination', 'destination_xyz'), ('final', 'final_xyz')]:
                for axis, value in zip('xyz', run.get(key) or ['', '', '']):
                    row[prefix+'_'+axis] = value
            trials.append(row)
            for sample in run.get('localization_samples', []):
                measurement = dict(session=directory.name, task=session['task'], trial=index,
                                   image_stamp_ns=sample['image_stamp_ns'], xy_error_m=sample['xy_error_m'],
                                   z_surface_center_difference_m=sample['z_surface_center_difference_m'])
                for prefix, key in [('camera_surface', 'camera_surface_xyz'), ('gazebo_center', 'gazebo_center_xyz')]:
                    for axis, value in zip('xyz', sample[key]):
                        measurement[prefix+'_'+axis] = value
                measurements.append(measurement)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, rows in [('trials.csv', trials), ('localization.csv', measurements)]:
        with (args.output / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [])
            writer.writeheader()
            writer.writerows(rows)
    result = dict(validation_kind='camera_randomized_follow_based_flow',
                  sessions=[str(p.resolve()) for p in args.sessions],
                  trials=len(trials), passed=sum(bool(row['passed']) for row in trials),
                  failed=sum(not bool(row['passed']) for row in trials),
                  xy_surface_to_center_discrepancy={task: summarize(
                      row['xy_error_m'] for row in measurements if row['task'] == task)
                      for task in sorted({row['task'] for row in trials})},
                  limitations=['Surface point versus model center, not camera calibration accuracy.',
                               'Known model height and collision geometry remain in use.',
                               'Pose following remains enabled; not a physical grasp success rate.'])
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
