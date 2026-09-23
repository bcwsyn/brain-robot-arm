"""Validation for absolute six-axis PiPER joint commands.

The vendor SDK transmits all six absolute joint targets in every JointCtrl
call.  A malformed ROS JointState must therefore be rejected before it can
be converted to controller units or reach any CAN control API.
"""

import math


ARM_JOINT_NAMES = (
    'joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6',
)
OPTIONAL_JOINT_NAMES = frozenset(('gripper',))
ALLOWED_JOINT_NAMES = frozenset(ARM_JOINT_NAMES) | OPTIONAL_JOINT_NAMES


def validate_absolute_joint_state(names, positions):
    """Return a validated name-to-radian mapping or ``(None, reason)``.

    A valid command names every arm joint exactly once.  The gripper is
    optional and is only included in the result when explicitly commanded.
    """
    if len(names) != len(positions):
        return None, 'name/position length mismatch'

    values = {}
    for name, position in zip(names, positions):
        if name not in ALLOWED_JOINT_NAMES:
            return None, f'unknown joint name: {name}'
        if name in values:
            return None, f'duplicate joint name: {name}'
        try:
            value = float(position)
        except (TypeError, ValueError):
            return None, f'non-numeric position for {name}'
        if not math.isfinite(value):
            return None, f'non-finite position for {name}'
        values[name] = value

    missing = [name for name in ARM_JOINT_NAMES if name not in values]
    if missing:
        return None, 'missing arm joints: ' + ', '.join(missing)
    return values, None
