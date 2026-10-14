"""Check authorized launch-only position bounds; never change arm geometry."""
import ast
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

LAUNCH = Path(__file__).parents[2] / 'brain_robot_ball_pick/launch/cube_visual_search.launch.py'
helper = next(node for node in ast.parse(LAUNCH.read_text()).body
              if isinstance(node, ast.FunctionDef) and node.name == '_physical_gripper_description')
namespace = {'ET': ET}
exec(compile(ast.Module(body=[helper], type_ignores=[]), str(LAUNCH), 'exec'), namespace)


def test_only_finger_position_bounds_are_updated():
    original = '''<robot name="piper"><joint name="joint1" type="revolute">
      <limit lower="-2.6" upper="2.6" velocity="3" effort="10"/></joint>
      <joint name="joint7" type="prismatic"><origin xyz="0 0 .1358" rpy="1.5708 0 0"/>
      <limit lower="0" upper=".035" velocity="1" effort="10"/></joint>
      <joint name="joint8" type="prismatic"><origin xyz="0 0 .1358" rpy="1.5708 0 -3.1416"/>
      <limit lower="-.035" upper="0" velocity="1" effort="10"/></joint></robot>'''
    expected = ET.fromstring(original)
    expected.find("joint[@name='joint7']/limit").set('lower', '0.0')
    expected.find("joint[@name='joint7']/limit").set('upper', '0.05')
    expected.find("joint[@name='joint8']/limit").set('lower', '-0.05')
    expected.find("joint[@name='joint8']/limit").set('upper', '0.0')
    assert namespace['_physical_gripper_description'](original) == ET.tostring(expected, encoding='unicode')


def test_unknown_model_is_not_silently_rewritten():
    with pytest.raises(RuntimeError, match='Expected PiPER prismatic finger'):
        namespace['_physical_gripper_description']('<robot name="unknown"/>')


def test_configured_j5_upper_changes_no_other_arm_or_geometry_fields():
    original = '''<robot name="piper"><joint name="joint1" type="revolute">
      <limit lower="-2.6" upper="2.6" velocity="3" effort="10"/></joint>
      <joint name="joint5" type="revolute"><origin xyz=".1 0 .2" rpy="0 0 1"/>
      <axis xyz="0 0 1"/><limit lower="-1.22" upper="1.22" velocity="3" effort="10"/></joint>
      <joint name="joint7" type="prismatic"><limit lower="0" upper=".035" velocity="1" effort="10"/></joint>
      <joint name="joint8" type="prismatic"><limit lower="-.035" upper="0" velocity="1" effort="10"/></joint></robot>'''
    expected = ET.fromstring(namespace['_physical_gripper_description'](original))
    expected.find("joint[@name='joint5']/limit").set('upper', '1.22108')
    actual = namespace['_physical_gripper_description'](original, joint5_upper=1.22108)
    assert actual == ET.tostring(expected, encoding='unicode')


def test_requested_j5_override_requires_real_joint5():
    original = '''<robot name="piper">
      <joint name="joint7" type="prismatic"><limit lower="0" upper=".035"/></joint>
      <joint name="joint8" type="prismatic"><limit lower="-.035" upper="0"/></joint></robot>'''
    with pytest.raises(RuntimeError, match='Expected PiPER revolute joint5'):
        namespace['_physical_gripper_description'](original, joint5_upper=1.22108)


def test_observation_retains_measured_five_axes_and_sets_j5_to_70_degrees():
    import json
    import yaml
    root = next(p for p in Path(__file__).resolve().parents if (p / 'CODEX_TASK_PROMPT.md').exists())
    recorded = json.loads((root / 'docs/evidence/piper_new_observation_pose_20261014.json').read_text())
    task = yaml.safe_load((LAUNCH.parent.parent / 'config/cube_task_real.yaml').read_text())
    goal = task['visual_search_controller']['ros__parameters']['observe_joint_positions']
    for i in (0, 1, 2, 3, 5):
        assert abs(goal[i] - recorded['q_ros_rad'][i]) < 1e-12
    assert abs(goal[4] - 70 * .017444) < 1e-12
    grasp = task['grasp_lift_executor']['ros__parameters']
    assert goal[4] == grasp['real_trajectory_joint_max'][4]
    assert all(lo <= v <= hi for v, lo, hi in zip(
        goal, grasp['real_trajectory_joint_min'], grasp['real_trajectory_joint_max']))
    # Keep the original driver rounding: no requested target exceeds firmware +70 deg.
    assert round(goal[4] * 57324.840764) <= 70000
