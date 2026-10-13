#!/usr/bin/env python3
"""Spawn the red-ball Gazebo scene and mirror its collision geometry into MoveIt."""

from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from gazebo_msgs.srv import DeleteEntity, SpawnEntity
from geometry_msgs.msg import Pose
from moveit_msgs.msg import CollisionObject, PlanningScene
from moveit_msgs.srv import ApplyPlanningScene
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from shape_msgs.msg import SolidPrimitive
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


class BallSceneManager(Node):
    """Own just the simulation scene; no physical-arm command is issued here."""

    def __init__(self):
        super().__init__('ball_scene_manager')
        for name, value in (
                ('simulation_only', True), ('world_frame', 'world'),
                ('table_x', 0.35), ('table_y', 0.0),
                ('table_length', 0.70), ('table_width', 0.50),
                ('table_thickness', 0.05), ('table_center_z', -0.025),
                ('planning_table_min_x', 0.10), ('ball_x', 0.40),
                ('ball_y', -0.12), ('ball_radius', 0.0175), ('ball_mass', 0.015)):
            self.declare_parameter(name, value)
        if not self.get_parameter('simulation_only').value:
            raise RuntimeError('simulation_only=false is forbidden; no real-arm command was sent')

        self.declare_parameter('flow_demo', True)
        self.declare_parameter('physics_grasp', False)
        self.declare_parameter('object_friction', 1.2)
        self.declare_parameter('contact_kp', 100000.0)
        self.declare_parameter('contact_kd', 10.0)
        self.world_frame = str(self._value('world_frame'))
        self.ball_z = float(self._value('ball_radius'))
        self._validate()
        self.delete_client = self.create_client(DeleteEntity, '/delete_entity')
        self.spawn_client = self.create_client(SpawnEntity, '/spawn_entity')
        self.apply_scene_client = self.create_client(ApplyPlanningScene, '/apply_planning_scene')
        ready_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                               durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.ready_publisher = self.create_publisher(
            Bool, '/brain_robot_ball_pick/scene_ready', ready_qos)
        self.create_service(Trigger, '/brain_robot_ball_pick/reset_scene', self._reset)
        self.busy = False
        self.requested = True
        self._publish_ready(False)
        self.create_timer(1.0, self._try_start)

    def _value(self, name):
        return self.get_parameter(name).value

    def _validate(self):
        positives = ('table_length', 'table_width', 'table_thickness', 'ball_radius', 'ball_mass')
        if any(float(self._value(name)) <= 0.0 for name in positives):
            raise ValueError('table and ball dimensions must be positive')
        min_x = float(self._value('table_x')) - float(self._value('table_length')) / 2.0
        max_x = float(self._value('table_x')) + float(self._value('table_length')) / 2.0
        min_y = float(self._value('table_y')) - float(self._value('table_width')) / 2.0
        max_y = float(self._value('table_y')) + float(self._value('table_width')) / 2.0
        if not (min_x <= float(self._value('planning_table_min_x')) < max_x and
                min_x <= float(self._value('ball_x')) <= max_x and
                min_y <= float(self._value('ball_y')) <= max_y):
            raise ValueError('ball and planning-table bounds must lie on the tabletop')

    def _publish_ready(self, value):
        message = Bool()
        message.data = value
        self.ready_publisher.publish(message)

    def _reset(self, _request, response):
        self.requested = True
        self._publish_ready(False)
        response.success = True
        response.message = 'Red-ball scene reset queued.'
        return response

    def _try_start(self):
        if self.busy or not self.requested:
            return
        if not all(client.service_is_ready() for client in
                   (self.delete_client, self.spawn_client, self.apply_scene_client)):
            return
        self.busy = True
        self.requested = False
        self._publish_ready(False)
        self._delete_next(['ground_plane', 'care_floor', 'care_table', 'medicine_cup', 'red_ball'])

    def _delete_next(self, names):
        if not names:
            self._spawn('care_floor', self._floor_sdf(), 0.0, 0.0, 0.0, self._after_floor)
            return
        request = DeleteEntity.Request()
        request.name = names[0]
        future = self.delete_client.call_async(request)
        future.add_done_callback(lambda _future: self._delete_next(names[1:]))

    @staticmethod
    def _pose(x, y, z):
        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z = x, y, z
        pose.orientation.w = 1.0
        return pose

    def _spawn(self, name, xml, x, y, z, continuation):
        request = SpawnEntity.Request()
        request.name, request.xml = name, xml
        request.robot_namespace = '/brain_robot_ball_pick'
        request.reference_frame = self.world_frame
        request.initial_pose = self._pose(x, y, z)
        future = self.spawn_client.call_async(request)
        future.add_done_callback(continuation)

    def _success(self, future, label):
        try:
            response = future.result()
        except Exception as exc:  # noqa: BLE001
            self._fail(f'{label} service failed: {exc}')
            return False
        if not response.success:
            self._fail(f'{label} rejected: {response.status_message}')
            return False
        return True

    def _after_floor(self, future):
        if self._success(future, 'floor spawn'):
            self._spawn('care_table', self._table_sdf(), float(self._value('table_x')),
                        float(self._value('table_y')), 0.0, self._after_table)

    def _after_table(self, future):
        if self._success(future, 'table spawn'):
            self._spawn('red_ball', self._ball_sdf(), float(self._value('ball_x')),
                        float(self._value('ball_y')), self.ball_z, self._after_ball)

    def _after_ball(self, future):
        if not self._success(future, 'red ball spawn'):
            return
        request = ApplyPlanningScene.Request()
        request.scene = self._planning_scene()
        result = self.apply_scene_client.call_async(request)
        result.add_done_callback(self._after_scene)

    def _after_scene(self, future):
        try:
            response = future.result()
        except Exception as exc:  # noqa: BLE001
            self._fail(f'MoveIt scene update failed: {exc}')
            return
        if not response.success:
            self._fail('MoveIt rejected the red-ball planning scene.')
            return
        self.busy = False
        self._publish_ready(True)
        self.get_logger().info('Red ball scene ready: Gazebo and MoveIt are synchronized.')

    def _fail(self, reason):
        self.busy = False
        self._publish_ready(False)
        self.get_logger().error(reason)

    @staticmethod
    def _floor_sdf():
        return '''<sdf version="1.7"><model name="care_floor"><static>true</static><link name="floor"><collision name="c"><pose>0 0 -0.26 0 0 0</pose><geometry><box><size>4 4 0.02</size></box></geometry></collision><visual name="v"><pose>0 0 -0.26 0 0 0</pose><geometry><box><size>4 4 0.02</size></box></geometry><material><ambient>0.58 0.60 0.63 1</ambient></material></visual></link></model></sdf>'''

    def _table_sdf(self):
        length, width = float(self._value('table_length')), float(self._value('table_width'))
        thickness, center_z = float(self._value('table_thickness')), float(self._value('table_center_z'))
        return f'''<sdf version="1.7"><model name="care_table"><static>true</static><link name="table"><collision name="c"><pose>0 0 {center_z} 0 0 0</pose><geometry><box><size>{length} {width} {thickness}</size></box></geometry></collision><visual name="v"><pose>0 0 {center_z} 0 0 0</pose><geometry><box><size>{length} {width} {thickness}</size></box></geometry><material><ambient>0.18 0.42 0.62 1</ambient><diffuse>0.22 0.52 0.76 1</diffuse></material></visual></link></model></sdf>'''

    def _ball_sdf(self):
        path = Path(get_package_share_directory('brain_robot_ball_pick')) / 'models' / 'red_ball' / 'model.sdf.in'
        radius, mass = float(self._value('ball_radius')), float(self._value('ball_mass'))
        physics = bool(self._value('physics_grasp'))
        flow_demo = bool(self._value('flow_demo'))
        if physics == flow_demo:
            raise ValueError('Select exactly one of physics_grasp or flow_demo')
        pose_plugin = '' if physics else '''<plugin name="ball_pose_plugin" filename="libcup_pose_plugin.so">
      <ros><namespace>/brain_robot_ball_pick</namespace></ros>
      <topic>ball_target_pose</topic>
    </plugin>'''
        return path.read_text(encoding='utf-8').format(
            ball_radius=radius, ball_mass=mass, ball_inertia=0.4 * mass * radius * radius,
            no_contact_force=str(flow_demo).lower(), gravity=str(physics).lower(),
            friction=float(self._value('object_friction')),
            contact_kp=float(self._value('contact_kp')), contact_kd=float(self._value('contact_kd')),
            pose_plugin=pose_plugin)

    def _planning_scene(self):
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        # A single ApplyPlanningScene request cannot safely remove and add the
        # same object id. Gazebo has already been reset above; ADD replaces the
        # two task objects in this fresh simulation session.
        table = CollisionObject()
        table.header.frame_id, table.id, table.operation = self.world_frame, 'care_table', CollisionObject.ADD
        table_box = SolidPrimitive(type=SolidPrimitive.BOX)
        max_x = float(self._value('table_x')) + float(self._value('table_length')) / 2.0
        min_x = float(self._value('planning_table_min_x'))
        table_box.dimensions = [max_x - min_x, float(self._value('table_width')),
                                float(self._value('table_thickness'))]
        table.primitives.append(table_box)
        table.primitive_poses.append(self._pose(
            min_x + (max_x - min_x) / 2.0, float(self._value('table_y')),
            float(self._value('table_center_z'))))
        scene.world.collision_objects.append(table)
        ball = CollisionObject()
        ball.header.frame_id, ball.id, ball.operation = self.world_frame, 'red_ball', CollisionObject.ADD
        sphere = SolidPrimitive(type=SolidPrimitive.SPHERE)
        sphere.dimensions = [float(self._value('ball_radius'))]
        ball.primitives.append(sphere)
        ball.primitive_poses.append(self._pose(float(self._value('ball_x')), float(self._value('ball_y')), self.ball_z))
        scene.world.collision_objects.append(ball)
        return scene


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = BallSceneManager()
        rclpy.spin(node)
    except (KeyboardInterrupt, RuntimeError, ValueError) as exc:
        if node is not None:
            node.get_logger().error(str(exc))
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
