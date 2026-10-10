"""Replay the installed controller with instantaneous MOCK feedback in domain 78.

This checks state order and collision-planned trajectory bounds, NOT physical
execution, camera calibration, USB stability, velocity tracking or grasp success.
No CAN/adapter/joint_commands publisher is created. Never run in the real domain.
"""
import math
import os
import time

import rclpy
from geometry_msgs.msg import Vector3Stamped
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from rcl_interfaces.srv import GetParameters
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger
from trajectory_msgs.msg import JointTrajectory


if os.environ.get("ROS_DOMAIN_ID") != "78":
    raise RuntimeError("Replay requires isolated ROS_DOMAIN_ID=78")

OBSERVE = [0.0, 0.98, -0.75, 0.0, 0.30, 0.0]
NAMES = [f"joint{i}" for i in range(1, 7)]


class Replay(Node):
    def __init__(self):
        super().__init__("center_search_mock_feedback")
        self.q = OBSERVE.copy()
        self.feedback = True
        self.target = False
        self.scenario = ""
        self.phase = ""
        self.reason = ""
        self.details = []
        self.endpoints = []
        self.error = None
        self.full_seen = False
        self.center_return = False
        self.local_started = False
        self.pub = self.create_publisher(JointState, "/joint_states", 10)
        self.valid = self.create_publisher(Bool, "/brain_robot_vision/target_valid", 10)
        self.pixel = self.create_publisher(Vector3Stamped, "/brain_robot_vision/pixel_error", 10)
        latched = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(String, "/brain_robot_visual_control/reason", self.on_reason, latched)
        self.create_subscription(String, "/brain_robot_visual_control/search_direction", self.on_detail, latched)
        self.create_subscription(JointTrajectory, "/brain_robot_grasp/arm_trajectory", self.on_trajectory, 10)
        self.timer = self.create_timer(0.02, self.publish)
        self.start = self.create_client(Trigger, "/visual_search_controller/start")
        self.stop = self.create_client(Trigger, "/visual_search_controller/stop")
        self.parameters = self.create_client(GetParameters, "/visual_search_controller/get_parameters")

    def publish(self):
        if self.feedback:
            if self.scenario == "settled_feedback" and "CENTER_HOLD" in self.phase:
                # Real regression: J3 settled 1.5 mrad after the anchor snapshot.
                self.q[2] = OBSERVE[2] - 0.0015
            state = JointState()
            state.header.stamp = self.get_clock().now().to_msg()
            state.name = NAMES + ["joint7", "joint8"]
            state.position = self.q + [0.0231, -0.0231]
            self.pub.publish(state)
        self.valid.publish(Bool(data=self.target))
        if self.target:
            pixel = Vector3Stamped()
            pixel.header.stamp = self.get_clock().now().to_msg()
            self.pixel.publish(pixel)  # Zero pixel error: synthetic acquired target.

    def on_reason(self, msg):
        self.reason = msg.data
        print("REPLAY_REASON", self.scenario, self.reason, flush=True)

    def on_detail(self, msg):
        self.phase = msg.data
        self.details.append(msg.data)
        if "CENTER_RETURN_CONFIRMED" in msg.data:
            self.center_return = True
        if "PHASE=CENTER_HOLD" in msg.data and self.scenario == "acquire_at_center":
            self.target = True
        if "source=FULL_SEARCH" in msg.data:
            self.full_seen = True
            if not self.center_return:
                self.error = "Full scan before measured return to center"

    def on_trajectory(self, trajectory):
        if not trajectory.points:
            self.error = "Empty trajectory"
            return
        points = [{name: value for name, value in zip(trajectory.joint_names, pt.positions)}
                  for pt in trajectory.points]
        for point in points:
            if not all(math.isfinite(point.get(name, float("nan"))) for name in NAMES):
                self.error = "Incomplete/non-finite trajectory"
            # Replays start exactly at observe; only J1/J5 search may move.
            for i in (1, 2, 3, 5):
                # 0.001 path hold around an anchor; next scan anchors may be
                # within the tightened 0.0001 goal tolerance of that posture.
                limit = 0.003 if self.scenario == "settled_feedback" else 0.002
                if abs(point[NAMES[i]] - OBSERVE[i]) > limit:
                    self.error = f"Non-search hold exceeded: {NAMES[i]}={point[NAMES[i]]}"
            if not -1.351 <= point["joint1"] <= 1.351 or not -0.601 <= point["joint5"] <= 0.951:
                self.error = "Search range exceeded"
        end = points[-1]
        changes = max(abs(end[name] - self.q[i]) for i, name in enumerate(NAMES))
        if changes > 0.011:
            self.endpoints.append((end["joint1"], end["joint5"]))
            print("REPLAY_ENDPOINT", self.scenario, self.phase, self.endpoints[-1], flush=True)
            if "CENTER_LOCAL_SCAN" in self.phase:
                self.local_started = True
                if self.scenario == "stale_feedback":
                    self.feedback = False
        # Instantaneous mock tracking, not real dynamics or adapter execution.
        self.q = [end[name] for name in NAMES]

    def spin_for(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.02)
            if self.error:
                raise AssertionError(self.error)

    def call(self, client):
        if not client.wait_for_service(timeout_sec=10.0):
            raise AssertionError("Replay controller service unavailable")
        future = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if not future.done() or not future.result().success:
            raise AssertionError("Replay service failed")

    def run(self, scenario):
        self.call(self.stop)
        self.scenario = scenario
        self.q = OBSERVE.copy()
        self.feedback = True
        self.target = False
        self.full_seen = self.center_return = self.local_started = False
        self.endpoints = []
        self.details = []
        self.reason = self.phase = ""
        self.spin_for(0.3)
        self.call(self.start)
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            self.spin_for(0.05)
            if scenario == "acquire_at_center" and self.reason in (
                    "TARGET_ACQUIRED", "DIRECT_VISUAL_ALIGN_ACQUIRED"):
                assert not self.endpoints and not self.full_seen
                print("CENTER_TARGET_PREEMPTS_ALL_SWEEPS_PASS", flush=True)
                break
            if scenario == "stale_feedback" and self.reason == "JOINT_STATE_TIMEOUT":
                assert self.local_started and not self.full_seen
                print("STALE_FEEDBACK_CANNOT_EXPAND_PASS", flush=True)
                break
            if scenario == "settled_feedback" and self.local_started:
                assert not self.full_seen
                assert abs(self.q[2] - OBSERVE[2]) < 0.0002
                print("SETTLED_FEEDBACK_START_INCLUDED_PASS", flush=True)
                break
            if scenario == "full_scan" and self.full_seen:
                negative = any(h <= -1.34 for h, _ in self.endpoints)
                positive = any(h >= 1.34 for h, _ in self.endpoints)
                if negative and positive:
                    local = self.endpoints[:8]
                    assert all(abs(h) <= 0.081 and 0.179 <= v <= 0.421 for h, v in local)
                    assert self.center_return
                    print("CENTER_LOCAL_RETURN_FULL_BOTH_SIDES_PASS", flush=True)
                    break
            if "FAULT" in self.reason or self.reason.startswith("CENTER_SEARCH_"):
                raise AssertionError("Unexpected replay failure: " + self.reason)
        else:
            raise AssertionError("Replay phase timeout: " + self.phase + " " + self.reason)
        self.call(self.stop)
        self.spin_for(0.1)


