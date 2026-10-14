#!/usr/bin/env python3
"""Export independent physical trial measurements; never start ROS or motion."""
import argparse
import csv
import json
import math
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sessions', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    groups = {}
    for session in args.sessions:
        data = json.loads((session / 'session.json').read_text())
        if not data.get('physics_grasp'):
            raise ValueError('A flow session cannot enter physical results: ' + str(session))
        for index, run in enumerate(data['runs'], 1):
            samples = [s for s in run['model_samples'] if s.get('grasp_state') == 'HOLDING_PHYSICAL_OBJECT']
            span = max((s['sim_time_s'] for s in samples), default=0) - min(
                (s['sim_time_s'] for s in samples), default=0)
            contacts = run.get('contact_samples', [])
            fit_errors = [s['xy_error_m'] for s in run['localization_samples']]
            row = dict(task=data['task'], session=str(session), trial=index, zone=run['zone'],
                       completed=run.get('completed', False), passed=run.get('passed', False),
                       peak_lift_m=run['maximum_z']-run['initial_xyz'][2],
                       hold_span_sim_s=span,
                       minimum_hold_lift_m=run['holding_min_z']-run['initial_xyz'][2]
                       if run['holding_min_z'] is not None and math.isfinite(run['holding_min_z']) else None,
                       elapsed_s=run.get('elapsed_s'), placement_error_m=run.get('placement_error_m'),
                       home_error_rad=run.get('home_error_rad'),
                       nonzero_jogs=run['nonzero_jogs_while_owned'],
                       contact_samples=len(contacts), bilateral_samples=sum(s['both'] for s in contacts),
                       maximum_contact_force_n=max((s['force_n'] for s in contacts), default=0),
                       fitted_center_xy_error_m=max(fit_errors, default=None),
                       failure_reason=run.get('failure_reason', ''))
            rows.append(row)
            groups.setdefault(data['task'], []).append(row)
    with (args.output / 'trials.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    for task, trials in groups.items():
        errors = sorted(r['fitted_center_xy_error_m'] for r in trials if r['fitted_center_xy_error_m'] is not None)
        summary[task] = dict(trials=len(trials), passed=sum(r['passed'] for r in trials),
                            complete=sum(r['completed'] for r in trials),
                            minimum_peak_lift_m=min(r['peak_lift_m'] for r in trials),
                            minimum_hold_span_sim_s=min(r['hold_span_sim_s'] for r in trials),
                            xy_center_error_mean_m=sum(errors)/len(errors) if errors else None,
                            xy_center_error_p95_m=errors[math.ceil(.95*len(errors))-1] if errors else None)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
