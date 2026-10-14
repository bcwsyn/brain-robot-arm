#!/usr/bin/env python3
"""Run frozen Gazebo cup batches; preserve every failed case and stop on failure."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time

WS = Path(__file__).resolve().parents[1]
CASES = {
    'main': (['--diameter-mm', '75', '--seed', '20261015', '--batch-trials', '5'], 5, None),
    '55': (['--diameter-mm', '55', '--seed', '20261016', '--batch-trials', '2'], 2, None),
    '85': (['--diameter-mm', '85', '--seed', '20261017', '--batch-trials', '2'], 2, None),
    'miss': (['--seed', '20261018', '--batch-trials', '1', '--physics-negative', 'miss'], 0, 'capture'),
    'feedback-loss': (['--seed', '20261018', '--batch-trials', '1', '--fault', 'feedback-loss'], 0, 'STALE_FORCE_FEEDBACK'),
    'overforce': (['--seed', '20261018', '--batch-trials', '1', '--fault', 'overforce'], 0, 'OVERFORCE'),
    'stop': (['--seed', '20261018', '--batch-trials', '1', '--physics-negative', 'stop'], 0, 'CONTROLLED_STOP'),
    'oversize': (['--diameter-mm', '105', '--seed', '20261018', '--batch-trials', '1', '--fault', 'oversize'], 0, 'oversize'),
}


def assess(session_dir, result_code, count, expected):
    session = json.loads((session_dir/'session.json').read_text())
    events = [json.loads(line) for line in (session_dir/'events.jsonl').read_text().splitlines()]
    if expected is None:
        return dict(passed=result_code == 0 and len(session['runs']) == count and
                    all(r.get('passed') for r in session['runs']),
                    completed=session['completed'], metrics=[{key: run.get(key) for key in
                    ('passed', 'peak_lift_m', 'hold_span_sim_s', 'placement_error_m',
                     'home_error_rad', 'final_tilt_rad', 'hold_force_range_n')} for run in session['runs']])
    if expected == 'oversize':
        result = json.loads((session_dir/'negative_result.json').read_text())
        return dict(passed=result_code == 0 and result['expected_rejection'] and
                    result['no_task_executor_launched'] and result['home_error_rad'] < .002,
                    evidence=result)
    text = '\n'.join(json.dumps(event) for event in events)
    states = [e['value'] for e in events if e.get('topic') == 'grasp']
    has_expected = ('CONTACT_TIMEOUT' in text or 'NO_CAPTURE' in text) if expected == 'capture' else expected in text
    injected = expected in ('STALE_FORCE_FEEDBACK', 'OVERFORCE')
    injection_seen = any('injected_fault' in event for event in events) if injected else True
    tail = session['runs'][-1].get('joint_samples', []) if session['runs'] else []
    if tail:
        tail = [s for s in tail if s['elapsed_s'] >= tail[-1]['elapsed_s'] - .5]
    drift = max((max(s['positions'][i] for s in tail) - min(s['positions'][i] for s in tail)
                 for i in range(6)), default=0.) if tail else None
    passed = result_code != 0 and has_expected and injection_seen and 'COMPLETE' not in states
    if expected == 'capture':
        passed = passed and 'LIFTING_PHYSICAL_OBJECT' not in states
    else:
        passed = passed and drift is not None and drift < .01
    return dict(passed=passed, expected_fault=expected, observed_states=states,
                injection_seen=injection_seen, final_half_second_joint_drift_rad=drift)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['all', *CASES], default='all')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or WS/'validation/cup_grasp'/('acceptance_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    output.mkdir(parents=True, exist_ok=False)
    plan = WS/'validation/cup_grasp/stage5_test_plan.json'
    source_paths = [p for base in (WS/'src/brain_robot_pick_place', WS/'scripts', WS/'config')
                    for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    frozen = {str(p.relative_to(WS)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    (output/'frozen_sources.json').write_text(json.dumps(frozen, indent=2)+'\n')
    (output/'frozen_plan.json').write_bytes(plan.read_bytes())
    results = []
    for name in (['55', '85', 'main', 'miss', 'feedback-loss', 'overforce', 'stop', 'oversize']
                 if args.case == 'all' else [args.case]):
        flags, count, expected = CASES[name]
        before = set((WS/'log/visual_sim').glob('cup-*'))
        command = ['bash', str(WS/'scripts/run_cup_grasp_sim.sh'), '--headless', *flags]
        print('Starting', name, flush=True)
        with (output/(name+'.console.log')).open('w') as log:
            process = subprocess.Popen(command, cwd=WS, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                result_code = process.wait(timeout=120 + 200*max(1,count))
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                process.send_signal(signal.SIGINT)
                process.wait(timeout=20)
                raise
        created = set((WS/'log/visual_sim').glob('cup-*')) - before
        if len(created) != 1:
            raise RuntimeError('Expected exactly one new simulation session, got '+str(len(created)))
        session_dir = created.pop()
        outcome = assess(session_dir, result_code, count, expected)
        outcome.update(case=name, exit_code=result_code, session=str(session_dir.relative_to(WS)), command=command)
        results.append(outcome)
        changed = [p for p,digest in frozen.items() if not (WS/p).is_file() or
                   hashlib.sha256((WS/p).read_bytes()).hexdigest() != digest]
        outcome['frozen_sources_unchanged'] = not changed
        outcome['passed'] = outcome['passed'] and not changed
        report = dict(passed=all(r['passed'] for r in results), cases=results,
                      complete=len(results) == (len(CASES) if args.case == 'all' else 1))
        (output/'results.json').write_text(json.dumps(report, indent=2)+'\n')
        print(name, 'PASSED' if outcome['passed'] else 'FAILED', str(session_dir), flush=True)
        if not outcome['passed']:
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
