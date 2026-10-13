"""Exercise shell startup gates with fake ROS commands, never ROS/CAN output."""
import os
from pathlib import Path
import signal
import subprocess
import time

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


def test_camera_checks_have_a_forced_exit_deadline():
    health = function("camera_has_required_frame")
    startup = function("wait_for_actual_frame")
    assert health.count("timeout -k 2s 4s ros2 topic echo --once") == 3
    assert 'timeout -k 2s 4s ros2 topic echo --once "$topic"' in startup


def test_camera_check_terminates_a_term_resistant_ros_cli(tmp_path):
    """Fake subscriber ignores TERM; no ROS, USB or robot is involved."""
    cli = tmp_path / "ros2"
    cli.write_text('#!/bin/bash\ntrap "" TERM\nexec sleep 60\n')
    cli.chmod(0o700)
    started = time.monotonic()
    result = subprocess.run(
        ["bash", "-c", function("camera_has_required_frame") +
         "\nDEPTH_ONLY_TARGET=1; camera_has_required_frame"],
        env={**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"]},
        capture_output=True, timeout=10, start_new_session=True,
    )
    assert result.returncode == 137, result.stderr
    assert 4 <= time.monotonic() - started < 9


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


@pytest.mark.parametrize("interruption", [signal.SIGINT, signal.SIGTERM])
def test_cleanup_finishes_owned_group_cleanup_after_repeated_signal(tmp_path, interruption):
    """Only signal our mock shell; kill/ROS functions cannot affect real hardware."""
    trace = tmp_path / "trace"
    ready = tmp_path / "ready"
    mock = r'''
SUCCESSFUL_CYCLE_COMPLETE=0
DISABLE_REQUESTED=1
MOTION_ARMED=0
CAMERA_HEALTH_PID=""
CAN_HEALTH_PID=""
CAMERA_STARTED_BY_SCRIPT=1
LOG_GUARD_PID=""
PIDS=(987654)
timeout() { shift; "$@"; }
ros2() { printf 'ros2 %s\n' "$*" >> "$TRACE"; }
kill() { printf 'kill %s\n' "$*" >> "$TRACE"; }
sleep() { :; }
stop_rgb_camera() {
  printf 'camera_cleanup_started\n' >> "$TRACE"
  : > "$READY"
  command sleep 0.5
}
stop_astra_camera() {
  # A trapped signal must not become an inherited, unchangeable ignored signal.
  bash -c 'trap "exit 42" TERM; kill -TERM $$; exit 0'
  printf 'helper_signal_status=%s\n' "$?" >> "$TRACE"
  printf 'astra_cleanup_finished\n' >> "$TRACE"
}
'''
    with subprocess.Popen(
        ["bash", "-c", mock + function("cleanup") + "\ncleanup"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "TRACE": str(trace), "READY": str(ready)},
        start_new_session=True,
    ) as process:
        deadline = time.monotonic() + 3
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "mock cleanup did not reach its synchronization point"
        os.kill(process.pid, interruption)
        stdout, stderr = process.communicate(timeout=3)
        assert process.returncode == 0, (stdout, stderr)
    calls = trace.read_text().splitlines()
    assert calls[:3] == [
        "ros2 service call /visual_search_controller/stop std_srvs/srv/Trigger {}",
        "ros2 service call /servo_node/stop_servo std_srvs/srv/Trigger {}",
        "ros2 service call /piper_jog_adapter/disarm std_srvs/srv/Trigger {}",
    ]
    assert "astra_cleanup_finished" in calls
    assert "helper_signal_status=42" in calls
    assert "kill -TERM -- -987654" in calls
    assert "kill -KILL -- -987654" in calls
    assert not any("DisableArm" in call or "return_home" in call for call in calls)
    assert "一键流程已停止" in stdout.decode()
