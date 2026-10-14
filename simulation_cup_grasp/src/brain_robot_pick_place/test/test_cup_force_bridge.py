"""Exercise bridge timing, trajectory preload and fault latching with ROS messages."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cup_force_gripper_node as bridge
from adaptive_gripper_policy import ContactForcePolicy
from rclpy.time import Time
from std_srvs.srv import Trigger


class Publisher:
    def __init__(self, topic='test'):
        self.topic_name, self.messages = topic, []

    def publish(self, message):
        self.messages.append(message)

    def get_subscription_count(self):
        return 1


def node_fixture(monkeypatch):
    monkeypatch.setattr(bridge.time, 'monotonic', lambda: 100.)
    node = NS(mode='CAPTURE', request_id=1, state='STARTING', command=.06, center_offset=0.,
              previous_targets=[.03, -.03], positions=[.0375, -.0375],
              position_time=[100., 100.], forces=[2.8, 2.8], force_time=[100., 100.],
              force_error=['', ''], gross_forces=[3., 3.], axis_age=[0., 0.],
              width=None, width_time=100., last_clock=19.975, started=99., stable_since=0.,
              low_force_since=None, open_sent=False, last_open_send=-1., relief_started=0.,
              allow_fault_injection=False, injected_fault='', injection_time=0., pending_overforce=False,
              healthy=Publisher(), status=Publisher(), diagnostic=Publisher(),
              policy=ContactForcePolicy(minimum_force_n=2.5, maximum_force_n=3.5))
    node.jaw_publishers = [Publisher('/gripper_controller/joint_trajectory'),
                           Publisher('/gripper8_controller/joint_trajectory')]
    node.clock = 20.
    node.get_clock = lambda: NS(now=lambda: Time(seconds=node.clock))
    node.count_publishers = lambda _: 1
    node.publish_command = lambda: bridge.CupForceGripper.publish_command(node)
    return node


def test_stream_keeps_previous_command_not_blocked_position(monkeypatch):
    node = node_fixture(monkeypatch)
    node.command = .058
    node.publish_command()
    for i, publisher in enumerate(node.jaw_publishers):
        message = publisher.messages[-1]
        assert list(message.points[0].positions) == [.03 if i == 0 else -.03]
        assert list(message.points[0].positions) != [node.positions[i]]
        assert list(message.points[1].positions) == [.029 if i == 0 else -.029]
        assert message.points[1].time_from_start.nanosec == 25_000_000


def test_force_requires_continuous_stability_before_hold(monkeypatch):
    node = node_fixture(monkeypatch)
    bridge.CupForceGripper.tick(node)
    assert node.mode == 'CAPTURE' and not node.healthy.messages[-1].data
    node.clock = 20.6
    bridge.CupForceGripper.tick(node)
    assert node.mode == 'HOLD' and node.healthy.messages[-1].data


def test_force_loss_during_hold_cannot_remain_healthy(monkeypatch):
    node = node_fixture(monkeypatch)
    node.mode, node.forces = 'HOLD', [0., 2.8]
    bridge.CupForceGripper.tick(node)
    node.clock = 20.2
    bridge.CupForceGripper.tick(node)
    assert node.state == 'FAULT_LOST_BILATERAL_FORCE'
    assert not node.healthy.messages[-1].data


def test_stale_feedback_blocks_commands(monkeypatch):
    node = node_fixture(monkeypatch)
    node.force_time[0] = 99.7
    bridge.CupForceGripper.tick(node)
    assert node.state == 'FAULT_STALE_FORCE_FEEDBACK'
    assert not node.jaw_publishers[0].messages


def test_overload_relief_survives_stop_and_never_resumes(monkeypatch):
    node = node_fixture(monkeypatch)
    node.forces = [6., 3.]
    bridge.CupForceGripper.tick(node)
    assert node.mode == 'RELIEF' and not node.healthy.messages[-1].data
    opening = node.command
    response = bridge.CupForceGripper.request(node, 'stop', Trigger.Response())
    assert response.success and node.mode == 'RELIEF'
    node.clock = 20.05
    bridge.CupForceGripper.tick(node)
    assert node.command > opening
    node.forces = [3., 3.]
    bridge.CupForceGripper.tick(node)
    assert node.mode == 'FAULT' and node.state == 'FAULT_OVERFORCE_RELIEVED'


def test_test_fault_service_disabled_by_default(monkeypatch):
    node = node_fixture(monkeypatch)
    node.mode = 'HOLD'
    response = bridge.CupForceGripper.inject(node, 'feedback_loss', Trigger.Response())
    assert not response.success and not node.injected_fault


def test_other_command_owner_blocks_motion(monkeypatch):
    node = node_fixture(monkeypatch)
    node.count_publishers = lambda _: 2
    bridge.CupForceGripper.tick(node)
    assert node.state == 'FAULT_MULTIPLE_JAW_COMMAND_OWNERS'
    assert not node.jaw_publishers[0].messages


def test_single_opening_interface_enforces_symmetric_commands(monkeypatch):
    node = node_fixture(monkeypatch)
    node.center_offset = .001
    node.publish_command()
    left = node.jaw_publishers[0].messages[-1].points[-1].positions[0]
    right = node.jaw_publishers[1].messages[-1].points[-1].positions[0]
    assert left == -right and node.center_offset == 0.


def test_overforce_injection_is_consumed_even_after_timer_delay(monkeypatch):
    node = node_fixture(monkeypatch)
    node.mode, node.allow_fault_injection = 'HOLD', True
    assert bridge.CupForceGripper.inject(node, 'overforce', Trigger.Response()).success
    monkeypatch.setattr(bridge.time, 'monotonic', lambda: 101.)
    node.position_time = node.force_time = [101., 101.]
    bridge.CupForceGripper.tick(node)
    assert node.state == 'FAULT_BACKOFF_OVERFORCE' and not node.pending_overforce
