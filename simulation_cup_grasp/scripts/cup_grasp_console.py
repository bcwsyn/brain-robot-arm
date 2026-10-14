#!/usr/bin/env python3
"""Simulation-only cup integration: learned sizing, physical contact and force loop."""
import argparse
from contextlib import nullcontext
import fcntl
import json
import math
import os
from pathlib import Path
import socket
import sys
import hashlib
from copy import deepcopy
import tarfile
import time
import xml.etree.ElementTree as ET

import numpy as np
import yaml

from visual_sim_console import VisualSession, Keyboard, BatchKeyboard, QuitRequested

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS / 'src/brain_robot_pick_place/scripts'))
from cup_geometry import CupSpec, write_model
from contact_force_feedback import target_normal_force


class CupSession(VisualSession):
    def __init__(self, args, keyboard):
        super().__init__(args, keyboard)
        # Tall cups need clearance from the forearm at the release pose.
        self.zones = {'1': ('A', .43, .12), '2': ('B', .44, .16)}
        from std_msgs.msg import String, Bool
        from sensor_msgs.msg import Image
        from visualization_msgs.msg import MarkerArray
        from rclpy.qos import qos_profile_sensor_data
        from geometry_msgs.msg import TransformStamped
        from tf2_ros import StaticTransformBroadcaster
        from scipy.spatial.transform import Rotation
        self.clients['start'] = self.node.create_client(self.Trigger, '/grasp_lift_executor/execute')
        self.clients['stop'] = self.node.create_client(self.Trigger, '/grasp_lift_executor/stop')
        self.vision, self.vision_time, self.force_data = None, 0., None
        self.last_valid_vision = None
        self.executor_ready = False
        self.contact_packets_saved = set()
        self.last_debug_image = None
        self.force_image = self.node.create_publisher(Image, '/cup_task/live_debug_image', 1)
        self.force_markers = self.node.create_publisher(MarkerArray, '/cup_task/status_markers', 1)
        self.node.create_timer(.2, self.publish_force_view)
        self.fault_injected = False
        if args.fault in ('feedback-loss', 'overforce'):
            service = 'feedback_loss' if args.fault == 'feedback-loss' else 'overforce'
            self.clients['inject'] = self.node.create_client(self.Trigger, '/cup_gripper/inject_' + service)
        sources = ['src/brain_robot_pick_place/src/grasp_lift_executor.cpp',
                   'src/brain_robot_pick_place/scripts/cup_force_gripper_node.py',
                   'src/brain_robot_pick_place/scripts/contact_force_feedback.py',
                   'src/brain_robot_pick_place/scripts/adaptive_gripper_policy.py',
                   'src/brain_robot_pick_place/scripts/cup_width_estimation.py',
                   'src/brain_robot_pick_place/scripts/cup_perception.py',
                   'src/brain_robot_pick_place/scripts/cup_geometry.py',
                   'src/brain_robot_pick_place/scripts/yolo_cup_target_node.py',
                   'src/brain_robot_pick_place/scripts/scene_manager_node.py',
                   'scripts/cup_grasp_console.py', 'scripts/visual_sim_console.py',
                   'src/brain_robot_pick_place/launch/cup_task.launch.py',
                   'src/piper_description/urdf/piper_description_gazebo.xacro',
                   'src/piper_gazebo/config/ros2_controllers.yaml',
                   'src/brain_robot_pick_place/launch/wrist_camera_gazebo.launch.py',
                   'src/brain_robot_pick_place/config/gazebo_clock_default.yaml',
                   'config/gazebo_clock_cup.yaml', 'config/cup_grasp.rviz']
        with tarfile.open(self.output / 'source_snapshot.tar.gz', 'w:gz') as archive:
            for name in sources:
                archive.add(self.workspace / name, arcname=name)
        (self.output / 'source_hashes.json').write_text(json.dumps(
            {name: hashlib.sha256((self.workspace / name).read_bytes()).hexdigest() for name in sources}, indent=2) + '\n')
        self.subscriptions.extend([
            self.node.create_subscription(String, '/brain_robot_vision/cup_diagnostic', self.on_vision, 10),
            self.node.create_subscription(String, '/cup_gripper/diagnostic', self.on_force, 10),
            self.node.create_subscription(Image, '/cup_probe/view1/camera/image_raw', self.on_camera,
                                          qos_profile_sensor_data),
            self.node.create_subscription(Image, '/brain_robot_vision/cup_debug_image',
                                          self.on_debug_image, qos_profile_sensor_data),
        ])
        # Fixed external RGB-D calibration. Object truth is never broadcast as a target TF.
        xyz, target = np.array([.08, -.4, .24]), np.array([.40, -.10, .12])
        forward = (target - xyz) / np.linalg.norm(target - xyz)
        yaw = math.atan2(forward[1], forward[0])
        right = np.array([math.sin(yaw), -math.cos(yaw), 0.])
        rotation = np.column_stack((right, np.cross(forward, right), forward))
        self.camera_xyz = xyz.tolist()
        self.camera_pitch, self.camera_yaw = -math.asin(forward[2]), yaw
        self.broadcaster = StaticTransformBroadcaster(self.node)
        tf = TransformStamped()
        tf.header.frame_id, tf.child_frame_id = 'world', 'cup_observer_optical'
        tf.transform.translation.x, tf.transform.translation.y, tf.transform.translation.z = xyz.tolist()
        q = Rotation.from_matrix(rotation).as_quat()
        tf.transform.rotation.x, tf.transform.rotation.y, tf.transform.rotation.z, tf.transform.rotation.w = q.tolist()
        self.broadcaster.sendTransform(tf)
        self.world = self.make_world()
        (self.output / 'scope.json').write_text(json.dumps(dict(
            camera='fixed external RGB-D with static calibration',
            target='YOLO learned mask and depth; no Gazebo pose for grasp target',
            retention='Gazebo object height and contacts used only for independent acceptance',
            total_stroke_m=.100, force_band_n=[2.5, 3.5], hard_force_limit_n=5.,
            body_diameter_truth_m=args.diameter_mm / 1000,
            mass_kg=.080, mass_is_measured=False, wall_thickness_m=.002,
            clock_publish_hz=100., joint_tf_publish_hz=50., visualization_fps=10,
            symmetric_single_opening_command=True), indent=2) + '\n')

    def make_world(self):
        root = ET.parse(self.workspace / 'validation/grasp_validation.world')
        physics = root.getroot().find('world/physics')
        solver = ET.SubElement(ET.SubElement(physics, 'ode'), 'solver')
        ET.SubElement(solver, 'type').text = 'quick'
        ET.SubElement(solver, 'iters').text = '200'
        x, y, z = self.camera_xyz
        camera = ET.fromstring(f'''<model name="cup_observer"><static>true</static>
          <pose>{x} {y} {z} 0 {self.camera_pitch} {self.camera_yaw}</pose><link name="camera">
          <sensor name="rgbd" type="depth"><always_on>true</always_on><update_rate>5</update_rate>
          <camera><horizontal_fov>1.0471975512</horizontal_fov><image><width>640</width><height>480</height>
          <format>R8G8B8</format></image><clip><near>.05</near><far>2</far></clip></camera>
          <plugin name="cup_observer_rgbd" filename="libgazebo_ros_camera.so">
          <ros><namespace>/cup_probe/view1</namespace></ros><camera_name>camera</camera_name>
          <frame_name>cup_observer_optical</frame_name><min_depth>.05</min_depth><max_depth>2</max_depth>
          </plugin></sensor></link></model>''')
        root.getroot().find('world').append(camera)
        path = self.output / 'cup_integration.world'
        root.write(path, encoding='utf-8', xml_declaration=True)
        return path

    def on_vision(self, msg):
        self.vision, self.vision_time = json.loads(msg.data), time.monotonic()
        if self.vision['status'] == 'VALID':
            self.last_valid_vision = self.vision
        self.record(cup_vision=self.vision)

    def on_camera(self, msg):
        if msg.header.frame_id == 'cup_observer_optical':
            super().on_camera(msg)

    def on_models(self, msg):
        super().on_models(msg)
        if self.model in msg.name:
            q = msg.pose[msg.name.index(self.model)].orientation
            self.object_tilt_rad = math.acos(max(-1., min(1., 1 - 2*(q.x*q.x + q.y*q.y))))
            if self.active_run and self.active_run.get('model_samples'):
                self.active_run['model_samples'][-1]['tilt_rad'] = self.object_tilt_rad

    def on_force(self, msg):
        self.force_data = json.loads(msg.data)
        if self.active_run:
            self.record(cup_force=self.force_data)
            self.active_run.setdefault('force_samples', []).append(dict(
                **self.force_data, grasp_state=self.state['grasp']))

    def on_debug_image(self, msg):
        self.last_debug_image = msg
        self.mark_image('detection')

    def publish_force_view(self):
        from visualization_msgs.msg import Marker, MarkerArray
        from sensor_msgs.msg import Image
        import cv2
        force, vision = self.force_data, self.last_valid_vision
        if not force:
            return
        opening = force['measured_opening_m'] * 1000
        left, right = force['force_n']
        diameter = vision.get('diameter_m', float('nan')) * 1000 if vision else float('nan')
        lines = [f'Cup D: {diameter:.1f} mm | Opening: {opening:.1f} mm',
                 f'Left: {left:.2f} N | Right: {right:.2f} N',
                 f"{self.state['grasp']} | {force['state']}"]
        marker = Marker()
        marker.header.frame_id = 'world'
        marker.ns, marker.id, marker.type, marker.action = 'cup_status', 0, Marker.TEXT_VIEW_FACING, Marker.ADD
        marker.pose.position.x, marker.pose.position.y, marker.pose.position.z = .40, 0., .43
        marker.pose.orientation.w, marker.scale.z = 1., .016
        marker.color.r, marker.color.g, marker.color.b, marker.color.a = .1, .7, .2, 1.
        marker.pose.position.z = .32
        marker.scale.z = .02
        marker.text = f'Grip {left:.1f} / {right:.1f} N'
        self.force_markers.publish(MarkerArray(markers=[marker]))
        msg = self.last_debug_image
        if msg is not None and msg.encoding == 'bgr8':
            color = np.ndarray((msg.height, msg.width, 3), dtype=np.uint8,
                               buffer=bytes(msg.data), strides=(msg.step, 3, 1)).copy()
            panel = np.zeros((100, msg.width, 3), np.uint8)
            for i, line in enumerate(lines):
                cv2.putText(panel, line, (10, 24 + i*30), cv2.FONT_HERSHEY_SIMPLEX,
                            .48, (240, 240, 240), 1, cv2.LINE_AA)
            color = np.vstack((color, panel))
            output = Image(header=deepcopy(msg.header), height=color.shape[0], width=color.shape[1],
                           encoding='bgr8', step=color.shape[1]*3, data=color.tobytes())
            self.force_image.publish(output)

    def check_state(self):
        if (self.args.fault in ('feedback-loss', 'overforce') and not self.fault_injected
                and self.active_run and self.state['grasp'] == 'LIFTING_PHYSICAL_OBJECT'
                and self.active_run['maximum_z'] >= self.active_run['initial_xyz'][2] + .025):
            self.fault_injected = True
            self.record(injected_fault=self.args.fault)
            self.request('inject')
        previous = self.mode
        super().check_state()
        if previous != 'FINISHED' and self.mode == 'FINISHED':
            run = self.runs[-1]
            holding = [s for s in run['force_samples']
                       if s['grasp_state'] == 'HOLDING_PHYSICAL_OBJECT' and s['mode'] == 'HOLD']
            forces = [s['force_n'] for s in holding]
            run['hold_force_samples'] = len(holding)
            run['hold_force_range_n'] = [[min(f[i] for f in forces), max(f[i] for f in forces)]
                                         for i in (0, 1)] if forces else None
            run['force_acceptance_passed'] = bool(holding) and all(
                s['healthy'] and not s['injected_fault'] and max(s['force_age_s']) <= .2
                and all(2.5 <= f <= 3.5 for f in s['force_n']) for s in holding)
            run['final_tilt_rad'] = self.object_tilt_rad
            run['passed'] = run['passed'] and run['force_acceptance_passed'] and self.object_tilt_rad < .12
            self.save_summary()
            if not run['passed']:
                self.fault('物理取放结束，但保持阶段双侧力验收未通过')

    def fault(self, reason):
        super().fault(reason)
        if (self.args.fault or self.args.physics_negative) and not getattr(self, 'fault_observed', False):
            self.fault_observed = True
            until = time.monotonic() + 2.
            self.wait(lambda: time.monotonic() >= until, 3., '故障后停止反馈观察')

    def on_contacts(self, msg, index):
        super().on_contacts(msg, index)
        value, count = target_normal_force(msg, self.model, require_step_time=True)
        if value > .5 and index not in self.contact_packets_saved:
            from rosidl_runtime_py.convert import message_to_ordereddict
            self.contact_packets_saved.add(index)
            (self.output / f'raw_contacts_link{index+7}.json').write_text(json.dumps(dict(
                latest_step_force_n=value, latest_step_points=count,
                message=message_to_ordereddict(msg)), indent=2) + '\n')

    def on_grasp(self, msg):
        super().on_grasp(msg)
        if msg.data in ('COMPLETE', 'WAITING_FOR_GRASP_REQUEST'):
            self.state['visual'] = 'IDLE'
        elif msg.data == 'CONTROLLED_STOP':
            self.state['visual'] = 'STOPPED'
        elif msg.data.startswith('FAULT_'):
            self.state['visual'] = 'FAULT'
        else:
            self.state['visual'] = 'GRASPING'

    def on_joints(self, msg):
        super().on_joints(msg)
        if self.active_run and self.joints is not None:
            samples = self.active_run.setdefault('joint_samples', [])
            elapsed = time.monotonic() - self.active_run['started']
            if not samples or elapsed - samples[-1]['elapsed_s'] >= .05:
                samples.append(dict(elapsed_s=elapsed, positions=list(self.joints),
                                    grasp_state=self.state['grasp']))

    def on_diagnostic(self, msg):
        if msg.data == 'CUP_EXECUTOR_READY':
            self.executor_ready = True
        self.record(cup_executor_diagnostic=msg.data)
        super().on_diagnostic(msg)

    def prepare_scene_profile(self):
        path = super().prepare_scene_profile()
        profile = yaml.safe_load(path.read_text())
        spec = CupSpec(body_diameter_m=self.args.diameter_mm / 1000,
                       mouth_diameter_m=self.args.diameter_mm * .84 / 1000)
        model = write_model(self.output / f'cup_model_{self.scene_index:03d}', spec, name=self.model,
                            compact_bottom=True)
        profile['scene_manager']['ros__parameters'].update(cup_radius=spec.body_diameter_m / 2,
            cup_height=spec.height_m, cup_z=spec.height_m / 2, cup_model_sdf=str(model))
        path.write_text(yaml.safe_dump(profile, sort_keys=False))
        self.expected_pose[2] = spec.height_m / 2
        task = yaml.safe_load(self.physics_task_profile.read_text())
        task['grasp_lift_executor']['ros__parameters'].update(
            adaptive_cup_enabled=True, known_position_task=False, auto_execute=False,
            target_point_topic='/brain_robot_vision/cup_grasp_point',
            target_size_topic='/brain_robot_vision/grasp_width',
            depth_valid_topic='/brain_robot_vision/cup_target_valid',
            physics_object_width_m=0., top_down_tilt_candidates=[1.2, 1.0, .70],
            gripper_tip_offset_m=.130, grasp_center_offset_m=.130,
            linear_approach_velocity_scaling=.03,
            top_down_pregrasp_clearance_m=.10)
        self.physics_task_profile.write_text(yaml.safe_dump(task, sort_keys=False))
        return path

    def bootstrap(self):
        self.mode = 'LOADING'
        self.executor_ready, self.force_data = False, None
        self.vision = None
        self.last_valid_vision, self.last_debug_image = None, None
        self.contact_latest = [0., 0.]
        self.generation += 1
        self.clear_state()
        self.say('1/5', '加载 Gazebo 虚拟机械臂、物理指垫和固定 RGB-D 相机…')
        self.launch_ros('gazebo', 'brain_robot_pick_place', 'wrist_camera_gazebo.launch.py',
                        'gui:=false', 'physics_grasp:=true', 'physics_jaw_kp:=300',
                        'physics_jaw_kd:=0.5', 'state_publish_frequency:=50.0',
                        'gazebo_params_file:=' + str(self.workspace / 'config/gazebo_clock_cup.yaml'),
                        'world:=' + str(self.world))
        client = self.clients['controllers']
        self.wait(client.service_is_ready, 60, '控制器服务')
        discovered = time.monotonic()
        self.wait(lambda: time.monotonic() - discovered >= 2., 3, '控制器服务发现稳定')
        future = None
        def active():
            nonlocal future
            if future is None:
                future = client.call_async(self.ListControllers.Request())
            if not future.done():
                return False
            controllers = {c.name for c in future.result().controller if c.state == 'active'}
            future = None
            return {'joint_state_broadcaster', 'arm_controller', 'gripper_controller', 'gripper8_controller'} <= controllers
        self.wait(active, 60, '虚拟控制器激活')
        self.wait(lambda: self.joints is not None and max(abs(v) for v in self.joints) < .001,
                  20, '虚拟零位反馈')
        if not self.args.headless:
            self.launch('gazebo-window', ['gzclient'])
        self.say('2/5', '加载 MoveIt…')
        self.launch_ros('moveit', 'piper_with_gripper_moveit', 'piper_moveit.launch.py', 'start_rviz:=false')
        self.wait(self.clients['planning'].service_is_ready, 60, 'MoveIt 场景服务')
        if not self.args.headless:
            layout = (self.workspace / 'config/visual_grasp.rviz').read_text().replace(
                '/brain_robot_vision/debug_image', '/cup_task/live_debug_image').replace(
                '/wrist_camera/wrist_camera/image_raw', '/cup_probe/view1/camera/image_raw')
            layout = layout.replace('Name: Wrist Camera', 'Name: Cup RGB-D Camera')
            layout = layout.replace('Name: Target Detection', 'Name: Cup Detection and Grip Force')
            settings = yaml.safe_load(layout)
            settings['Visualization Manager']['Displays'].append(dict(
                Class='rviz_default_plugins/MarkerArray', Name='Cup Grip Status', Enabled=True,
                Value=True, Topic={'Value': '/cup_task/status_markers', 'Reliability Policy': 'Reliable',
                                  'Durability Policy': 'Volatile', 'History Policy': 'Keep Last', 'Depth': 5}))
            layout = yaml.safe_dump(settings, sort_keys=False)
            rviz = self.output / 'cup_view.rviz'
            preset = self.workspace / 'config/cup_grasp.rviz'
            rviz.write_text(preset.read_text() if preset.is_file() else layout)
            self.launch('rviz-window', ['rviz2', '-d', str(rviz), '--ros-args', '-r',
                '__node:=cup_grasp_viewer', '-p', 'use_sim_time:=true'],
                dict(os.environ, LIBGL_ALWAYS_SOFTWARE='1', __GLX_VENDOR_LIBRARY_NAME='mesa'))
        self.say('3/5', '创建 200 mm 中空台阶杯…')
        self.load_scene()
        self.say('4/5', '加载训练后的 YOLO 与 RGB-D 估径…')
        self.launch('yolo', [str(self.workspace / '.venv-yolo/bin/python'), '-s',
            str(self.workspace / 'src/brain_robot_pick_place/scripts/yolo_cup_target_node.py'),
            '--ros-args', '-p', 'use_sim_time:=true', '-p',
            'evidence_directory:=' + str(self.output / 'locked_frames'), '-p',
            'grasp_height_fraction:=0.60', '-p',
            'model:=' + str(self.workspace / 'models/cup_yolov8n_seg_v2.pt'),
            '-p', 'rgb_topic:=/cup_probe/view1/camera/image_raw',
            '-p', 'depth_topic:=/cup_probe/view1/camera/depth/image_raw',
            '-p', 'camera_info_topic:=/cup_probe/view1/camera/camera_info'])
        if self.args.fault == 'oversize':
            self.wait(lambda: self.vision is not None and self.vision['status'] == 'REJECTED'
                      and any(word in self.vision.get('reason', '') for word in ('stroke', 'clearance')),
                      50, '超开口目标被视觉尺寸策略拒绝')
            self.mode = 'BLOCKED'
            result = dict(expected_rejection=True, reason=self.vision['reason'],
                          no_task_executor_launched=True, home_error_rad=max(abs(v) for v in self.joints))
            (self.output / 'negative_result.json').write_text(json.dumps(result, indent=2) + '\n')
            return
        self.wait(lambda: self.vision is not None and self.vision['status'] == 'VALID'
                  and time.monotonic() - self.vision_time < .5, 50, 'YOLO 单杯定位与估径')
        self.record(initial_cup_vision=self.vision)
        self.say('5/5', '加载独立水杯执行器与接触力闭环…')
        self.launch_ros('task', self.package, 'cup_task.launch.py',
                        'params_file:=' + str(self.physics_task_profile),
                        'allow_fault_injection:=' + str(bool(self.args.fault)).lower())
        self.wait(lambda: self.executor_ready and self.force_data is not None
                  and self.force_data['ready_for_commands']
                  and abs(self.force_data['sim_time_s'] - self.sim_time_s) <= .3 and
                  all(self.clients[k].service_is_ready() for k in ('start', 'stop', 'placement')),
                  40, '水杯执行器')
        self.state['visual'] = 'IDLE'
        self.mode = 'READY'
        self.set_placement(self.selected_zone)
        self.say('就绪', 'S 视觉估径抓取 | 1/2 放置区 | R 复位 | X 停止 | Q 退出')

    def run(self):
        if self.args.fault == 'oversize':
            self.bootstrap()
            return
        super().run()

    def handle_key(self, key):
        if key == 'r' and self.mode in ('FINISHED', 'READY'):
            self.wait(lambda: not self.state['owned'] and self.joints is not None
                      and time.monotonic() - self.joint_time <= .5
                      and max(abs(v) for v in self.joints) < .02, 5., '复位前新鲜回零反馈')
            # Gazebo Classic hot deletion of the compound cup triggered a
            # heap error during repeat trials. Recreate our complete isolated
            # session between planned trials, without retrying failed motions.
            self.say('复位', '重新加载本轮水杯仿真和随机场景…')
            self.teardown()
            self.pending.clear()
            self.bootstrap()
            return
        super().handle_key(key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--seed', type=int)
    parser.add_argument('--batch-trials', type=int, default=0)
    parser.add_argument('--diameter-mm', type=float, default=75.)
    parser.add_argument('--physics-negative', choices=['miss', 'drop', 'stop'])
    parser.add_argument('--fault', choices=['feedback-loss', 'overforce', 'oversize'])
    args = parser.parse_args()
    maximum_diameter = 120 if args.fault == 'oversize' else 95
    if not 35 <= args.diameter_mm <= maximum_diameter or not 0 <= args.batch_trials <= 20:
        parser.error('Supported specimen diameter 35..95 mm; batch count 0..20')
    if args.batch_trials and (not args.headless or args.seed is None):
        parser.error('Batch requires --headless and --seed')
    if (args.fault or args.physics_negative) and args.batch_trials != 1:
        parser.error('Explicit simulation fault tests require exactly one batch trial')
    if args.fault and args.physics_negative:
        parser.error('Choose one fault injection per trial')
    if not args.batch_trials and not sys.stdin.isatty():
        parser.error('Interactive mode needs a terminal')
    args.task, args.physics = 'cup', True
    (WS / 'log').mkdir(exist_ok=True)
    with (WS / 'log/cup_grasp.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 11485))
        session = None
        keyboard = BatchKeyboard() if args.batch_trials else Keyboard()
        try:
            with (nullcontext(keyboard) if args.batch_trials else keyboard):
                session = CupSession(args, keyboard)
                session.run()
        except (KeyboardInterrupt, QuitRequested):
            return 0
        except Exception as error:
            print(f'Cup simulation failed: {error}', file=sys.stderr, flush=True)
            return 1
        finally:
            if session:
                session.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
