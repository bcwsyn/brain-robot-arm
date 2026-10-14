#!/usr/bin/env python3
"""Independent random-task acceptance against the PREDECLARED task plan."""
import argparse
import json
import math
from pathlib import Path


def analyze(path):
    session = json.loads((path/'session.json').read_text())
    plan = json.loads((path/'random_task_plan.json').read_text())
    runs = session['runs']
    trials = []
    for index, run in enumerate(runs):
        expected = plan['trials'][index]
        initial_ok = math.dist(run['initial_xyz'][:2], expected['start_xy']) < .001
        destination_ok = math.dist(run['destination_xyz'][:2], expected['goal_xy']) < 1e-9
        actual_error = math.dist(run['final_xyz'], [*expected['goal_xy'], run['initial_xyz'][2]]) if run.get('final_xyz') else None
        passed = (bool(run.get('passed')) and initial_ok and destination_ok
                  and actual_error is not None and actual_error < .03)
        trials.append(dict(trial=index+1, start_xy=expected['start_xy'], goal_xy=expected['goal_xy'],
                           passed=passed, initial_pose_matches_plan=initial_ok,
                           destination_matches_plan=destination_ok, placement_error_m=actual_error,
                           peak_lift_m=run.get('peak_lift_m'), hold_span_sim_s=run.get('hold_span_sim_s'),
                           hold_force_range_n=run.get('hold_force_range_n'), tilt_rad=run.get('final_tilt_rad'),
                           completed=run.get('completed', False)))
    passed = sum(t['passed'] for t in trials)
    full = len(runs) == len(plan['trials']) and passed == len(runs)
    return dict(schema_version=1, session=path.name, seed=plan['seed'],
                planned=len(plan['trials']), attempted=len(runs), passed=passed,
                unattempted=len(plan['trials'])-len(runs), full_plan_passed=full,
                max_placement_error_m=max((t['placement_error_m'] for t in trials if t['placement_error_m'] is not None), default=None),
                unique_starts=len({tuple(t['start_xy']) for t in trials}),
                unique_goals=len({tuple(t['goal_xy']) for t in trials}),
                interpretation='Gazebo wrist RGB-D + MoveIt + force controller baseline; NOT RL policy results',
                trials=trials)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.session)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(f"Random baseline: {result['passed']}/{result['planned']}; attempted {result['attempted']}")
    if not result['full_plan_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
