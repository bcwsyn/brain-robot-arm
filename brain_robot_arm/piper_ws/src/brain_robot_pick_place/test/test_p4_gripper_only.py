"""Scoped diagnostic-mode contracts; no ROS/device output in these tests."""
import os
import subprocess
import pytest
from test_p4_open_loop import CPP, SCRIPT, function, launch_helpers


def test_explicit_gripper_test_needs_no_arm_target_and_does_not_enable_by_default():
    visual, grasp = launch_helpers()({'BRAIN_ROBOT_P4_OPEN_LOOP': '1',
        'BRAIN_ROBOT_P4_PLAN_ONLY': '0', 'BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY': '1'})
    assert visual == {'stop_after_observe': True}
    assert grasp['p4_gripper_test_only'] is True
    assert not any(k in grasp for k in ['p4_surface_base_m', 'p4_center_base_m'])
    assert launch_helpers()({'BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY': '1'}) == ({}, {})
    assert 'ParameterOr<bool>("p4_gripper_test_only", false)' in CPP


@pytest.mark.parametrize('changes', [{'BRAIN_ROBOT_P4_PLAN_ONLY': '1'},
                                   {'BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY': 'bad'}])
def test_gripper_mode_rejects_ambiguous_or_preview_execution(changes):
    with pytest.raises(RuntimeError):
        launch_helpers()({'BRAIN_ROBOT_P4_OPEN_LOOP': '1', 'BRAIN_ROBOT_P4_PLAN_ONLY': '0',
                         'BRAIN_ROBOT_P4_GRIPPER_TEST_ONLY': '1', **changes})


def test_exclusive_test_service_reuses_policy_without_an_arm_or_lift_call():
    body = CPP[CPP.index('  void P4GripperOnlyTest()'):CPP.index('  bool GentleCloseGripper(')]
    for required in ['CommandRealGripper(true)', 'WaitForGripperCommand(',
                     'GentleCloseGripper(&empty)', 'P4_GRIPPER_TEST_EMPTY_NO_LIFT',
                     'std::chrono::duration<double>(gripper_settle_s_)']:
        assert required in body
    for forbidden in ['ExecuteArmTrajectory(', 'MoveArm', 'FinishGraspAndLift(',
                      'PointGraspAndLift(', 'JointCtrl', 'DisableArm', 'ResetPiper']:
        assert forbidden not in body
    assert 'if (p4_open_loop_enabled_ && p4_gripper_test_only_)' in CPP
    assert 'Gripper-only mode cannot start an arm/grasp sequence.' in CPP


@pytest.mark.parametrize('state,expected', [('P4_GRIPPER_TEST_EMPTY_NO_LIFT', 0),
    ('P4_GRIPPER_TEST_CONTACT_CANDIDATE_NO_LIFT', 1), ('FAULT_P4_GRIPPER_TEST_CLOSE_UNCONFIRMED', 1)])
def test_original_entry_reuses_enable_handoff_and_calls_only_gripper_service(tmp_path, state, expected):
    trace = tmp_path/'trace'
    mock = '''
wait_for() { return 0; }
enable_physical_motion() { echo ORIGINAL_ENABLE_HANDOFF >> "$TRACE"; return 0; }
timeout() { shift 3; "$@"; }
ros2() {
  echo "$*" >> "$TRACE"
  if [[ "$1" == service ]]; then echo 'success=True'; else echo "data: $STATE"; fi
}
'''
    result = subprocess.run(['bash', '-c', mock+function('run_p4_gripper_test')+'\nrun_p4_gripper_test'],
        capture_output=True, timeout=4, env={**os.environ,'TRACE':str(trace),'STATE':state})
    assert result.returncode == expected, result.stderr
    calls=trace.read_text().splitlines()
    assert sum('test_gentle_gripper' in line for line in calls)==1
    assert calls.count('ORIGINAL_ENABLE_HANDOFF') == 1
    assert not any(x in '\n'.join(calls) for x in ['/visual_search_controller/',
                     '/reset', '/grasp_lift_executor/execute'])
    text=SCRIPT.read_text()
    dispatch=text.index('  run_p4_gripper_test\n')
    assert dispatch < text.index('if [[ "$AUTO_START"', dispatch)


def test_gripper_only_cleanup_skips_visual_stop_hold_trajectory():
    body=function('cleanup')
    assert 'if [[ "$P4_GRIPPER_TEST_ONLY" != "1" ]]; then' in body
    assert '/piper_jog_adapter/disarm' in body
