"""Compile the actual Astra TF math offline; no ROS graph, cameras or CAN."""
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

REPO = Path(__file__).resolve().parents[5]
SOURCE = REPO / 'brain_robot_arm/ros2_ws/src/ros2_astra_camera/astra/src/astra_camera'
FACTORY = REPO / 'docs/evidence/piper_board_handeye_20261016/usb31_mount_deploy01/factory.json'


def function_body(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    level = 1
    for i in range(opening + 1, len(source)):
        level += (source[i] == '{') - (source[i] == '}')
        if not level:
            return source[opening + 1:i]
    raise AssertionError('Unclosed source function')


def compile_tf_math(tmp_path, rotation, translation):
    """Execute unchanged production calculation prefix and conversion helper."""
    node = (SOURCE / 'src/ob_camera_node.cpp').read_text()
    body = function_body(node, 'void OBCameraNode::calcAndPublishStaticTransform()')
    prefix = body.split('  rclcpp::Time tf_timestamp =')[0]
    helper = function_body((SOURCE / 'src/utils.cpp').read_text(),
                           'tf2::Quaternion rotationMatrixToQuaternion(')
    # The existing publishStaticTF optical->ROS mapping must stay unchanged.
    publisher = function_body(node, 'void OBCameraNode::publishStaticTF(')
    for field, expression in [('x', 'trans.at(2)'), ('y', '-trans.at(0)'), ('z', '-trans.at(1)')]:
        assert f'msg.transform.translation.{field} = {expression} / 1000.0;' in publisher
    cpp = '''#include <cmath>
#include <iostream>
#include <iomanip>
#include <vector>
#include <Eigen/Dense>
#include <tf2/LinearMath/Quaternion.h>
tf2::Quaternion rotationMatrixToQuaternion(const float rotation[9]) {HELPER}
struct Params {float r2l_r[9]; float r2l_t[3];};
int main() {
 Params params = {{ROTATION},{TRANSLATION}};
 auto camera_params_ = &params;
 PREFIX
 std::cout << std::setprecision(17) << "[" << trans[2]/1000.0 << ","
   << -trans[0]/1000.0 << "," << -trans[1]/1000.0 << ","
   << Q.x() << "," << Q.y() << "," << Q.z() << "," << Q.w() << "]";
}
'''.replace('HELPER', helper).replace('ROTATION', ','.join(f'{v:.17g}' for v in rotation))
    cpp = cpp.replace('TRANSLATION', ','.join(f'{v:.17g}' for v in translation)).replace('PREFIX', prefix)
    path = tmp_path / 'actual_tf_math.cpp'
    path.write_text(cpp)
    binary = tmp_path / 'actual_tf_math'
    subprocess.run(['g++', '-std=c++17', '-I/usr/include/eigen3',
                    '-I/opt/ros/humble/include/tf2', str(path), '-o', str(binary)],
                   capture_output=True, text=True, check=True, timeout=20)
    output = subprocess.run([str(binary)], capture_output=True, text=True, check=True, timeout=2)
    values = json.loads(output.stdout)
    matrix = np.eye(4)
    matrix[:3, :3] = Rotation.from_quat(values[3:]).as_matrix()
    matrix[:3, 3] = values[:3]
    # Q above ends at camera_color_frame. The unchanged next TF edge rotates
    # color optical into that frame; omitting it tests the wrong frame.
    return matrix @ optical_to_link(), values


def optical_to_link():
    matrix = np.eye(4)
    matrix[:3, :3] = Rotation.from_euler('xyz', [-np.pi / 2, 0, -np.pi / 2]).as_matrix()
    return matrix


def test_factory_inverse_composes_back_to_depth_to_color(tmp_path):
    params = json.loads(FACTORY.read_text())['get_camera_params']
    actual, _ = compile_tf_math(tmp_path, params['r2l_r'], params['r2l_t'])
    color_from_depth = np.linalg.inv(actual) @ optical_to_link()
    assert color_from_depth[:3, :3] == pytest.approx(np.array(params['r2l_r']).reshape(3, 3), abs=1e-7)
    assert color_from_depth[:3, 3] == pytest.approx(np.array(params['r2l_t']) * .001, abs=2e-9)


@pytest.mark.parametrize('translation', [[0, 0, 0], [31, -7, 4], [-21, 13, 11]])
def test_nontrivial_inverse_translation_not_just_negation(tmp_path, translation):
    r = Rotation.from_euler('xyz', [.2, -.3, .4]).as_matrix()
    actual, _ = compile_tf_math(tmp_path, r.ravel(), translation)
    expected = np.eye(4)
    expected[:3, :3] = r
    expected[:3, 3] = np.asarray(translation) * .001
    assert np.linalg.inv(actual) @ optical_to_link() == pytest.approx(expected, abs=1e-7)
