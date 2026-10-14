#!/usr/bin/env python3
"""Read-only normal-force recording for an existing domain-83 Gazebo session."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

WS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS/'src/brain_robot_pick_place/scripts'))
from contact_force_feedback import target_normal_force


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=90)
    parser.add_argument('--target', default='medicine_cup')
    args = parser.parse_args()
    if os.environ.get('ROS_DOMAIN_ID') != '83' or not 0 < args.duration <= 300:
        parser.error('Requires ROS_DOMAIN_ID=83 and duration in (0, 300]')
    if args.output.exists():
        parser.error('output must not exist')
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from gazebo_msgs.msg import ContactsState
    rclpy.init()
    node = rclpy.create_node('contact_force_recorder')
    samples, errors, subscriptions = [], [], []
    start = time.monotonic()
    def receive(msg, jaw):
        try:
            force, count = target_normal_force(msg, args.target)
            if count:
                samples.append(dict(elapsed_s=time.monotonic()-start, jaw=jaw,
                    sim_time_s=msg.header.stamp.sec+msg.header.stamp.nanosec/1e9,
                    normal_force_n=force, contact_points=count, frame=msg.header.frame_id))
        except ValueError as error:
            errors.append(str(error))
    for jaw in (7, 8):
        subscriptions.append(node.create_subscription(ContactsState, f'/brain_robot_physics/link{jaw}_contacts',
            lambda msg, jaw=jaw: receive(msg, jaw), qos_profile_sensor_data))
    try:
        while time.monotonic()-start < args.duration:
            rclpy.spin_once(node, timeout_sec=.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary = {str(jaw): dict(samples=sum(s['jaw'] == jaw for s in samples),
        peak_normal_force_n=max((s['normal_force_n'] for s in samples if s['jaw'] == jaw), default=0)) for jaw in (7, 8)}
    args.output.write_text(json.dumps(dict(mode='read-only; does not regulate force', unit='N',
        target=args.target, summary=summary, errors=errors, samples=samples), indent=2)+'\n')
    print(json.dumps(summary), flush=True)
    return 0 if samples and not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
