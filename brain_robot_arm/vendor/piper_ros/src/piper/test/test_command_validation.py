import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from piper.command_validation import validate_absolute_joint_state


def driver_method(name, **globals_for_test):
    """Compile only the requested function; never import a ROS node or SDK."""
    source = Path(__file__).resolve().parents[1] / 'piper' / 'piper_ctrl_single_node.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = {'Bool': object, **globals_for_test}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace[name]


class TestAbsoluteJointStateValidation(unittest.TestCase):
    def setUp(self):
        self.names = ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']
        self.positions = [0.1, 0.2, -0.3, 0.4, -0.5, 0.6]

    def test_accepts_complete_six_axis_command_in_any_order(self):
        values, reason = validate_absolute_joint_state(
            list(reversed(self.names)), list(reversed(self.positions)))
        self.assertIsNone(reason)
        self.assertEqual(values['joint1'], 0.1)
        self.assertEqual(values['joint6'], 0.6)

    def test_accepts_explicit_optional_gripper(self):
        values, reason = validate_absolute_joint_state(
            self.names + ['gripper'], self.positions + [0.02])
        self.assertIsNone(reason)
        self.assertEqual(values['gripper'], 0.02)

    def test_rejects_malformed_commands(self):
        cases = [
            (self.names[:-1], self.positions[:-1]),
            (self.names + ['joint1'], self.positions + [0.7]),
            (self.names[:-1] + ['other'], self.positions),
            (self.names, self.positions[:-1]),
            (self.names, self.positions[:-1] + [math.nan]),
        ]
        for names, positions in cases:
            with self.subTest(names=names, positions=positions):
                values, reason = validate_absolute_joint_state(names, positions)
                self.assertIsNone(values)
                self.assertIsNotNone(reason)

    def test_explicit_gripper_stream_uses_v2_handshake_then_steady_code(self):
        source_path = Path(__file__).resolve().parents[1] / 'piper' / 'piper_ctrl_single_node.py'
        tree = ast.parse(source_path.read_text(encoding='utf-8'))
        callback = next(node for node in ast.walk(tree)
                        if isinstance(node, ast.FunctionDef) and node.name == 'joint_callback')
        calls = [node for node in ast.walk(callback) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'GripperCtrl']
        calls.sort(key=lambda node: (node.lineno, node.col_offset))
        self.assertEqual(len(calls), 3)
        self.assertEqual([call.args[2].value for call in calls], [0x02, 0x01, 0x01])
        self.assertEqual([call.args[3].value for call in calls], [0x00, 0x00, 0x00])

    def test_both_arm_enable_entries_do_not_send_a_jaw_target(self):
        for entry in ('enable_callback', 'handle_enable_service'):
            for cache in (0, 30000, 80000, 101900):
                for gripper_exist in (False, True):
                    with self.subTest(entry=entry, cache=cache, gripper_exist=gripper_exist):
                        calls = []
                        logger = SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)
                        sdk = SimpleNamespace(
                            GetArmEnableStatus=lambda: [True] * 6,
                            GetArmGripperMsgs=lambda: SimpleNamespace(gripper_state=SimpleNamespace(grippers_angle=cache)),
                            GripperCtrl=lambda *args: calls.append(('gripper', args)))

                        def arm(speed):
                            calls.append(('arm', speed))
                            return True

                        fake = SimpleNamespace(piper=sdk, gripper_exist=gripper_exist,
                                               _gripper_clear_pending=False, get_logger=lambda: logger,
                                               _enable_for_joint_control=arm)
                        clock = SimpleNamespace(time=lambda: 0., sleep=lambda *_: None)
                        method = driver_method(entry, time=clock)
                        if entry == 'enable_callback':
                            method(fake, SimpleNamespace(data=True))
                        else:
                            response = method(fake, SimpleNamespace(enable_request=True), SimpleNamespace())
                            self.assertTrue(response.enable_response)
                        self.assertEqual(calls, [('arm', 50)])
                        self.assertTrue(getattr(fake, '__enable_flag'))
                        self.assertTrue(fake._gripper_clear_pending)

    def test_six_axis_hold_has_no_gripper_and_explicit_target_still_clears_once(self):
        calls = []
        logger = SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)
        sdk = SimpleNamespace(JointCtrl=lambda *args: calls.append(('joints', args)),
                              GripperCtrl=lambda *args: calls.append(('gripper', args)))
        fake = SimpleNamespace(piper=sdk, gripper_exist=True, gripper_val_mutiple=1.,
                               _gripper_clear_pending=True, get_logger=lambda: logger,
                               GetEnableFlag=lambda: True, _can_feedback_available=lambda: True,
                               _set_joint_control_mode=lambda *_: None)
        method = driver_method('joint_callback', math=math, ARM_JOINT_NAMES=self.names,
                               validate_absolute_joint_state=validate_absolute_joint_state,
                               clip=lambda value, lower, upper: max(lower, min(upper, value)))
        packet = SimpleNamespace(name=self.names, position=self.positions, velocity=[], effort=[])
        method(fake, packet)
        self.assertEqual([kind for kind, _ in calls], ['joints'])
        self.assertTrue(fake._gripper_clear_pending)
        packet.name = self.names + ['gripper']
        packet.position = self.positions + [.05]
        packet.effort = [0.] * 6 + [1.]
        method(fake, packet)
        method(fake, packet)
        self.assertEqual([args for kind, args in calls if kind == 'gripper'],
                         [(0, 1000, 0x02, 0), (0, 1000, 0x01, 0),
                          (50000., 1000, 0x01, 0), (50000., 1000, 0x01, 0)])

    def test_failed_arm_enable_does_not_clear_gate_or_inject_a_gripper_target(self):
        for entry in ('enable_callback', 'handle_enable_service'):
            with self.subTest(entry=entry):
                calls = []
                logger = SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)
                fake = SimpleNamespace(
                    piper=SimpleNamespace(GetArmEnableStatus=lambda: [False] * 6,
                                          GripperCtrl=lambda *args: calls.append(args)),
                    gripper_exist=True, _gripper_clear_pending=False,
                    get_logger=lambda: logger, _enable_for_joint_control=lambda _: False)
                ticks = iter(range(20))
                clock = SimpleNamespace(time=lambda: next(ticks), sleep=lambda *_: None)
                method = driver_method(entry, time=clock)
                if entry == 'enable_callback':
                    method(fake, SimpleNamespace(data=True))
                else:
                    response = method(fake, SimpleNamespace(enable_request=True), SimpleNamespace())
                    self.assertFalse(response.enable_response)
                self.assertFalse(getattr(fake, '__enable_flag'))
                self.assertFalse(fake._gripper_clear_pending)
                self.assertEqual(calls, [])

    def test_p4_handshake_preserves_actual_opening_and_never_targets_zero(self):
        calls = []
        logger = SimpleNamespace(info=lambda *_: None, warning=lambda *_: None, error=lambda *_: None)
        fake = SimpleNamespace(
            p4_gentle_gripper=True, _p4_gripper_sample=(10., None, .0796, .02, 0x40),
            _p4_gripper_output_allowed=lambda: True,
            piper=SimpleNamespace(JointCtrl=lambda *a: None, GripperCtrl=lambda *a: calls.append(a)),
            gripper_exist=True, gripper_val_mutiple=1., _gripper_clear_pending=True,
            get_logger=lambda: logger, GetEnableFlag=lambda: True,
            _can_feedback_available=lambda: True, _set_joint_control_mode=lambda *_: None)
        packet = SimpleNamespace(name=self.names+['gripper'], position=self.positions+[.08],
                                 velocity=[], effort=[0.]*6+[.5])
        method = driver_method('joint_callback', math=math, ARM_JOINT_NAMES=self.names,
            validate_absolute_joint_state=validate_absolute_joint_state,
            clip=lambda v, a, b: max(a, min(b, v)))
        method(fake, packet)
        self.assertEqual(calls, [(79600, 500, 0x02, 0), (79600, 500, 0x01, 0),
                                 (80000., 500, 0x01, 0)])

    def test_p4_gripper_frame_is_published_once_without_cache_restamping(self):
        emitted, statuses = [], []
        sample = (10., SimpleNamespace(sec=20, nanosec=30), .037, -.2, 0x40)
        fake = SimpleNamespace(_p4_gripper_sample=sample, _p4_published_gripper_sample=None,
            p4_gripper_pub=SimpleNamespace(publish=emitted.append),
            p4_gripper_status_pub=SimpleNamespace(publish=statuses.append))
        method = driver_method('_publish_p4_gripper_sample',
            JointState=lambda: SimpleNamespace(header=SimpleNamespace()), UInt8=SimpleNamespace)
        method(fake); method(fake)
        self.assertEqual(len(emitted), 1)
        self.assertIs(emitted[0].header.stamp, sample[1])
        self.assertEqual(emitted[0].position, [.037])
        self.assertEqual(emitted[0].effort, [-.2])
        self.assertEqual(statuses[0].data, 0x40)

    def test_p4_stale_gripper_or_fault_does_not_pass_output_check(self):
        method = driver_method('_p4_gripper_output_allowed',
            time=SimpleNamespace(monotonic=lambda: 10.))
        fake = SimpleNamespace(_p4_gripper_sample=None)
        self.assertFalse(method(fake))
        for sample_time, status in [(9., 0x40), (10., 0x44), (10., 0x41)]:
            fake._p4_gripper_sample = (sample_time, None, .037, .1, status)
            self.assertFalse(method(fake))
        fake._p4_gripper_sample = (9.9, None, .037, .1, 0x40)
        self.assertTrue(method(fake))

    def test_ros_logger_calls_use_one_positional_message(self):
        source_path = (
            Path(__file__).resolve().parents[1] /
            'piper' / 'piper_ctrl_single_node.py')
        tree = ast.parse(source_path.read_text(encoding='utf-8'))
        bad_calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Attribute):
                continue
            if function.attr not in {
                    'debug', 'info', 'warn', 'warning', 'error', 'fatal'}:
                continue
            if len(node.args) > 1:
                bad_calls.append((node.lineno, function.attr, len(node.args)))
        self.assertEqual(bad_calls, [])

if __name__ == '__main__':
    unittest.main()
