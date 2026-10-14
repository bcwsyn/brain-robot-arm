#!/usr/bin/env python3
"""Own a Gazebo-only visual session; S starts, R resets, X stops, Q exits.

Use the shell entry points to load the simulation overlay. Every subprocess has
its own process group. No real-robot package or known-position task is launched.
"""
import argparse
from contextlib import nullcontext
import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import random
import select
import shutil
import signal
import socket
import subprocess
import sys
import termios
import time
import tty


class QuitRequested(Exception):
    pass


class Keyboard:
    def __enter__(self):
        self.original = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
        return self

    def read(self):
        if select.select([sys.stdin], [], [], 0)[0]:
            return os.read(sys.stdin.fileno(), 1).decode(errors='ignore').lower()
        return ''

    def __exit__(self, *_):
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.original)


class BatchKeyboard:
    def read(self):
        return ''


class VisualSession:
    def __init__(self, args, keyboard):
        import rclpy
        from rclpy.signals import SignalHandlerOptions
        from rclpy.qos import QoSProfile, DurabilityPolicy, qos_profile_sensor_data
        from controller_manager_msgs.srv import ListControllers
        from gazebo_msgs.msg import ModelStates, ContactsState
        from moveit_msgs.srv import GetPlanningScene
        from sensor_msgs.msg import Image, JointState
        from std_msgs.msg import Bool, String
        from std_srvs.srv import Trigger
        from geometry_msgs.msg import PointStamped
        from rcl_interfaces.srv import SetParametersAtomically
        from visualization_msgs.msg import MarkerArray

        self.rclpy, self.Trigger, self.ListControllers = rclpy, Trigger, ListControllers
        self.args, self.keyboard = args, keyboard
        self.workspace = Path(__file__).resolve().parents[1]
        self.prefix = '/brain_robot_ball_pick' if args.task == 'ball' else '/brain_robot_pick_place'
        self.model = 'red_ball' if args.task == 'ball' else 'medicine_cup'
        self.package = 'brain_robot_ball_pick' if args.task == 'ball' else 'brain_robot_pick_place'
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.output = self.workspace / 'log' / 'visual_sim' / (args.task + '-' + stamp)
        self.output.mkdir(parents=True)
        os.environ['ROS_LOG_DIR'] = str(self.output / 'ros_logs')
        self.events = (self.output / 'events.jsonl').open('w')
        self.children, self.handles, self.pending = [], [], {}
        self.generation, self.completed, self.runs = 0, 0, []
        self.start_rejections = []
        self.last_start_rejection = ''
        self.seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**32)
        self.rng, self.scene_index = random.Random(self.seed), 0
        self.zones = {'1': ('A', .38, .12), '2': ('B', .42, .12)}
        self.selected_zone = '1'
        self.latest_image = None
        self.sim_time_s = 0.0
        self.mode = 'LOADING'
        self.clear_state()
        # Keep the context alive through Ctrl+C so cleanup can request stop.
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        self.node = rclpy.create_node('visual_sim_console')
        # Create persistent clients before their servers appear, as in validation.
        self.clients = {
            'start': self.node.create_client(Trigger, '/visual_search_controller/start'),
            'stop': self.node.create_client(Trigger, '/visual_search_controller/stop'),
            'reset': self.node.create_client(Trigger, self.prefix + '/reset_scene'),
            'controllers': self.node.create_client(ListControllers, '/controller_manager/list_controllers'),
            'planning': self.node.create_client(GetPlanningScene, '/get_planning_scene'),
            'placement': self.node.create_client(SetParametersAtomically,
                                                '/grasp_lift_executor/set_parameters_atomically'),
        }
        transient = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.subscriptions = [
            self.node.create_subscription(Bool, self.prefix + '/scene_ready', self.on_ready, transient),
            self.node.create_subscription(String, '/brain_robot_visual_control/state', self.on_visual, transient),
            self.node.create_subscription(String, '/brain_robot_visual_control/reason',
                                          lambda msg: self.on_text('reason', msg), transient),
            self.node.create_subscription(String, '/brain_robot_grasp/state', self.on_grasp, transient),
            self.node.create_subscription(String, '/brain_robot_grasp/diagnostic', self.on_diagnostic, 10),
            self.node.create_subscription(JointState, '/joint_states', self.on_joints, qos_profile_sensor_data),
            self.node.create_subscription(ModelStates, '/gazebo/model_states', self.on_models, qos_profile_sensor_data),
            self.node.create_subscription(Image, '/wrist_camera/wrist_camera/image_raw',
                                          self.on_camera, qos_profile_sensor_data),
            self.node.create_subscription(Image, '/brain_robot_vision/debug_image',
                                          lambda _: self.mark_image('detection'), qos_profile_sensor_data),
            self.node.create_subscription(PointStamped, '/brain_robot_grasp/locked_camera_point',
                                          self.on_locked_point, transient),
        ]
        from control_msgs.msg import JointJog
        from rosgraph_msgs.msg import Clock
        self.subscriptions.append(self.node.create_subscription(Clock, '/clock',
            lambda msg: setattr(self, 'sim_time_s', msg.clock.sec + msg.clock.nanosec/1e9),
            qos_profile_sensor_data))
        self.subscriptions.append(self.node.create_subscription(JointJog, '/servo_node/delta_joint_cmds',
            self.on_jog, 10))
        self.zone_publisher = self.node.create_publisher(MarkerArray, '/brain_robot_sim/place_zones', transient)
        self.contact_latest = [0., 0.]
        if args.physics:
            for index in range(2):
                self.subscriptions.append(self.node.create_subscription(ContactsState,
                    f'/brain_robot_physics/link{index+7}_contacts',
                    lambda msg, index=index: self.on_contacts(msg, index), qos_profile_sensor_data))
        self.node.create_timer(1., self.publish_zones)
        self.say('日志', str(self.output))
        self.say('随机种子', str(self.seed) + '（已保存，可用于重现起点）')

    def clear_state(self):
        self.state = dict(visual='', grasp='', reason='', ready=False, owned=False)
        self.joints, self.pose = None, None
        self.joint_time = self.pose_time = self.ready_time = 0.
        self.camera_time = self.detection_time = 0.
        self.cycle_seen = False
        self.initial_pose = None
        self.active_run = None
        self.reset_time = self.started_time = 0.

    def say(self, label, message):
        print(f'[{label}] {message}', flush=True)
        self.record(label=label, message=message)

    def record(self, **entry):
        entry['time'] = time.monotonic()
        entry['sim_time_s'] = self.sim_time_s
        self.events.write(json.dumps(entry, ensure_ascii=False) + '\n')
        self.events.flush()

    def on_text(self, key, msg):
        if self.state[key] != msg.data:
            self.state[key] = msg.data
            self.record(topic=key, value=msg.data)
            if key == 'reason' and self.mode not in ('LOADING', 'CLOSING'):
                self.say('视觉', msg.data)

    def on_visual(self, msg):
        self.on_text('visual', msg)

    def on_grasp(self, msg):
        changed = self.state['grasp'] != msg.data
        self.on_text('grasp', msg)
        if self.mode in ('STARTING', 'RUNNING'):
            if msg.data not in ('COMPLETE', 'WAITING_FOR_GRASP_REQUEST') and not msg.data.startswith('FAULT'):
                self.cycle_seen = True
            if changed:
                self.say('抓取', msg.data)

    def on_diagnostic(self, msg):
        if msg.data == 'CONTROL_CLAIM_CONFIRMED':
            self.state['owned'] = True
        elif msg.data == 'CONTROL_RELEASE_CONFIRMED':
            self.state['owned'] = False
        if self.active_run is not None and msg.data.startswith('GRIPPER_WIDTH_ADAPTIVE'):
            self.active_run['adaptive_gripper_diagnostic'] = msg.data
        if self.active_run is not None and msg.data.startswith('PHYSICAL_'):
            self.record(physics_diagnostic=msg.data)
            self.active_run.setdefault('physics_diagnostics', []).append(msg.data)

    def on_contacts(self, msg, index):
        active = [c for c in msg.states if self.model + '::' in c.collision1_name
                  or self.model + '::' in c.collision2_name]
        now = time.monotonic()
        if active:
            self.contact_latest[index] = now
        if self.active_run and active:
            samples = self.active_run.setdefault('contact_samples', [])
            if not samples or now-self.active_run['started']-samples[-1]['elapsed_s'] >= .02:
                samples.append(dict(elapsed_s=now-self.active_run['started'], jaw=index+7,
                    states=len(active), both=all(now-t < .2 for t in self.contact_latest),
                    force_n=max(math.sqrt(c.total_wrench.force.x**2+c.total_wrench.force.y**2+
                                          c.total_wrench.force.z**2) for c in active)))

    def on_ready(self, msg):
        self.state['ready'] = msg.data
        self.ready_time = time.monotonic()

    def mark_image(self, kind):
        setattr(self, kind + '_time', time.monotonic())

    def on_camera(self, msg):
        self.latest_image = msg
        self.mark_image('camera')

    def on_jog(self, msg):
        if self.active_run and self.state['owned'] and any(abs(v) > 1e-9 for v in msg.velocities):
            self.active_run['nonzero_jogs_while_owned'] += 1

    def on_locked_point(self, msg):
        run = self.active_run
        stamp = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        if (run is None or stamp <= run['start_image_stamp_ns'] or msg.header.frame_id != 'world'
                or time.monotonic()-self.pose_time > .5):
            return
        point = [msg.point.x, msg.point.y, msg.point.z]
        if not all(math.isfinite(v) for v in point):
            return
        # The detector returns a visible surface point, not a fitted center.
        # XY error is useful for this grasp; Z is reported separately as bias.
        reference = list(run['initial_xyz'])
        delta = [a-b for a, b in zip(point, reference)]
        measurement = dict(image_stamp_ns=stamp, frame='world', camera_surface_xyz=point,
                           gazebo_center_xyz=reference, delta_xyz_m=delta,
                           xy_error_m=math.hypot(*delta[:2]), z_surface_center_difference_m=delta[2])
        measurement['point_kind'] = 'fitted_center' if self.args.physics else 'visible_surface'
        if self.args.physics:
            measurement['camera_center_xyz'] = measurement.pop('camera_surface_xyz')
            measurement['center_z_error_m'] = measurement.pop('z_surface_center_difference_m')
        run.setdefault('localization_samples', []).append(measurement)
        self.record(localization=measurement)
        if self.latest_image is not None:
            from PIL import Image as PillowImage
            image = self.latest_image
            if image.encoding in ('rgb8', 'bgr8'):
                name = f"scene-{run['scene_index']:03d}-lock-{len(run['localization_samples']):02d}.png"
                PillowImage.frombytes('RGB', (image.width, image.height), bytes(image.data), 'raw',
                    'RGB' if image.encoding == 'rgb8' else 'BGR', image.step).save(self.output / name)
                measurement['snapshot'] = name
                measurement['snapshot_stamp_ns'] = image.header.stamp.sec*10**9 + image.header.stamp.nanosec
        self.save_summary()

    def publish_zones(self):
        from visualization_msgs.msg import Marker, MarkerArray
        array = MarkerArray()
        for index, (key, (label, x, y)) in enumerate(self.zones.items()):
            marker = Marker()
            marker.header.frame_id, marker.ns, marker.id = 'world', 'placement_regions', index
            marker.type, marker.action = Marker.CYLINDER, Marker.ADD
            marker.pose.position.x, marker.pose.position.y, marker.pose.position.z = x, y, .002
            marker.pose.orientation.w = 1.
            marker.scale.x = marker.scale.y = .035
            marker.scale.z = .002
            marker.color.r, marker.color.g, marker.color.b = (1., .7, .1) if key == self.selected_zone else (.6, .6, .6)
            marker.color.a = .85
            array.markers.append(marker)
            text = Marker()
            text.header.frame_id, text.ns, text.id = 'world', 'placement_labels', index
            text.type, text.action = Marker.TEXT_VIEW_FACING, Marker.ADD
            text.pose.position.x, text.pose.position.y, text.pose.position.z = x, y, .08
            text.pose.orientation.w, text.scale.z, text.color.a = 1., .025, 1.
            text.color.r, text.color.g, text.color.b = ((1., .7, .1)
                if key == self.selected_zone else (.7, .7, .7))
            text.text = label
            array.markers.append(text)
        self.zone_publisher.publish(array)

    def prepare_scene_profile(self):
        import yaml
        self.scene_index += 1
        x, y = self.rng.uniform(.38, .42), self.rng.uniform(-.12, -.08)
        ball = self.args.task == 'ball'
        path = self.workspace / 'src' / self.package / 'config' / ('ball_scene.yaml' if ball else 'scene.yaml')
        profile = yaml.safe_load(path.read_text())
        stem = 'ball' if ball else 'cup'
        for node in (('ball_scene_manager', 'ball_follow') if ball else ('scene_manager', 'cup_follow')):
            profile[node]['ros__parameters'].update({stem+'_x': x, stem+'_y': y})
        self.physics_task_profile = None
        if self.args.physics:
            manager = 'ball_scene_manager' if ball else 'scene_manager'
            follower = 'ball_follow' if ball else 'cup_follow'
            profile[manager]['ros__parameters'].update({
                'flow_demo': False, 'physics_grasp': True,
                'object_friction': 1.2, 'contact_kp': 100000.0, 'contact_kd': 10.0})
            profile[follower]['ros__parameters']['physics_grasp'] = True
            if not ball:
                # A 50 mm diameter sample leaves room inside the 70 mm stroke.
                profile[manager]['ros__parameters']['cup_radius'] = .025
            task_path = self.workspace / 'src' / self.package / 'config' / (
                'ball_task_sim.yaml' if ball else 'visual_search_sim.yaml')
            task_profile = yaml.safe_load(task_path.read_text())
            task_profile['grasp_lift_executor']['ros__parameters'].update({
                'physics_grasp_enabled': True, 'adaptive_size_enabled': True,
                'gripper_clearance_m': 0.002 if ball else 0.004, 'gripper_max_joint_m': 0.035,
                'physics_object_width_m': .035 if ball else .050,
                'target_point_topic': '/brain_robot_vision/physics_center',
                'hold_after_lift_s': 3.3,
                'gripper_tip_offset_m': .1238, 'grasp_center_offset_m': .1238,
                'top_down_grasp_clearance_m': 0.0,
                'top_down_tilt_candidates': [1.0, .70, .35, 0.0] if ball else [.70, 1.0, .35, 0.0],
                'grasp_landing_tolerance_m': .003,
                'grasp_landing_orientation_tolerance_rad': .03,
                'grasp_landing_max_correction_m': .008,
                'grasp_contact_check_enabled': True,
                # A top-down surface insertion uses the RGB-D visible face and
                # the locked object size to place the jaw centre at the true
                # geometric centre. This avoids the old side-grasp tangent
                # error for the sphere and keeps the cylinder volume inside
                # the two jaws.
                'top_down_grasp_enabled': True,
                'top_down_surface_grasp_enabled': False,
                'diagonal_side_grasp_enabled': False,
                'physics_test_drop': self.args.physics_negative == 'drop',
                'physics_test_offset_y_m': .06 if self.args.physics_negative == 'miss' else 0.0})
            self.physics_task_profile = self.output / (
                'physics-' + ('ball' if ball else 'cylinder') + '-task.yaml')
            self.physics_task_profile.write_text(yaml.safe_dump(task_profile, sort_keys=False))
        self.expected_pose = [x, y, .0175 if ball else .05]
        destination = self.output / f'scene-{self.scene_index:03d}.yaml'
        destination.write_text(yaml.safe_dump(profile, sort_keys=False))
        self.record(scene_index=self.scene_index, seed=self.seed, requested_xyz=self.expected_pose,
                    profile=destination.name)
        return destination

    def load_scene(self):
        profile = self.prepare_scene_profile()
        self.state['ready'] = False
        self.pose = None
        self.launch_ros('scene', self.package, 'ball_scene.launch.py' if self.args.task == 'ball' else 'scene.launch.py',
                        'params_file:=' + str(profile))
        self.wait(lambda: self.state['ready'] and self.pose is not None and time.monotonic()-self.pose_time < 1
                  and math.dist(self.pose, self.expected_pose) < .001, 60, '随机物品场景')
        self.initial_pose = list(self.pose)

    def set_placement(self, key):
        from rclpy.parameter import Parameter
        from rcl_interfaces.srv import SetParametersAtomically
        label, x, y = self.zones[key]
        client = self.clients['placement']
        self.wait(client.service_is_ready, 10, '放置区选择服务')
        request = SetParametersAtomically.Request()
        request.parameters = [Parameter('place_x', value=x).to_parameter_msg(),
                              Parameter('place_y', value=y).to_parameter_msg()]
        future = client.call_async(request)
        self.wait(future.done, 10, '放置区确认')
        if not future.result().result.successful:
            raise RuntimeError('放置区被拒绝：' + future.result().result.reason)
        self.selected_zone = key
        self.publish_zones()
        self.record(selected_zone=label, destination_xy=[x, y])
        self.say('放置区', label + ' 区已选中。')

    def on_joints(self, msg):
        names = ['joint' + str(i) for i in range(1, 7)]
        if all(name in msg.name and msg.name.index(name) < len(msg.position) for name in names):
            values = [msg.position[msg.name.index(name)] for name in names]
            if all(math.isfinite(x) for x in values):
                self.joints, self.joint_time = values, time.monotonic()
                if self.active_run and self.mode in ('STOPPING', 'STOPPED'):
                    self.active_run.setdefault('stop_joint_samples', []).append(
                        dict(time=self.joint_time, positions=list(values)))

    def on_models(self, msg):
        if self.model in msg.name:
            pose = msg.pose[msg.name.index(self.model)].position
            self.pose = [pose.x, pose.y, pose.z]
            self.pose_time = time.monotonic()
            if self.active_run and self.mode in ('STARTING', 'RUNNING', 'STOPPING'):
                self.active_run['maximum_z'] = max(self.active_run['maximum_z'], pose.z)
                run = self.active_run
                samples = run['model_samples']
                elapsed = time.monotonic()-run['started']
                if not samples or elapsed-samples[-1]['elapsed_s'] >= .1:
                    samples.append(dict(elapsed_s=elapsed, sim_time_s=self.sim_time_s,
                        grasp_state=self.state['grasp'], xyz=list(self.pose)))
                if self.state['grasp'] in ('HOLDING', 'HOLDING_PHYSICAL_OBJECT'):
                    self.active_run['holding_min_z'] = min(
                        self.active_run['holding_min_z'] if self.active_run['holding_min_z'] is not None
                        else self.pose[2], self.pose[2])

    def launch(self, label, command, environment=None):
        suffix = f'-{self.scene_index:03d}' if label == 'scene' else ''
        log = (self.output / f'{self.generation:02d}-{label}{suffix}.log').open('w')
        child = subprocess.Popen(command, cwd=self.workspace, env=environment, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.children.append((label, child))
        child.visual_log_path = log.name
        self.handles.append(log)
        self.record(launched=label, pid=child.pid, command=command, log=log.name)
        (self.output / 'owned_process_groups.json').write_text(json.dumps(
            {name: process.pid for name, process in self.children}, indent=2) + '\n')

    def launch_ros(self, label, package, filename, *arguments):
        self.launch(label, ['ros2', 'launch', package, filename, *arguments])

    def health(self):
        for label, child in self.children:
            status = child.poll()
            if label.endswith('-window') and status == 0:
                self.say('退出', label + ' 窗口已关闭。')
                raise QuitRequested()
            if status is not None:
                raise RuntimeError(f'{label} 已退出；详情见 {child.visual_log_path}')

    def pump(self, loading=False):
        self.rclpy.spin_once(self.node, timeout_sec=.02)
        self.health()
        key = self.keyboard.read()
        if key in ('q', '\x04'):
            raise QuitRequested()
        if key:
            if loading:
                self.say('等待', '正在加载，请就绪后操作；Q 可退出。')
            else:
                self.handle_key(key)

    def wait(self, predicate, timeout, label):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump(loading=True)
            if predicate():
                return
        raise RuntimeError('等待超时：' + label)

    def bootstrap(self):
        self.mode = 'LOADING'
        self.generation += 1
        self.clear_state()
        self.say('1/5', '加载虚拟机械臂和控制器…')
        self.launch_ros('gazebo', 'brain_robot_pick_place', 'wrist_camera_gazebo.launch.py',
                        'gui:=false', 'physics_grasp:=' + str(self.args.physics).lower(),
                        'physics_jaw_kp:=' + ('600' if self.args.task == 'cylinder' else '300'),
                        'physics_jaw_kd:=' + ('1.0' if self.args.task == 'cylinder' else '0.2'),
                        'world:=' + str(self.workspace / 'validation/grasp_validation.world'))
        client = self.clients['controllers']
        self.wait(client.service_is_ready, 60, '控制器服务')
        discovered = time.monotonic()
        self.wait(lambda: time.monotonic() - discovered >= 2., 3, '控制器服务发现')
        future = None

        def active():
            nonlocal future
            if future is None:
                future = client.call_async(self.ListControllers.Request())
            if not future.done():
                return False
            response = future.result()
            future = None
            present = {c.name for c in response.controller if c.state == 'active'}
            return {'joint_state_broadcaster', 'arm_controller', 'gripper_controller', 'gripper8_controller'} <= present

        self.wait(active, 60, '四个控制器激活')
        if self.args.physics:
            self.wait(lambda: self.joints is not None and time.monotonic()-self.joint_time < .5,
                      10, '初始虚拟关节反馈')
            try:
                self.wait(lambda: max(abs(v) for v in self.joints) < .001 and
                          time.monotonic()-self.joint_time < .5, 10, '虚拟初始零位')
            except RuntimeError:
                self.record(initialization_joint_feedback=self.joints)
                raise RuntimeError('虚拟零位初始化失败，实测关节=' + repr(self.joints))
        if not self.args.headless:
            self.launch('gazebo-window', ['gzclient'])
        self.say('2/5', '加载 MoveIt' + (' 和 RViz 相机画面…' if not self.args.headless else '…'))
        self.launch_ros('moveit', 'piper_with_gripper_moveit', 'piper_moveit.launch.py', 'start_rviz:=false')
        self.wait(self.clients['planning'].service_is_ready, 60, 'MoveIt 场景服务')
        if not self.args.headless:
            # Own the viewer directly so a crashed/closed window is detected.
            # Mesa avoids this desktop's GLX drawable failure with Image panels.
            environment = dict(os.environ, LIBGL_ALWAYS_SOFTWARE='1', __GLX_VENDOR_LIBRARY_NAME='mesa')
            self.launch('rviz-window', ['rviz2', '-d', str(self.workspace / 'config/visual_grasp.rviz'),
                        '--ros-args', '-r', '__node:=visual_grasp_viewer', '-p', 'use_sim_time:=true'], environment)
            self.wait(lambda: 'visual_grasp_viewer' in self.node.get_node_names(), 30, 'RViz 窗口节点')
        self.say('3/5', '创建桌面和' + ('小球…' if self.args.task == 'ball' else '圆柱体…'))
        self.load_scene()
        self.say('4/5', '加载 RGB-D 相机检测…')
        self.launch_ros('detector', self.package, 'ball_detector.launch.py' if self.args.task == 'ball' else 'cup_detector.launch.py')
        if self.args.physics:
            self.launch('physics-target', ['ros2', 'run', 'brain_robot_pick_place', 'physics_target_node.py',
                '--ros-args', '-p', 'use_sim_time:=true', '-p',
                'shape:=' + ('sphere' if self.args.task == 'ball' else 'cylinder'),
                '-p', 'radius:=' + ('.0175' if self.args.task == 'ball' else '.025')])
        self.wait(lambda: time.monotonic()-self.camera_time < 2 and time.monotonic()-self.detection_time < 2,
                  45, '相机原图和检测图')
        self.say('5/5', '加载视觉搜索与抓取任务…')
        task_args = ['backend:=simulation']
        if self.physics_task_profile is not None:
            task_args.append('params_file:=' + str(self.physics_task_profile))
        self.launch_ros('task', self.package,
                        'ball_visual_search.launch.py' if self.args.task == 'ball' else 'visual_search.launch.py',
                        *task_args)
        self.wait(lambda: self.state['visual'] == 'IDLE' and all(self.clients[k].service_is_ready() for k in ('start','stop','reset'))
                  and self.joints is not None and time.monotonic()-self.joint_time < .5, 60, '视觉任务')
        self.mode = 'READY'
        self.set_placement(self.selected_zone)
        self.say('就绪', '1/2 选择 A/B 放置区 | S 相机抓取 | R 随机复位 | X 停止 | Q 退出')

    def request(self, kind):
        client = self.clients[kind]
        if not client.service_is_ready():
            raise RuntimeError(kind + ' 服务不可用')
        self.pending[kind] = (client.call_async(self.Trigger.Request()), time.monotonic() + 15.)

    def handle_key(self, key):
        if key in self.zones:
            if self.mode != 'READY':
                self.say('提示', '请在就绪时选择放置区；运动中不能更改。')
                return
            self.set_placement(key)
        elif key == 's':
            if self.mode != 'READY':
                self.say('提示', '当前不能开始。完成后先按 R；运动中等待结束或按 X。')
                return
            if time.monotonic()-self.joint_time > .5 or time.monotonic()-self.camera_time > 2:
                self.say('提示', '反馈尚未更新，请确认 Gazebo 未暂停。')
                return
            self.mode, self.cycle_seen = 'STARTING', False
            self.last_start_rejection = ''
            self.started_time = time.monotonic()
            label, x, y = self.zones[self.selected_zone]
            image = self.latest_image
            self.active_run = dict(initial_xyz=list(self.pose), maximum_z=self.pose[2],
                holding_min_z=None, started=self.started_time,
                seed=self.seed, scene_index=self.scene_index, zone=label, destination_xyz=[x, y, self.pose[2]],
                start_image_stamp_ns=image.header.stamp.sec*10**9+image.header.stamp.nanosec,
                model_samples=[], localization_samples=[], nonzero_jogs_while_owned=0)
            self.say('操作', '开始相机搜索、抓取与放置。')
            self.request('start')
        elif key == 'r':
            if self.mode in ('FAULT', 'STOPPED'):
                self.say('复位', '中途停止/故障后重新加载本次仿真，清理附着和跟随状态。')
                self.teardown()
                self.pending.clear()
                self.bootstrap()
            elif self.mode in ('FINISHED', 'READY'):
                if (self.state['visual'] != 'IDLE' or self.state['owned'] or self.joints is None
                        or time.monotonic()-self.joint_time > .5 or max(abs(v) for v in self.joints) >= .02):
                    self.say('提示', '等待新鲜关节反馈、回零和控制权释放后再复位。')
                    return
                self.mode = 'RESETTING'
                self.say('复位', '随机摆放新目标，同步 Gazebo、MoveIt 和跟随节点…')
                # Replace only our scene/follow pair with one shared profile.
                # Keeping the old follower would retain its old initial pose.
                self.stop_children({'scene'})
                self.load_scene()
                self.mode = 'READY'
                self.say('复位完成', '新物品已就绪；1/2 选择放置区，S 再次相机抓取。')
            else:
                self.say('提示', '运动或加载中不能复位。请先等待完成，或按 X 停止。')
        elif key == 'x':
            if self.mode in ('STARTING', 'RUNNING'):
                self.mode = 'STOPPING'
                self.say('操作', '请求停止，停止后 R 重载复位，Q 退出。')
                self.request('stop')
            else:
                self.say('提示', '当前没有正在运行的抓取任务。')

    def fault(self, reason):
        moving = self.mode in ('STARTING', 'RUNNING', 'STOPPING')
        self.mode = 'FAULT'
        self.say('故障', reason + '；R 重载复位，Q 退出。')
        if self.active_run:
            self.active_run['failure_reason'] = reason
        if moving and 'stop' not in self.pending and self.clients['stop'].service_is_ready():
            self.request('stop')

    def check_state(self):
        now = time.monotonic()
        for kind, (future, deadline) in list(self.pending.items()):
            if not future.done():
                if now > deadline:
                    future.cancel()
                    del self.pending[kind]
                    self.fault(kind + ' 请求超时')
                continue
            del self.pending[kind]
            response = future.result()
            if response is None or not response.success:
                message = response.message if response else '未收到响应'
                if kind == 'start' and self.mode == 'STARTING':
                    self.mode, self.active_run = 'READY', None
                    self.last_start_rejection = message
                    self.start_rejections.append(dict(scene_index=self.scene_index, reason=message,
                                                      time=time.monotonic()))
                    self.say('拒绝', message + '；确认就绪后再按 S。')
                    self.save_summary()
                else:
                    self.fault(message)
            elif kind == 'start' and self.mode == 'STARTING':
                self.mode = 'RUNNING'
        if self.mode in ('STARTING', 'RUNNING'):
            if (self.args.physics_negative == 'stop' and self.state['grasp'] == 'LIFTING_PHYSICAL_OBJECT'
                    and self.active_run['maximum_z'] >= self.active_run['initial_xyz'][2] + .025
                    and not self.active_run.get('stop_injected')):
                self.active_run['stop_injected'] = True
                self.handle_key('x')
                return
            if self.state['visual'] == 'FAULT' or self.state['grasp'].startswith('FAULT_'):
                self.fault(self.state['grasp'] + ' / ' + self.state['reason'])
            elif now - self.started_time > 200:
                self.fault('本轮等待超过 200 秒')
            elif (self.cycle_seen and self.state['grasp'] == 'COMPLETE' and self.state['visual'] == 'IDLE'
                  and not self.state['owned'] and self.joints is not None and now-self.joint_time < .5
                  and max(abs(v) for v in self.joints) < .02 and now-self.pose_time < 1):
                self.mode = 'FINISHED'
                self.completed += 1
                run = self.active_run
                run.update(completed=True, elapsed_s=now-run['started'], final_xyz=list(self.pose),
                           peak_lift_m=run['maximum_z']-run['initial_xyz'][2],
                           home_error_rad=max(abs(v) for v in self.joints))
                run['placement_error_m'] = math.dist(run['final_xyz'], run['destination_xyz'])
                holding = [s for s in run['model_samples'] if s.get('grasp_state') == 'HOLDING_PHYSICAL_OBJECT']
                run['hold_span_sim_s'] = max((s['sim_time_s'] for s in holding), default=0) - min(
                    (s['sim_time_s'] for s in holding), default=0)
                run['passed'] = (run['peak_lift_m'] >= .05 and
                    (not self.args.physics or (run['holding_min_z'] is not None and
                        run['holding_min_z'] >= run['initial_xyz'][2] + .05 and
                        run['hold_span_sim_s'] >= 3.0 and
                        'PHYSICAL_RELEASE_SETTLED_NO_JAW_CONTACT' in run.get('physics_diagnostics', []))) and
                    run['placement_error_m'] < .03
                    and run['home_error_rad'] < .02 and run['nonzero_jogs_while_owned'] == 0
                    and bool(run['localization_samples']))
                self.runs.append(run)
                self.active_run = None
                self.say('完成', f'第 {self.completed} 轮取放完成；R 复位后可再按 S，Q 退出。')
                self.save_summary()
                if not run['passed']:
                    self.fault('流程结束，但数据验收条件未通过')
        elif self.mode == 'STOPPING':
            if self.state['visual'] in ('STOPPED', 'FAULT') and not self.state['owned'] and 'stop' not in self.pending:
                self.mode = 'STOPPED'
                self.say('已停止', 'R 重新加载并复位，Q 退出。')

    def save_summary(self):
        measurements = [sample for run in self.runs for sample in run.get('localization_samples', [])]
        errors = sorted(sample['xy_error_m'] for sample in measurements)
        statistics = dict(count=len(errors))
        if errors:
            statistics.update(mean_xy_error_m=sum(errors)/len(errors), max_xy_error_m=max(errors),
                              p95_xy_error_m=errors[max(0, math.ceil(.95*len(errors))-1)])
        data = json.dumps(dict(
            task=self.args.task, headless=self.args.headless, completed=self.completed,
            seed=self.seed, scene_index=self.scene_index, selected_zone=self.zones[self.selected_zone][0],
            random_bounds_xy=[[.38, .42], [-.12, -.08]], localization_statistics=statistics,
            mode=self.mode, runs=self.runs, active_run=self.active_run,
            start_rejections=self.start_rejections,
            validation_kind=('camera_randomized_physics_grasp' if self.args.physics
                             else 'camera_randomized_follow_based_flow'),
            physics_grasp=self.args.physics, negative_case=self.args.physics_negative),
            ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        temporary = self.output / 'session.json.tmp'
        with temporary.open('w') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.output / 'session.json')

    def stop_children(self, labels=None):
        selected = [(label, child) for label, child in self.children if labels is None or label in labels]
        groups = [child.pid for _, child in selected]

        def exists(pgid):
            try:
                os.killpg(pgid, 0)
                return True
            except ProcessLookupError:
                return False

        for sig, timeout in [(signal.SIGINT, 8), (signal.SIGTERM, 3), (signal.SIGKILL, 1)]:
            for pgid in reversed(groups):
                try:
                    os.killpg(pgid, sig)
                except ProcessLookupError:
                    pass
            deadline = time.monotonic()+timeout
            while time.monotonic() < deadline:
                for _, child in selected:
                    child.poll()
                if not any(exists(p) for p in groups):
                    break
                self.rclpy.spin_once(self.node, timeout_sec=.05)
        for _, child in selected:
            child.wait(timeout=2)
        self.children = [(label, child) for label, child in self.children if (label, child) not in selected]
        self.record(cleaned_process_groups=groups)

    def teardown(self):
        if self.active_run is not None:
            run = self.active_run
            run.update(completed=False, interrupted_in=self.mode, elapsed_s=time.monotonic()-run['started'],
                       final_xyz=self.pose)
            self.runs.append(run)
            self.active_run = None
        self.mode = 'CLOSING'
        self.say('关闭', '正在停止本程序启动的仿真进程…')
        if self.children and self.clients['stop'].service_is_ready():
            future = self.clients['stop'].call_async(self.Trigger.Request())
            deadline = time.monotonic() + 2
            while not future.done() and time.monotonic() < deadline:
                self.rclpy.spin_once(self.node, timeout_sec=.05)
        self.stop_children()
        for handle in self.handles:
            handle.close()
        self.handles.clear()
        for future, _ in self.pending.values():
            future.cancel()
        self.pending.clear()

    def run(self):
        if self.args.batch_trials:
            rng = random.Random(self.seed)
            plan = [dict(trial=i+1, start_xy=[rng.uniform(.38, .42), rng.uniform(-.12, -.08)],
                         zone=self.zones[str(i % 2 + 1)][0]) for i in range(self.args.batch_trials)]
            (self.output / 'trial_plan.json').write_text(json.dumps(dict(seed=self.seed, trials=plan,
                failure_policy='stop_at_first_failure'), indent=2)+'\n')
        self.bootstrap()
        if self.args.batch_trials:
            for index in range(self.args.batch_trials):
                if index:
                    self.handle_key('r')
                if self.mode != 'READY':
                    raise RuntimeError('批量试验复位未就绪')
                self.handle_key(str(index % 2 + 1))
                start_deadline = time.monotonic()+10.
                while True:
                    self.handle_key('s')
                    while self.mode in ('STARTING', 'RUNNING', 'STOPPING'):
                        self.pump()
                        self.check_state()
                    # Retry only an explicit pre-motion joint-discovery refusal,
                    # on the same scene/zone; never retry a failed moving trial.
                    if (self.mode == 'READY' and self.last_start_rejection.startswith('No fresh joint state')
                            and time.monotonic() < start_deadline):
                        wait_until = time.monotonic()+.5
                        self.wait(lambda: time.monotonic() >= wait_until, 1., '初始反馈发现')
                        continue
                    break
                if self.mode != 'FINISHED' or not self.runs[-1]['passed']:
                    if self.args.physics_negative == 'stop':
                        end = time.monotonic()+2.
                        self.wait(lambda: time.monotonic() >= end, 3., '停止后反馈观察')
                    raise RuntimeError('批量试验失败；保留数据并停止后续试验')
            return
        while self.rclpy.ok():
            self.pump()
            self.check_state()

    def close(self):
        self.teardown()
        self.save_summary()
        self.node.destroy_node()
        if self.rclpy.ok():
            self.rclpy.shutdown()
        self.events.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=['ball', 'cylinder'])
    parser.add_argument('--headless', action='store_true', help='Developer check: omit Gazebo/RViz windows')
    parser.add_argument('--seed', type=int, help='Repeatable random placement seed; saved with the session')
    parser.add_argument('--batch-trials', type=int, default=0,
                        help='Developer acceptance only: explicitly run 1..20 headless visual trials')
    parser.add_argument('--physics', action='store_true',
                        help='Enable gravity/contact/friction grasping and size-adaptive jaw opening')
    parser.add_argument('--physics-negative', choices=['miss', 'drop', 'stop'], default=None,
                        help='Explicit simulation fault injection for one batch trial')
    args = parser.parse_args()
    if args.physics_negative and (not args.physics or args.batch_trials != 1):
        parser.error('物理故障注入仅用于 --physics --batch-trials 1。')
    if args.batch_trials and (not args.headless or not 1 <= args.batch_trials <= 20 or args.seed is None):
        parser.error('批量验收需 --headless、--seed 和 --batch-trials 1..20。')
    if args.batch_trials < 0:
        parser.error('--batch-trials 不能为负数。')
    if not sys.stdin.isatty() and not args.batch_trials:
        parser.error('请在交互终端运行，按键操作不需要回车。')
    if not args.headless and not os.environ.get('DISPLAY'):
        parser.error('没有 DISPLAY，请在 Ubuntu 图形桌面的终端运行。')
    if os.environ.get('ROS_DOMAIN_ID') != '83' or os.environ.get('GAZEBO_MASTER_URI') != 'http://127.0.0.1:11483':
        parser.error('请使用 run_ball_visual_sim.sh 或 run_cylinder_visual_sim.sh 启动。')
    if not args.headless and not shutil.which('gzclient'):
        parser.error('找不到 Gazebo 窗口程序 gzclient。')
    workspace = Path(__file__).resolve().parents[1]
    lock_path = workspace / 'log' / 'visual_sim.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('[错误] 小球或圆柱体程序已在运行，请先按 Q 退出该实例。', flush=True)
            return 1
        # Read-only conflict check; never stop a foreign Gazebo instance.
        try:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 11483))
        except OSError:
            print('[错误] 本程序的 Gazebo 端口 11483 已被占用，请先退出对应仿真。', flush=True)
            return 1
        session = None
        code = 0
        with (Keyboard() if sys.stdin.isatty() else nullcontext(BatchKeyboard())) as keyboard:
            try:
                session = VisualSession(args, keyboard)
                # Discover existing nodes before starting any servers or motion.
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    session.rclpy.spin_once(session.node, timeout_sec=.05)
                reserved = {'move_group', 'controller_manager', 'servo_node', 'visual_search_controller', 'grasp_lift_executor'}
                if reserved.intersection(session.node.get_node_names()):
                    raise RuntimeError('ROS 域 83 已有控制节点，请先退出对应仿真。')
                print('=== 相机取放仿真：' + ('小球' if args.task == 'ball' else '圆柱体') + ' ===', flush=True)
                print('加载完成后按 S 开始，R 复位，X 停止，Q 退出；仅控制虚拟机械臂。', flush=True)
                session.run()
            except (QuitRequested, KeyboardInterrupt):
                print('\n[退出] 正在退出…', flush=True)
            except Exception as exc:
                code = 1
                print('[错误] ' + str(exc), flush=True)
            finally:
                # Ignore repeated interrupt keys while recovering owned children.
                signal.signal(signal.SIGINT, signal.SIG_IGN)
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                if session is not None:
                    session.close()
        print('[退出完成] 本程序启动的仿真已关闭。', flush=True)
        return code


if __name__ == '__main__':
    def terminate(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())
