"""Check the launch-only finger range correction; never change arm geometry."""
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
    expected.find("joint[@name='joint7']/limit").set('upper', '0.04')
    expected.find("joint[@name='joint8']/limit").set('lower', '-0.04')
    expected.find("joint[@name='joint8']/limit").set('upper', '0.0')
    assert namespace['_physical_gripper_description'](original) == ET.tostring(expected, encoding='unicode')


def test_unknown_model_is_not_silently_rewritten():
    with pytest.raises(RuntimeError, match='Expected PiPER prismatic finger'):
        namespace['_physical_gripper_description']('<robot name="unknown"/>')
