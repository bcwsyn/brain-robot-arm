#!/usr/bin/env python3
"""Keep the Gazebo scene and MoveIt planning scene geometrically identical."""

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


class SceneManager(Node):
    """Spawn the fixed scene in Gazebo and mirror it into MoveIt."""

    def __init__(self):
        super().__init__('scene_manager')

        self.declare_parameter('simulation_only', True)
        self.declare_parameter('world_frame', 'world')
        self.declare_parameter('floor_name', 'care_floor')
        self.declare_parameter('floor_size', 4.00)
        self.declare_parameter('floor_thickness', 0.02)
        self.declare_parameter('floor_z', -0.25)
        self.declare_parameter('table_name', 'care_table')
        self.declare_parameter('table_length', 0.70)
        self.declare_parameter('table_width', 0.50)
        self.declare_parameter('table_thickness', 0.05)
        self.declare_parameter('table_x', 0.35)
        self.declare_parameter('table_y', 0.00)
        self.declare_parameter('table_surface_z', 0.00)
        self.declare_parameter('table_center_z', -0.025)
        self.declare_parameter('planning_table_min_x', 0.10)
        self.declare_parameter('cup_name', 'medicine_cup')
        self.declare_parameter('cup_radius', 0.035)
        self.declare_parameter('cup_height', 0.10)
        self.declare_parameter('cup_mass', 0.08)
        self.declare_parameter('cup_x', 0.40)
        self.declare_parameter('cup_y', -0.12)
        self.declare_parameter('cup_z', 0.05)
        self.declare_parameter('cup_model_sdf', '')

        if not self.get_parameter('simulation_only').value:
            raise RuntimeError(
                'simulation_only=false is forbidden in this package; no real-arm command was sent')

        self.declare_parameter('flow_demo', True)
        self.declare_parameter('physics_grasp', False)
        self.declare_parameter('object_friction', 1.2)
        self.declare_parameter('contact_kp', 100000.0)
        self.declare_parameter('contact_kd', 10.0)
        self.world_frame = str(self.get_parameter('world_frame').value)
        self.floor_name = str(self.get_parameter('floor_name').value)
        self.table_name = str(self.get_parameter('table_name').value)
        self.cup_name = str(self.get_parameter('cup_name').value)
        self._validate_parameters()

        self.delete_client = self.create_client(DeleteEntity, '/delete_entity')
        self.spawn_client = self.create_client(SpawnEntity, '/spawn_entity')
        self.apply_scene_client = self.create_client(
            ApplyPlanningScene, '/apply_planning_scene')

        ready_qos = QoSProfile(depth=1)
        ready_qos.reliability = ReliabilityPolicy.RELIABLE
        ready_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.ready_publisher = self.create_publisher(
            Bool, '/brain_robot_pick_place/scene_ready', ready_qos)
        self.reset_service = self.create_service(
            Trigger, '/brain_robot_pick_place/reset_scene', self._on_reset)

        self._busy = False
        self._requested = True
        self._wait_notice_printed = False
        self._publish_ready(False)
        self.timer = self.create_timer(1.0, self._try_start)

    def _value(self, name):
        return self.get_parameter(name).value

    def _publish_ready(self, ready):
        message = Bool()
        message.data = ready
        self.ready_publisher.publish(message)

    def _on_reset(self, _request, response):
        self._requested = True
        self._publish_ready(False)
        response.success = True
        response.message = 'Scene reset has been queued.'
        return response

    def _try_start(self):
        if self._busy or not self._requested:
            return

        clients = (self.delete_client, self.spawn_client, self.apply_scene_client)
        if not all(client.service_is_ready() for client in clients):
            if not self._wait_notice_printed:
                self.get_logger().info(
                    'Waiting for Gazebo factory and MoveIt planning-scene services...')
                self._wait_notice_printed = True
            return

        self._requested = False
        self._busy = True
        self._wait_notice_printed = False
        self._publish_ready(False)
        self.get_logger().info('Resetting Gazebo and MoveIt scene...')
        self._delete_entities(
            ['ground_plane', self.floor_name, self.table_name, self.cup_name],
            self._after_entities_deleted)

    def _delete_entities(self, names, continuation):
        if not names:
            continuation()
            return
        request = DeleteEntity.Request()
        request.name = names[0]
        future = self.delete_client.call_async(request)
        future.add_done_callback(
            lambda _result: self._delete_entities(names[1:], continuation))

    def _after_entities_deleted(self):
        try:
            floor_xml = self._build_floor_sdf()
        except Exception as exc:  # noqa: BLE001 - report template errors to ROS log
            self._fail(f'Could not build floor SDF: {exc}')
            return
        self._spawn_entity(
            self.floor_name, floor_xml, 0.0, 0.0, 0.0,
            self._after_floor_spawned)

    def _spawn_entity(self, name, xml, x, y, z, continuation):
        request = SpawnEntity.Request()
        request.name = name
        request.xml = xml
        request.robot_namespace = '/brain_robot_pick_place'
        request.reference_frame = self.world_frame
        request.initial_pose = self._pose(x, y, z)
        future = self.spawn_client.call_async(request)
        future.add_done_callback(lambda result: continuation(result))

    def _after_floor_spawned(self, future):
        if not self._service_succeeded(future, 'floor spawn'):
            return
        try:
            table_xml = self._build_table_sdf()
        except Exception as exc:  # noqa: BLE001
            self._fail(f'Could not build table SDF: {exc}')
            return
        self._spawn_entity(
            self.table_name, table_xml,
            float(self._value('table_x')), float(self._value('table_y')), 0.0,
            self._after_table_spawned)

    def _after_table_spawned(self, future):
        if not self._service_succeeded(future, 'table spawn'):
            return
        try:
            cup_xml = self._build_cup_sdf()
        except Exception as exc:  # noqa: BLE001
            self._fail(f'Could not build cup SDF: {exc}')
            return
        self._spawn_entity(
            self.cup_name, cup_xml,
            float(self._value('cup_x')),
            float(self._value('cup_y')),
            float(self._value('cup_z')),
            self._after_cup_spawned)

    def _after_cup_spawned(self, future):
        if not self._service_succeeded(future, 'cup spawn'):
            return

        request = ApplyPlanningScene.Request()
        request.scene = self._build_planning_scene()
        result = self.apply_scene_client.call_async(request)
        result.add_done_callback(self._after_scene_applied)

    def _after_scene_applied(self, future):
        try:
            response = future.result()
        except Exception as exc:  # noqa: BLE001
            self._fail(f'ApplyPlanningScene service failed: {exc}')
            return
        if not response.success:
            self._fail('MoveIt rejected the planning-scene update.')
            return

        self._busy = False
        self._publish_ready(True)
        self.get_logger().info(
            'Scene ready: lowered floor, care_table and medicine_cup are synchronized.')

    def _service_succeeded(self, future, operation):
        try:
            response = future.result()
        except Exception as exc:  # noqa: BLE001
            self._fail(f'{operation} service failed: {exc}')
            return False
        if not response.success:
            self._fail(f'{operation} was rejected: {response.status_message}')
            return False
        return True

    def _fail(self, message):
        self._busy = False
        self._publish_ready(False)
        self.get_logger().error(message)

    def _validate_parameters(self):
        length = float(self._value('table_length'))
        width = float(self._value('table_width'))
        thickness = float(self._value('table_thickness'))
        table_x = float(self._value('table_x'))
        table_y = float(self._value('table_y'))
        surface_z = float(self._value('table_surface_z'))
        center_z = float(self._value('table_center_z'))
        floor_z = float(self._value('floor_z'))
        cup_x = float(self._value('cup_x'))
        cup_y = float(self._value('cup_y'))
        cup_z = float(self._value('cup_z'))
        cup_height = float(self._value('cup_height'))
        planning_min_x = float(self._value('planning_table_min_x'))

        positive_values = (
            length, width, thickness,
            float(self._value('floor_size')),
            float(self._value('floor_thickness')),
            float(self._value('cup_radius')), cup_height,
            float(self._value('cup_mass')),
        )
        if min(positive_values) <= 0.0:
            raise ValueError('all scene dimensions and cup mass must be positive')
        if abs(center_z - (surface_z - thickness / 2.0)) > 1.0e-6:
            raise ValueError('table_center_z must place the tabletop surface at table_surface_z')
        if floor_z >= center_z - thickness / 2.0:
            raise ValueError('floor_z must be below the underside of the tabletop')

        min_x = table_x - length / 2.0
        max_x = table_x + length / 2.0
        min_y = table_y - width / 2.0
        max_y = table_y + width / 2.0
        if not (min_x <= planning_min_x < max_x):
            raise ValueError('planning_table_min_x must lie inside the visual tabletop')
        if not (planning_min_x <= cup_x <= max_x and min_y <= cup_y <= max_y):
            raise ValueError('cup must lie on the tabletop and outside the base clearance zone')
        expected_cup_z = surface_z + cup_height / 2.0
        if abs(cup_z - expected_cup_z) > 1.0e-6:
            raise ValueError('cup_z must place the cup bottom on table_surface_z')

    def _build_floor_sdf(self):
        template = self._read_template('care_floor')
        size = float(self._value('floor_size'))
        thickness = float(self._value('floor_thickness'))
        surface_z = float(self._value('floor_z'))
        return template.format(
            floor_size=size,
            floor_thickness=thickness,
            floor_center_z=surface_z - thickness / 2.0,
        )

    def _build_table_sdf(self):
        template = self._read_template('care_table')
        length = float(self._value('table_length'))
        width = float(self._value('table_width'))
        thickness = float(self._value('table_thickness'))
        center_z = float(self._value('table_center_z'))
        floor_z = float(self._value('floor_z'))
        leg_top_z = center_z - thickness / 2.0
        leg_height = leg_top_z - floor_z
        if min(length, width, thickness, leg_height) <= 0.0:
            raise ValueError('table dimensions must be positive')
        return template.format(
            table_length=length,
            table_width=width,
            table_thickness=thickness,
            table_center_z=center_z,
            leg_x=length / 2.0 - 0.05,
            negative_leg_x=-(length / 2.0 - 0.05),
            leg_y=width / 2.0 - 0.05,
            negative_leg_y=-(width / 2.0 - 0.05),
            leg_height=leg_height,
            leg_center_z=(leg_top_z + floor_z) / 2.0,
        )

    def _build_cup_sdf(self):
        hollow = str(self._value('cup_model_sdf'))
        if hollow:
            if not self._value('physics_grasp') or self._value('flow_demo'):
                raise ValueError('Hollow cup requires physical mode with pose following disabled')
            return Path(hollow).read_text(encoding='utf-8')
        template = self._read_template('medicine_cup')
        radius = float(self._value('cup_radius'))
        height = float(self._value('cup_height'))
        mass = float(self._value('cup_mass'))
        if min(radius, height, mass) <= 0.0:
            raise ValueError('cup radius, height and mass must be positive')
        physics = bool(self._value('physics_grasp'))
        flow_demo = bool(self._value('flow_demo'))
        if physics == flow_demo:
            raise ValueError('Select exactly one of physics_grasp or flow_demo')
        pose_plugin = '' if physics else '''<plugin name="cup_pose_plugin" filename="libcup_pose_plugin.so">
      <ros><namespace>/brain_robot_pick_place</namespace></ros>
      <topic>cup_target_pose</topic>
    </plugin>'''
        return template.format(
            no_contact_force=str(flow_demo).lower(), gravity=str(physics).lower(),
            friction=float(self._value('object_friction')),
            contact_kp=float(self._value('contact_kp')), contact_kd=float(self._value('contact_kd')),
            pose_plugin=pose_plugin,
            cup_radius=radius,
            cup_height=height,
            cup_mass=mass,
            inertia_xy=mass * (3.0 * radius * radius + height * height) / 12.0,
            inertia_z=0.5 * mass * radius * radius,
        )

    @staticmethod
    def _read_template(model_name):
        share = Path(get_package_share_directory('brain_robot_pick_place'))
        return (share / 'models' / model_name / 'model.sdf.in').read_text(
            encoding='utf-8')

    def _build_planning_scene(self):
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True

        table = CollisionObject()
        table.header.frame_id = self.world_frame
        table.id = self.table_name
        table.operation = CollisionObject.ADD
        table_box = SolidPrimitive()
        table_box.type = SolidPrimitive.BOX
        visual_table_max_x = (
            float(self._value('table_x')) +
            float(self._value('table_length')) / 2.0)
        planning_table_min_x = float(self._value('planning_table_min_x'))
        planning_table_length = visual_table_max_x - planning_table_min_x
        table_box.dimensions = [
            planning_table_length,
            float(self._value('table_width')),
            float(self._value('table_thickness')),
        ]
        table.primitives.append(table_box)
        table.primitive_poses.append(self._pose(
            planning_table_min_x + planning_table_length / 2.0,
            float(self._value('table_y')),
            float(self._value('table_center_z'))))

        cup = CollisionObject()
        cup.header.frame_id = self.world_frame
        cup.id = self.cup_name
        cup.operation = CollisionObject.ADD
        cup_cylinder = SolidPrimitive()
        cup_cylinder.type = SolidPrimitive.CYLINDER
        cup_cylinder.dimensions = [
            float(self._value('cup_height')),
            float(self._value('cup_radius')),
        ]
        cup.primitives.append(cup_cylinder)
        cup.primitive_poses.append(self._pose(
            float(self._value('cup_x')),
            float(self._value('cup_y')),
            float(self._value('cup_z'))))

        scene.world.collision_objects = [table, cup]
        return scene

    @staticmethod
    def _pose(x, y, z):
        pose = Pose()
        pose.position.x = x
        pose.position.y = y
        pose.position.z = z
        pose.orientation.w = 1.0
        return pose


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = SceneManager()
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
