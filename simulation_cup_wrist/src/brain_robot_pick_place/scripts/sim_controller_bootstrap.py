#!/usr/bin/env python3
"""Activate only the four Gazebo controllers; keep DDS service clients alive.

Launch this inside the simulation's isolated ROS domain after spawning Piper.
The two-second discovery window avoids querying a just-created response reader.
"""
import time
import rclpy
from rclpy.node import Node
from controller_manager_msgs.srv import ListControllers, LoadController, ConfigureController, SwitchController


def main():
    rclpy.init()
    node = Node('sim_controller_bootstrap')
    clients = {name: node.create_client(service, '/controller_manager/' + name)
               for name, service in [('list_controllers', ListControllers),
                                     ('load_controller', LoadController),
                                     ('configure_controller', ConfigureController),
                                     ('switch_controller', SwitchController)]}
    try:
        for client in clients.values():
            if not client.wait_for_service(timeout_sec=60):
                raise RuntimeError('Gazebo controller manager service unavailable')
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=.1)

        def call(name, request):
            future = clients[name].call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=30)
            if not future.done() or future.result() is None:
                raise RuntimeError(name + ' did not respond')
            return future.result()

        required = ['joint_state_broadcaster', 'arm_controller', 'gripper_controller', 'gripper8_controller']
        existing = {c.name:c.state for c in call('list_controllers', ListControllers.Request()).controller}
        inactive = []
        for name in required:
            state = existing.get(name)
            if state is None:
                if not call('load_controller', LoadController.Request(name=name)).ok:
                    raise RuntimeError('Cannot load ' + name)
                state = 'unconfigured'
            if state == 'unconfigured':
                if not call('configure_controller', ConfigureController.Request(name=name)).ok:
                    raise RuntimeError('Cannot configure ' + name)
                state = 'inactive'
            if state != 'active':
                inactive.append(name)
        if inactive:
            request = SwitchController.Request()
            request.activate_controllers = inactive
            request.strictness = SwitchController.Request.STRICT
            request.activate_asap = True
            request.timeout.sec = 10
            if not call('switch_controller', request).ok:
                raise RuntimeError('Cannot activate Gazebo controllers')
        node.get_logger().info('All four Gazebo controllers active; retaining service clients.')
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        node.get_logger().error(str(exc))
        return 1
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
