#!/usr/bin/env python3
"""Read-only PiPER visual-grasp runtime monitor."""

import sys
import time

import rclpy
from control_msgs.msg import JointJog
from geometry_msgs.msg import PointStamped, PoseStamped, Vector3Stamped
from moveit_msgs.msg import PlanningScene
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import JointState, PointCloud2
from std_msgs.msg import Bool, Int8, String
from tf2_ros import Buffer, TransformException, TransformListener


class RuntimeMonitor(Node):
    def __init__(self) -> None:
        super().__init__('brain_robot_runtime_monitor')
        state_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        reliable_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        sensor_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)

        self.values: dict[str, object] = {}
        self.received: dict[str, float] = {}
        self.camera_optical_frame = self.declare_parameter(
            'camera_optical_frame', 'camera_color_optical_frame').value
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.create_subscription(String, '/brain_robot_visual_control/state',
                                 lambda message: self.store('visual_state', message.data), state_qos)
        self.create_subscription(String, '/brain_robot_visual_control/reason',
                                 lambda message: self.store('visual_reason', message.data), state_qos)
        self.create_subscription(String, '/brain_robot_visual_control/search_direction',
                                 lambda message: self.store('search_direction', message.data), state_qos)
        self.create_subscription(String, '/brain_robot_visual_control/command_diagnostic',
                                 lambda message: self.store('command_diagnostic', message.data), state_qos)
        self.create_subscription(String, '/brain_robot_grasp/state',
                                 lambda message: self.store('grasp_state', message.data), state_qos)
        self.create_subscription(PoseStamped, '/brain_robot_grasp/target_pose',
                                 lambda message: self.store('grasp_target_pose', message), state_qos)
        self.create_subscription(PoseStamped, '/brain_robot_grasp/current_pose',
                                 lambda message: self.store('grasp_current_pose', message), state_qos)
        self.create_subscription(String, '/brain_robot_grasp/diagnostic',
                                 lambda message: self.store('grasp_diagnostic', message.data), state_qos)
        self.create_subscription(Bool, '/brain_robot_vision/target_valid',
                                 lambda message: self.store('target_valid', message.data), reliable_qos)
        self.create_subscription(Bool, '/brain_robot_vision/depth_valid',
                                 lambda message: self.store('depth_valid', message.data), reliable_qos)
        self.create_subscription(String, '/brain_robot_vision/depth_diagnostic',
                                 lambda message: self.store('depth_diagnostic', message.data), state_qos)
        self.create_subscription(Vector3Stamped, '/brain_robot_vision/pixel_error',
                                 lambda message: self.store('pixel_error', message.vector), reliable_qos)
        self.create_subscription(PointStamped, '/brain_robot_vision/target_point_camera',
                                 lambda message: self.store('target_point', message), reliable_qos)
        self.create_subscription(PointCloud2, '/camera/depth/points',
                                 lambda message: self.store('raw_points', message), sensor_qos)
        self.create_subscription(PointCloud2, '/brain_robot_vision/filtered_points',
                                 lambda message: self.store('filtered_points', message), sensor_qos)
        self.create_subscription(PlanningScene, '/monitored_planning_scene',
                                 self.store_planning_scene, reliable_qos)
        self.create_subscription(String, '/brain_robot_active_scan/state',
                                 lambda message: self.store('active_scan_state', message.data), state_qos)
        self.create_subscription(String, '/brain_robot_active_scan/diagnostic',
                                 lambda message: self.store('active_scan_diagnostic', message.data), state_qos)
        self.create_subscription(JointState, '/joint_states',
                                 lambda message: self.store('joint_states', message), sensor_qos)
        self.create_subscription(JointState, '/joint_states_feedback',
                                 lambda message: self.store('gripper_feedback', message), sensor_qos)
        self.create_subscription(Int8, '/servo_node/status',
                                 lambda message: self.store('servo_status', message.data), reliable_qos)
        self.create_subscription(JointJog, '/servo_node/delta_joint_cmds',
                                 lambda message: self.store('joint_jog', message), reliable_qos)
        self.create_timer(0.5, self.render)

    def store(self, key: str, value: object) -> None:
        self.values[key] = value
        self.received[key] = time.monotonic()

    def store_planning_scene(self, message: PlanningScene) -> None:
        octomap = message.world.octomap.octomap
        if octomap.id:
            summary = (
                f'更新 is_diff={message.is_diff} octomap={octomap.id} '
                f'resolution={octomap.resolution:.3f} m data={len(octomap.data)} B')
        elif message.is_diff:
            summary = '收到场景差分（本消息不含 OctoMap 数据）'
        else:
            summary = '收到完整场景（本消息不含 OctoMap 数据）'
        self.store('planning_scene', summary)

    def age(self, key: str) -> str:
        if key not in self.received:
            return '--'
        return f'{time.monotonic() - self.received[key]:.2f}s'

    def value(self, key: str) -> str:
        value = self.values.get(key)
        return '--' if value is None else str(value)

    def camera_tf_status(self) -> str:
        try:
            transform = self.tf_buffer.lookup_transform(
                'base_link', self.camera_optical_frame, Time())
        except TransformException as exception:
            return f'不可用：{exception}'
        translation = transform.transform.translation
        return (
            f'可用 base_link <- {self.camera_optical_frame} '
            f't=({translation.x:.3f}, {translation.y:.3f}, {translation.z:.3f}) m')

    @staticmethod
    def stage_hint(state: str) -> str:
        if state.startswith('MICRO_APPROACH_STEP_'):
            return '闭环接近：本次最多前进 8 mm，完成后将重新检查视觉、深度和关节反馈。'
        hints = {
            'SEARCH': '等待连续有效目标帧。',
            'LOCAL_SEARCH': '目标短暂丢失，正在局部重搜。',
            'ALIGN': '视觉 J1/J5 微调，等待归一化误差满足门槛。',
            'LEVEL_ALIGN': 'J1 保持，J5 只翻向负角度；J2/J3 独自维持画面，J3 快速减小。',
            'LEVEL_RECOVERY': '目标丢失：J1保持，J2继续上抬，J3快速向零位，J5加速翻负。',
            'FINAL_ALIGN': 'J5 已为大负角度；J1/J2/J3/J5 在负角度范围内最终调控。',
            'GRASP_READY': '负角度整平完成；Servo 已停止，抓取将保持当前姿态做点位直线接近。',
            'PREPARE': '正在前往观察位姿。',
            'STOPPED': '控制已停止。',
            'FAULT': '控制器故障；查看视觉原因与抓取状态。',
        }
        return hints.get(state, '等待控制器开始或等待首帧数据。')

    def render(self) -> None:
        if sys.stdout.isatty():
            print('\033[H\033[2J', end='')
        state = self.value('visual_state')
        print(f'PiPER 只读运行监控  {time.strftime("%F %T")}')
        print('--------------------------------------------------')
        print(f'视觉状态: {state}  ({self.age("visual_state")})')
        print(f'视觉原因: {self.value("visual_reason")}  ({self.age("visual_reason")})')
        print(f'搜索方向: {self.value("search_direction")}  ({self.age("search_direction")})')
        print(f'抓取状态: {self.value("grasp_state")}  ({self.age("grasp_state")})')
        print(f'规划诊断: {self.value("grasp_diagnostic")}  ({self.age("grasp_diagnostic")})')
        print(f'Servo 状态: {self.value("servo_status")}  ({self.age("servo_status")})')
        print(f'命令来源: {self.value("command_diagnostic")}  '
              f'({self.age("command_diagnostic")})')
        print()
        print(f'视觉目标: target_valid={self.value("target_valid")}  '
              f'depth_valid={self.value("depth_valid")}')
        print(f'深度抓取门: {self.value("depth_diagnostic")}  '
              f'({self.age("depth_diagnostic")})')
        print('环境地图输入:')
        print(f'  原始点云: /camera/depth/points  ({self.age("raw_points")})')
        print(f'  自过滤点云: /brain_robot_vision/filtered_points  '
              f'({self.age("filtered_points")})')
        print(f'  相机 TF: {self.camera_tf_status()}')
        print(f'  MoveIt 场景: {self.value("planning_scene")}  '
              f'({self.age("planning_scene")})')
        print(f'  扫描前提: {self.value("active_scan_state")}  '
              f'({self.age("active_scan_state")})')
        print(f'  扫描诊断: {self.value("active_scan_diagnostic")}  '
              f'({self.age("active_scan_diagnostic")})')
        error = self.values.get('pixel_error')
        if error is None:
            print('像素误差: --')
        else:
            print(f'像素误差: dx={error.x:.1f}  dy={error.y:.1f}  '
                  f'normalized={error.z:.3f}  ({self.age("pixel_error")})')
        target = self.values.get('target_point')
        if target is None:
            print('相机三维点: --')
        else:
            point = target.point
            print(f'相机三维点: frame={target.header.frame_id}  '
                  f'x={point.x:.3f}  y={point.y:.3f}  z={point.z:.3f} m  '
                  f'({self.age("target_point")})')
        self.render_pose('当前规划目标', 'grasp_target_pose')
        self.render_pose('规划失败时末端', 'grasp_current_pose')
        print()
        joints = self.values.get('joint_states')
        if joints is None:
            print('当前关节: --')
        else:
            mapping = dict(zip(joints.name, joints.position))
            labels = []
            for index in range(1, 9):
                name = f'joint{index}'
                if name in mapping:
                    labels.append(f'J{index}={mapping[name]:+.3f} rad')
            print('当前关节: ' + ('  '.join(labels) if labels else '--'))
            print(f'关节数据年龄: {self.age("joint_states")}')
        gripper_feedback = self.values.get('gripper_feedback')
        if gripper_feedback is not None:
            mapping = dict(zip(gripper_feedback.name, gripper_feedback.position))
            if 'gripper' in mapping:
                print(f'夹爪原始反馈: {mapping["gripper"]:+.5f} rad  '
                      f'({self.age("gripper_feedback")})')
        command = self.values.get('joint_jog')
        if command is not None and command.joint_names:
            values = '  '.join(
                f'{name}={velocity:+.3f} rad/s'
                for name, velocity in zip(command.joint_names, command.velocities))
            print(f'最近 Servo 命令: {values}  ({self.age("joint_jog")})')
        print()
        print('阶段说明: ' + self.stage_hint(state))
        print('门槛: 1 个有效目标帧 -> ALIGN；连续 5 帧 normalized <= 0.20 -> LEVEL_ALIGN；')
        print('      LEVEL_ALIGN 丢目标 -> LEVEL_RECOVERY：J1保持、J2上抬、J3向零、J5加速翻负；')
        print('      J5 到达负角度 -> FINAL_ALIGN；连续 5 帧 normalized <= 0.20 -> GRASP_READY。')
        print('深度仅用于像素反投影成三维抓取点，不是阶段切换门槛。')

    def render_pose(self, label: str, key: str) -> None:
        pose_stamped = self.values.get(key)
        if pose_stamped is None:
            print(f'{label}: --')
            return
        pose = pose_stamped.pose
        print(
            f'{label}: frame={pose_stamped.header.frame_id} '
            f'p=({pose.position.x:.3f}, {pose.position.y:.3f}, {pose.position.z:.3f}) '
            f'q=({pose.orientation.x:.3f}, {pose.orientation.y:.3f}, '
            f'{pose.orientation.z:.3f}, {pose.orientation.w:.3f}) '
            f'({self.age(key)})')


def main() -> None:
    rclpy.init()
    monitor = RuntimeMonitor()
    try:
        rclpy.spin(monitor)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
