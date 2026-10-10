import ast
import math
from pathlib import Path
import unittest

from piper.command_validation import validate_absolute_joint_state


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

    def test_explicit_gripper_stream_uses_clear_then_steady_code(self):
        source_path = Path(__file__).resolve().parents[1] / 'piper' / 'piper_ctrl_single_node.py'
        tree = ast.parse(source_path.read_text(encoding='utf-8'))
        callback = next(node for node in ast.walk(tree)
                        if isinstance(node, ast.FunctionDef) and node.name == 'joint_callback')
        calls = [node for node in ast.walk(callback) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'GripperCtrl']
        self.assertEqual(len(calls), 1)
        self.assertIsInstance(calls[0].args[2], ast.Name)
        self.assertEqual(calls[0].args[2].id, 'gripper_code')
        self.assertEqual(calls[0].args[3].value, 0x00)

    def test_enable_service_holds_measured_jaw_instead_of_closing_to_zero(self):
        source_path = Path(__file__).resolve().parents[1] / 'piper' / 'piper_ctrl_single_node.py'
        tree = ast.parse(source_path.read_text(encoding='utf-8'))
        callback = next(node for node in ast.walk(tree)
                        if isinstance(node, ast.FunctionDef) and node.name == 'handle_enable_service')
        calls = [node for node in ast.walk(callback) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'GripperCtrl'
                 and isinstance(node.args[0], ast.Name) and node.args[0].id == 'held_gripper']
        self.assertEqual([node.args[2].value for node in calls], [0x02, 0x01])
        self.assertTrue(all(node.args[3].value == 0 for node in calls))

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
