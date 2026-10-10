"""Exercise shell startup gates with fake ROS commands, never ROS/CAN output."""
import os
from pathlib import Path
import subprocess

import pytest


SOURCE = Path(__file__).parents[4] / "scripts" / "start_brain_robot_cube_real.sh"
if not SOURCE.exists():
    SOURCE = Path.home() / "start_brain_robot_cube_real.sh"


def function(name):
    source = SOURCE.read_text()
    start = source.index(name + "() {")
    return source[start:source.index("\n}\n", start) + 3]


@pytest.mark.parametrize("ack,reason,expected", [
    ("True", "OBSERVE_POSE_REACHED", 0),
    ("False", "OBSERVE_POSE_REACHED", 1),
    ("True", "PREPARE_EXECUTION_FAILED", 1),
])
def test_start_ack_is_separate_from_feedback_completion(tmp_path, ack, reason, expected):
    trace = tmp_path / "trace"
    mock = r'''
timeout() {
  printf '%s\n' "$*" >> "$TRACE"
  shift
  "$@"
}
ros2() {
  if [[ "$1" == service ]]; then
    printf 'success=%s\n' "$ACK"
  else
    printf 'data: %s\n' "$REASON"
  fi
}
'''
    result = subprocess.run(["bash", "-c", mock + function("start_visual_sequence") +
                             "\nstart_visual_sequence"], capture_output=True,
                            env={**os.environ, "TRACE": str(trace), "ACK": ack,
                                 "REASON": reason}, timeout=5)
    assert result.returncode == expected
    calls = trace.read_text().splitlines()
    assert calls[0].startswith("30s ros2 service call /visual_search_controller/start ")
    assert sum("service call" in call for call in calls) == 1
    assert len(calls) == (1 if ack == "False" else 2)


def test_log_writer_stays_append_after_guard_truncation(tmp_path):
    assert 'setsid "$@" >>"$logfile" 2>&1 &' in function("start_group")
    path = tmp_path / "live.log"
    descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, b"previous CAN evidence\n")
        os.truncate(path, 0)
        os.write(descriptor, b"new CAN evidence\n")
    finally:
        os.close(descriptor)
    assert path.read_bytes() == b"new CAN evidence\n"


@pytest.mark.parametrize("grasp,visual,expected,returns_home", [
    ("IDLE", "FAULT", 1, False),
    ("IDLE", "'FAULT'", 1, False),
    ("IDLE", '"FAULT"', 1, False),
    ("FAULT_GRIPPER", "SEARCH", 1, False),
    ("RELEASE_COMPLETE_HOLDING_SAFE_RETREAT", "GRASP_READY", 0, True),
])
def test_early_search_fault_does_not_wait_at_idle_or_disable(tmp_path, grasp, visual, expected, returns_home):
    trace = tmp_path / "trace"
    mock = r'''
timeout() { shift; "$@"; }
ros2() {
  case "$*" in
    *brain_robot_grasp/state*) printf 'data: %s\n' "$GRASP";;
    *visual_control/state*) printf 'data: %s\n' "$VISUAL";;
    *visual_control/reason*) printf 'data: CENTER_SEARCH_NOT_REACHED_NO_FULL_SWEEP\n';;
  esac
}
reset_zero_sequence() { printf 'return_home\n' >> "$TRACE"; }
disable_after_confirmed_reset() { printf 'disable_after_home\n' >> "$TRACE"; }
'''
    result = subprocess.run(["bash", "-c", mock + function("wait_for_grasp_release_and_finalize") +
                             "\nwait_for_grasp_release_and_finalize"], capture_output=True,
                            env={**os.environ, "TRACE": str(trace), "GRASP": grasp,
                                 "VISUAL": visual, "BRAIN_ROBOT_GRASP_WAIT_SECONDS": "2"}, timeout=5)
    assert result.returncode == expected
    assert trace.exists() == returns_home
    if returns_home:
        assert trace.read_text().splitlines() == ["return_home", "disable_after_home"]
    elif grasp == "IDLE":
        assert b"CENTER_SEARCH_NOT_REACHED_NO_FULL_SWEEP" in result.stderr
