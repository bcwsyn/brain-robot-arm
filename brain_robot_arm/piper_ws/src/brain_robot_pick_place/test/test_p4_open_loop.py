"""P4 opt-in isolation and frozen surface contract. No ROS/CAN during these tests."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

PKG = Path(__file__).resolve().parents[1]
LAUNCH = PKG.parent / 'brain_robot_ball_pick/launch/cube_visual_search.launch.py'
CPP = (PKG / 'src/grasp_lift_executor.cpp').read_text()
SCRIPT = PKG.parents[2] / 'scripts/start_brain_robot_cube_real.sh'
spec = importlib.util.spec_from_file_location('p4_export', PKG / 'scripts/prepare_p4_board_target.py')
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def launch_helpers():
    tree = ast.parse(LAUNCH.read_text())
    module = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                             and node.name in ('_load_yaml', '_p4_overrides')], type_ignores=[])
    scope = {'math': __import__('math'), 'yaml': yaml}
    exec(compile(module, str(LAUNCH), 'exec'), scope)
    return scope['_p4_overrides']


def target_file(tmp_path, **changes):
    data = {'schema': 'p4_board_surface_v1', 'frame_id': 'base_link',
            'surface_base_m': [.3454, -.00938, .04452], 'cube_edge_m': .029,
            'provenance': 'test-only-snapshot', **changes}
    path = tmp_path / 'target.yaml'
    path.write_text(yaml.safe_dump(data))
    return str(path)


def function(name):
    text = SCRIPT.read_text()
    start = text.index(name + '() {')
    return text[start:text.index('\n}\n', start) + 3]


def test_disabled_mode_neither_reads_target_nor_changes_default_parameters():
    assert launch_helpers()({}) == ({}, {})
    assert launch_helpers()({'BRAIN_ROBOT_P4_TARGET_CONFIG': '/nonexistent'}) == ({}, {})
    assert 'ParameterOr<bool>("p4_open_loop_enabled", false)' in CPP


def test_p4_overrides_are_narrow_and_preview_is_default(tmp_path):
    path = target_file(tmp_path, real_trajectory_joint_min=[-999] * 6,
                       fresh_jaw_capture_required=False, gripper_tip_offset_m=999)
    visual, grasp = launch_helpers()({'BRAIN_ROBOT_P4_OPEN_LOOP': '1',
                                     'BRAIN_ROBOT_P4_TARGET_CONFIG': path})
    assert visual == {'stop_after_observe': True}
    assert grasp['p4_plan_only'] is True
    assert grasp['auto_release_after_lift'] is False
    assert set(grasp) == {'p4_open_loop_enabled', 'p4_plan_only', 'p4_surface_base_m',
                         'p4_cube_edge_m', 'p4_target_provenance', 'auto_release_after_lift'}


@pytest.mark.parametrize('changes', [dict(frame_id='camera_depth_optical_frame'),
                         dict(surface_base_m=[0, 0, float('nan')]), dict(cube_edge_m=0),
                         dict(schema='center_not_surface'), dict(provenance='')])
def test_invalid_target_fails_before_nodes_are_created(tmp_path, changes):
    with pytest.raises(RuntimeError):
        launch_helpers()({'BRAIN_ROBOT_P4_OPEN_LOOP': '1',
                          'BRAIN_ROBOT_P4_TARGET_CONFIG': target_file(tmp_path, **changes)})


def test_explicit_mode_requires_target():
    with pytest.raises(RuntimeError):
        launch_helpers()({'BRAIN_ROBOT_P4_OPEN_LOOP': '1'})


def test_handoff_flags_override_node_specific_task_yaml_not_only_wildcard_dicts():
    source = LAUNCH.read_text()
    assert 'visual_search_controller:stop_after_observe:=true' in source
    assert 'grasp_lift_executor:auto_release_after_lift:=false' in source
    assert 'if p4_visual else []' in source and 'if p4_grasp else []' in source
    assert 'arguments=p4_visual_args' in source and 'arguments=p4_grasp_args' in source


def test_export_uses_top_surface_not_half_height_or_bad_depth(tmp_path):
    review = tmp_path / 'review.json'; capture = tmp_path / 'observer.jsonl'
    review.write_text(json.dumps({'frames': [{'nominal_height_ray_intersections': [
        {'height_m': .0145, 'base_m': [9, 9, 9]},
        {'height_m': .029, 'base_m': [x, 2, 3]}]} for x in [1, 2, 6]]}))
    capture.write_text('\n'.join(json.dumps({'stamps_ns': {'rgb': i}, 'q_rad': [0] * 6})
                                 for i in [1, 2, 3]))
    result = export.make_target(review, capture)
    assert result['surface_base_m'] == [2, 2, 3]
    assert result['source_rgb_stamps_ns'] == [1, 2, 3]
    assert len(result['source_review_sha256']) == 64
    assert 'STATIC SNAPSHOT' in result['assumptions'][0]


def test_p4_does_not_enter_legacy_tracking_and_keeps_original_execution_checks():
    entry = CPP[CPP.index('  void PointGraspAndLift()'):CPP.index('  void CandidatePointGraspAndLift()')]
    assert entry.index('P4OpenLoopGraspAndLift();') < entry.index('near_seed_ = {}')
    branch = entry[entry.index('  void P4OpenLoopGraspAndLift()'):]
    for forbidden in ['AutomaticRgbApproach(', 'ObserveLockedTarget(', 'CaptureTargetModel(',
                      'arm_->execute(', 'DisableArm', 'ResetPiper']:
        assert forbidden not in branch
    for required in ['TargetDirectedApproach(', 'PlanArmCartesianWaypointsFromState(',
                     'RealTrajectoryWithinLimits(', 'ExecuteArmTrajectory(',
                     'EnsureRealTopDownLanding(', 'FinishGraspAndLift(retreat)']:
        assert required in branch
    preview = branch.index('if (p4_plan_only_)')
    assert preview < branch.index('!ExecuteArmTrajectory(')
    assert 'if (!p4_plan_only_)' in branch[:preview]
    assert 'if (!simulation_only_ && !p4_open_loop_enabled_ &&' in CPP
    handler = CPP[CPP.index('  void HandleVisualState'):CPP.index('  void StartWorker')]
    assert handler.index('if (p4_open_loop_enabled_') < handler.index('visual_state == "LEVEL_ALIGN"')
    assert 'if (p4_open_loop_enabled_) {p4_emergency_stop_latched_ = true;}' in CPP
    assert 'p4_emergency_stop_latched_ || visual_state == "FAULT"' in CPP


@pytest.mark.parametrize('preview,state,expected,observe_calls', [
    ('1', 'P4_PLAN_READY_NO_EXECUTION', 0, 0), ('0', 'HOLDING', 0, 1),
    ('0', 'FAULT_P4_LANDING', 1, 1), ('1', 'FAULT_P4_FULL_PATH_PLAN_FAILED', 1, 0),
])
def test_p4_original_entry_does_not_auto_reset_or_disable(tmp_path, preview, state, expected, observe_calls):
    trace = tmp_path / 'trace'
    mock = '''
restart_visual_sequence() { echo OBSERVE >> "$TRACE"; }
timeout() { shift 3; "$@"; }
ros2() {
  echo "$*" >> "$TRACE"
  if [[ "$1" == service ]]; then echo 'success=True'; else echo "data: $STATE"; fi
}
'''
    result = subprocess.run(['bash', '-c', mock + function('run_p4_sequence') + '\nrun_p4_sequence'],
                            capture_output=True, timeout=4,
                            env={**os.environ, 'TRACE': str(trace), 'STATE': state,
                                 'P4_PLAN_ONLY': preview})
    assert result.returncode == expected, result.stderr
    calls = trace.read_text().splitlines()
    assert calls.count('OBSERVE') == observe_calls
    assert not any('/reset' in c or '/enable_srv' in c or 'disable' in c for c in calls)
