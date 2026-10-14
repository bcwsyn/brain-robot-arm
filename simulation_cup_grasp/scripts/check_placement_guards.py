#!/usr/bin/env python3
"""Read/rejection checks against an already-running simulation console (domain 83)."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['idle', 'busy'], required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get('ROS_DOMAIN_ID') != '83' or os.environ.get('ROS_LOCALHOST_ONLY') != '1':
        parser.error('Use the localhost-only simulation environment, ROS domain 83.')
    import rclpy
    from rclpy.parameter import Parameter
    from rclpy.qos import QoSProfile, DurabilityPolicy
    from rcl_interfaces.srv import GetParameters, SetParametersAtomically
    from std_msgs.msg import String
    rclpy.init()
    node = rclpy.create_node('placement_guard_validation')
    current = {'visual': None}
    sub = node.create_subscription(String, '/brain_robot_visual_control/state',
        lambda msg: current.update(visual=msg.data), QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    setter = node.create_client(SetParametersAtomically, '/grasp_lift_executor/set_parameters_atomically')
    getter = node.create_client(GetParameters, '/grasp_lift_executor/get_parameters')

    def wait(predicate, timeout=240):
        deadline = time.monotonic()+timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise RuntimeError('Timed out waiting for simulation test condition')
            rclpy.spin_once(node, timeout_sec=.05)

    def call(client, request):
        future = client.call_async(request)
        wait(future.done, 10)
        return future.result()

    def values():
        request = GetParameters.Request()
        request.names = ['place_x', 'place_y']
        return [v.double_value for v in call(getter, request).values]

    result = {'phase': args.phase, 'checks': [], 'passed': False}
    try:
        wait(lambda: setter.service_is_ready() and getter.service_is_ready())
        wait(lambda: current['visual'] == 'IDLE' if args.phase == 'idle'
             else current['visual'] in ('SEARCH', 'ALIGN', 'GRASP_READY'))
        before = values()
        tests = [('busy_update', .4)] if args.phase == 'busy' else [
            ('out_of_bounds', 2.), ('nonfinite', float('nan')), ('wrong_type', 1)]
        for name, x in tests:
            request = SetParametersAtomically.Request()
            request.parameters = [Parameter('place_x', value=x).to_parameter_msg(),
                                  Parameter('place_y', value=.14).to_parameter_msg()]
            response = call(setter, request).result
            after = values()
            passed = not response.successful and before == after
            result['checks'].append(dict(case=name, input_x=repr(x), rejected=not response.successful,
                                         reason=response.reason, before=before, after=after, passed=passed))
        result['passed'] = all(row['passed'] for row in result['checks'])
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n')
        node.destroy_node()
        rclpy.shutdown()
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
