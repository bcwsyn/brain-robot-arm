import math
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


if __name__ == '__main__':
    unittest.main()