rclpy.init()
node = Replay()
try:
    node.spin_for(1.0)
    forbidden = ("piper_single_ctrl", "piper_jog_adapter", "grasp_lift_executor", "servo_node")
    if any(any(word in name for word in forbidden) for name in node.get_node_names()):
        raise RuntimeError("Unexpected execution/physical node in replay domain")
    if not node.parameters.wait_for_service(timeout_sec=10.0):
        raise RuntimeError("Replay parameter service unavailable")
    future = node.parameters.call_async(GetParameters.Request(names=[
        "joint_state_timeout_s", "initial_search_center_first", "initial_search_hold_s"]))
    rclpy.spin_until_future_complete(node, future, timeout_sec=10.0)
    if not future.done() or future.result() is None:
        raise RuntimeError("Replay parameter read failed")
    timeout, center_first, hold = future.result().values
    print("REPLAY_ACTUAL_PARAMETERS", timeout.double_value, center_first.bool_value,
          hold.double_value, flush=True)
    assert timeout.double_value == 0.5 and center_first.bool_value and hold.double_value == 2.0
    for scenario in ("full_scan", "acquire_at_center", "stale_feedback", "settled_feedback"):
        node.run(scenario)
    print("CENTER_REPLAY_ALL_PASS_NO_PHYSICAL_EXECUTION", flush=True)
finally:
    # Stop the isolated controller even when an assertion fails.
    if node.stop.service_is_ready():
        try:
            node.call(node.stop)
        except Exception:
            pass
    node.destroy_node()
    rclpy.shutdown()
