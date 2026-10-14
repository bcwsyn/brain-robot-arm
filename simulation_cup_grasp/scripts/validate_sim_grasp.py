#!/usr/bin/env python3
"""Bounded Gazebo-only validation; measures entity poses instead of follow commands.

Source simulation/install/setup.bash first. No hardware package is launched.
Results describe flow validation, never contact/friction grasp success.
"""
import argparse
from collections import deque
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=['cup-known', 'cup-vision', 'ball'])
    parser.add_argument('--debug-server', action='store_true')
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--negative-case', choices=['estop', 'stop', 'target-loss', 'unreachable'])
    parser.add_argument('--scene-params-file', type=Path)
    parser.add_argument('--timeout', type=float, default=300.0)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--params-file', type=Path,
                        help='Optional simulation profile for a controlled comparison')
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20 or (args.negative_case and args.repetitions != 1):
        parser.error("Use 1..20 repetitions; negative cases require one repetition.")
    workspace = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'validator_pid.txt').write_text(str(os.getpid()) + '\n')
    # Keep this test's ROS/Gazebo discovery separate from ordinary sessions.
    os.environ.update(ROS_DOMAIN_ID='82', ROS_LOCALHOST_ONLY='1',
                      GAZEBO_MASTER_URI='http://127.0.0.1:11482',
                      ROS_LOG_DIR=str(args.output.resolve() / 'ros_logs'),
                      FASTRTPS_DEFAULT_PROFILES_FILE=str(workspace / 'validation/fastdds_local_udp.xml'),
                      RMW_FASTRTPS_PUBLICATION_MODE='ASYNCHRONOUS')
    import rclpy
    from rclpy.qos import QoSProfile, DurabilityPolicy, qos_profile_sensor_data
    from gazebo_msgs.msg import ModelStates
    from std_msgs.msg import Bool, String
    from sensor_msgs.msg import Image, JointState
    from moveit_msgs.srv import GetPositionIK, GetPlanningScene, ApplyPlanningScene
    from moveit_msgs.msg import PlanningScene, PlanningSceneComponents, CollisionObject
    from control_msgs.msg import JointJog
    from controller_manager_msgs.srv import ListControllers
    from std_srvs.srv import Trigger

    rclpy.init()
    node = rclpy.create_node('simulation_grasp_validation')
    started = time.monotonic()
    result = dict(task=args.task, passed=False, validation_kind='follow_based_flow',
                  events=[], model_samples=[], target_valid_frames=0, camera_frames=0,
                  controller_names=[], start_response=None)
    result['params_file'] = str(args.params_file.resolve()) if args.params_file else 'default'
    trial_results = []
    group_started = started
    processes, handles = [], []
    current = {'ready': False, 'grasp': '', 'visual': '', 'pose': None}
    joint_samples = deque()
    stop_client = node.create_client(Trigger, '/visual_search_controller/stop') if args.negative_case == 'stop' else None
    estop_publisher = node.create_publisher(Bool, '/brain_robot_control/emergency_stop', 10) if args.negative_case == 'estop' else None
    prefix = '/brain_robot_ball_pick' if args.task == 'ball' else '/brain_robot_pick_place'
    model = 'red_ball' if args.task == 'ball' else 'medicine_cup'
    transient = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)

    def event(topic, message):
        value = message.data
        if topic == 'diagnostic' and value == 'CONTROL_CLAIM_CONFIRMED':
            current['owned'] = True
        if topic == 'diagnostic' and value == 'CONTROL_RELEASE_CONFIRMED':
            current['owned'] = False
        if current.get(topic) != value:
            current[topic] = value
            entry = dict(t=round(time.monotonic() - started, 3), topic=topic, value=value)
            result['events'].append(entry)
            print(json.dumps(entry), flush=True)

    subscriptions = [
        node.create_subscription(Bool, prefix + '/scene_ready',
                                 lambda msg: event('ready', msg), transient),
        node.create_subscription(String, '/brain_robot_grasp/state',
                                 lambda msg: event('grasp', msg), transient),
        node.create_subscription(String, '/brain_robot_visual_control/state',
                                 lambda msg: event('visual', msg), transient),
        node.create_subscription(String, '/brain_robot_visual_control/reason',
                                 lambda msg: event('reason', msg), transient),
        node.create_subscription(String, '/brain_robot_grasp/diagnostic',
                                 lambda msg: event('diagnostic', msg), 10),
    ]

    def models(msg):
        if model not in msg.name:
            return
        pose = msg.pose[msg.name.index(model)]
        current['pose'] = [pose.position.x, pose.position.y, pose.position.z]
        q = pose.orientation
        current['object_tilt_rad'] = math.acos(max(-1., min(1., 1.-2.*(q.x*q.x+q.y*q.y))))
        result['maximum_z'] = max(result.get('maximum_z', pose.position.z), pose.position.z)
        elapsed = round(time.monotonic() - started, 3)
        if not result['model_samples'] or elapsed - result['model_samples'][-1]['t'] >= 0.5:
            result['model_samples'].append(dict(t=elapsed, xyz=current['pose']))

    def valid(msg):
        result['target_valid_frames'] += int(msg.data)

    def camera(msg):
        result['camera_frames'] += 1
        if result['camera_frames'] == 1:
            try:
                from PIL import Image as PillowImage
                if msg.encoding not in ('rgb8', 'bgr8'):
                    raise ValueError('Unsupported snapshot encoding: ' + msg.encoding)
                image = PillowImage.frombytes('RGB', (msg.width, msg.height),
                                              bytes(msg.data), 'raw',
                                              'RGB' if msg.encoding == 'rgb8' else 'BGR',
                                              msg.step)
                image.save(args.output / 'camera_first.png')
            except Exception as exc:
                result['camera_snapshot_error'] = str(exc)

    def joints(msg):
        current['joints'] = msg
        if all(name in msg.name for name in ['joint1','joint2','joint3','joint4','joint5','joint6']):
            current['arm_positions'] = [msg.position[msg.name.index('joint' + str(i))] for i in range(1, 7)]
            current['arm_velocities'] = [msg.velocity[msg.name.index('joint' + str(i))] for i in range(1, 7)]
            if args.negative_case:
                sample_time = time.monotonic()
                joint_samples.append((sample_time, list(current['arm_positions'])))
                while joint_samples and joint_samples[0][0] < sample_time - 3.0:
                    joint_samples.popleft()

    def jog(msg):
        if current.get('owned') and any(abs(v) > 1e-9 for v in msg.velocities):
            result['nonzero_jogs_while_owned'] = result.get('nonzero_jogs_while_owned', 0) + 1

    subscriptions.extend([
        node.create_subscription(JointState, '/joint_states', joints, qos_profile_sensor_data),
        node.create_subscription(JointJog, '/servo_node/delta_joint_cmds', jog, 10),
        node.create_subscription(ModelStates, '/gazebo/model_states', models, qos_profile_sensor_data),
        node.create_subscription(Bool, '/brain_robot_vision/target_valid', valid, 10),
        node.create_subscription(Image, '/wrist_camera/wrist_camera/image_raw', camera,
                                 qos_profile_sensor_data),
    ])

    def launch(label, package, filename, *arguments):
        log = (args.output / (label + '.log')).open('w')
        handles.append(log)
        command = ['ros2', 'launch', package, filename, *arguments]
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        processes.append((label, process))
        (args.output / 'owned_process_groups.json').write_text(json.dumps(
            {name: child.pid for name, child in processes}, indent=2) + '\n')
        print('Started ' + label, flush=True)
        return process

    def wait_until(predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if predicate():
                return True
            dead = [label for label, process in processes
                    if process.poll() is not None and label != 'task' and
                    not (args.negative_case == 'target-loss' and label == 'detector')]
            if dead:
                raise RuntimeError('Simulation processes exited: ' + ', '.join(dead))
        return False

    try:
        launch('gazebo', 'brain_robot_pick_place', 'wrist_camera_gazebo.launch.py',
               'gui:=false', 'world:=' + str(workspace / 'validation/grasp_validation.world'),
               *(['debug_server:=true', 'gdb_script:=' + str(workspace / 'validation/step1/gazebo_rpc_backtrace.gdb')] if args.debug_server else []))
        launch('moveit', 'piper_with_gripper_moveit', 'piper_moveit.launch.py', 'start_rviz:=false')
        controllers = node.create_client(ListControllers, '/controller_manager/list_controllers')
        if not controllers.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('Controller manager unavailable')
        discovery_deadline = time.monotonic() + 2.0
        wait_until(lambda: time.monotonic() >= discovery_deadline, 3.0)
        pending = None

        def controllers_ready():
            nonlocal pending
            if pending is None:
                pending = controllers.call_async(ListControllers.Request())
            if not pending.done():
                return False
            result['controller_names'] = [{"name": item.name, "state": item.state}
                                          for item in pending.result().controller]
            active = {item['name'] for item in result['controller_names'] if item['state'] == 'active'}
            pending = None
            return {'arm_controller', 'gripper_controller', 'gripper8_controller',
                    'joint_state_broadcaster'} <= active

        if not wait_until(controllers_ready, 45.0):
            raise RuntimeError('Motion controllers did not become active')
        launch('scene', 'brain_robot_ball_pick' if args.task == 'ball' else 'brain_robot_pick_place',
               'ball_scene.launch.py' if args.task == 'ball' else 'scene.launch.py',
               *(['params_file:=' + str(args.scene_params_file.resolve())] if args.scene_params_file else []))
        if not wait_until(lambda: current['ready'] and current['pose'] is not None, 90.0):
            raise RuntimeError('Scene/entity readiness timed out')
        for repetition in range(args.repetitions):
            if repetition:
                reset = node.create_client(Trigger, prefix + '/reset_scene')
                current['ready'] = False
                future = reset.call_async(Trigger.Request())
                if not wait_until(future.done, 15) or not future.result().success:
                    raise RuntimeError('Scene reset refused')
                initial = trial_results[0]['initial_xyz']
                if not wait_until(lambda: current['ready'] and current['pose'] is not None and math.dist(current['pose'], initial) < .001, 30):
                    raise RuntimeError('Reset did not restore entity pose')
                old_result = result
                result = dict(task=args.task, passed=False, validation_kind='follow_based_flow',
                    events=[], model_samples=[], target_valid_frames=0, camera_frames=0,
                    controller_names=old_result['controller_names'], start_response=None,
                    params_file=old_result['params_file'], ik_diagnostics=[])
                current['grasp'] = 'WAITING_FOR_NEW_TASK'
                started = time.monotonic()
            result['initial_xyz'] = current['pose']
            if args.negative_case == 'unreachable':
                get_scene = node.create_client(GetPlanningScene, '/get_planning_scene')
                req = GetPlanningScene.Request()
                req.components.components = PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
                future = get_scene.call_async(req)
                if not wait_until(future.done, 10):
                    raise RuntimeError('Cannot inject unreachable planning target')
                obj = next(o for o in future.result().scene.world.collision_objects if o.id == model)
                obj.pose.position.x += 2.0
                obj.operation = CollisionObject.ADD
                update = ApplyPlanningScene.Request()
                update.scene.is_diff = True
                update.scene.world.collision_objects = [obj]
                apply = node.create_client(ApplyPlanningScene, '/apply_planning_scene')
                future = apply.call_async(update)
                if not wait_until(future.done, 10) or not future.result().success:
                    raise RuntimeError('Planning fault injection refused')
                result['negative_injection'] = 'MoveIt object target shifted +2m in x; actual Gazebo object unchanged'

            # Offline service diagnostics: same pose with/without collision checking;
            # neither variant executes a trajectory or disables runtime collision checks.
            ik = node.create_client(GetPositionIK, '/compute_ik')
            result['ik_diagnostics'] = []
            if repetition == 0 and ik.wait_for_service(timeout_sec=5):
                for tilt in [0.0, .75, .95, 1.10]:
                    pitch = math.pi - tilt
                    forward = [math.sin(pitch), 0, math.cos(pitch)]
                    for stage, retreat, clearance in [('grasp',0,0), ('pregrasp',.10,.06)]:
                        for collisions in [False, True]:
                            req = GetPositionIK.Request()
                            req.ik_request.group_name = 'arm'
                            req.ik_request.ik_link_name = 'gripper_base'
                            req.ik_request.avoid_collisions = collisions
                            req.ik_request.timeout.nanosec = 100000000
                            req.ik_request.robot_state.joint_state = current.get('joints', JointState())
                            target = req.ik_request.pose_stamped
                            target.header.frame_id = 'world'
                            center = result['initial_xyz']
                            target.pose.position.x = center[0] - forward[0]*(.1358+retreat)
                            target.pose.position.y = center[1]
                            target.pose.position.z = center[2] - forward[2]*(.1358+retreat) + clearance
                            target.pose.orientation.y = math.sin(pitch/2)
                            target.pose.orientation.w = math.cos(pitch/2)
                            f = ik.call_async(req)
                            responded = wait_until(f.done, 3)
                            result['ik_diagnostics'].append(dict(tilt=tilt,stage=stage,
                                avoid_collisions=collisions, code=f.result().error_code.val if responded else None))
            if args.task == 'cup-known':
                if repetition == 0:
                    task_process = launch('task', 'brain_robot_pick_place', 'pick_place.launch.py',
                        *(['params_file:=' + str(args.params_file.resolve())] if args.params_file else []))

                client = node.create_client(Trigger, '/grasp_lift_executor/execute')
                if not wait_until(lambda: client.service_is_ready() and current['visual'] == 'IDLE', 45):
                    raise RuntimeError('Known executor not ready')
                readiness_deadline = time.monotonic() + 10.0
                while True:
                    future = client.call_async(Trigger.Request())
                    if not wait_until(future.done, 15):
                        raise RuntimeError('Known task start service timed out')
                    response = future.result()
                    if response.success:
                        break
                    if time.monotonic() >= readiness_deadline:
                        raise RuntimeError('Known task refused: ' + response.message)
                    settle = time.monotonic() + .2
                    wait_until(lambda: time.monotonic() >= settle, .5)
                result['start_response'] = dict(success=True, message=response.message)
                def complete():
                    if current['grasp'].startswith('FAULT'):
                        if args.negative_case == 'unreachable':
                            return True
                        raise RuntimeError('Known task fault: ' + current['grasp'])
                    return current['grasp'] == 'COMPLETE'
            else:
                package = 'brain_robot_ball_pick' if args.task == 'ball' else 'brain_robot_pick_place'
                if repetition == 0:
                    detector_process = launch('detector', package, 'ball_detector.launch.py' if args.task == 'ball'
                           else 'cup_detector.launch.py')
                    launch('task', package, 'ball_visual_search.launch.py' if args.task == 'ball'
                           else 'visual_search.launch.py',
                           *(['params_file:=' + str(args.params_file.resolve())] if args.params_file else []))
                client = node.create_client(Trigger, '/visual_search_controller/start')
                if not wait_until(lambda: client.service_is_ready() and current['visual'] == 'IDLE', 45.0):
                    raise RuntimeError('Visual controller readiness timed out')
                # The start service can be discovered before the controller receives
                # its first joint sample. Retry this readiness rejection only.
                start_deadline = time.monotonic() + 10.0
                while True:
                    future = client.call_async(Trigger.Request())
                    if not wait_until(future.done, 15.0):
                        raise RuntimeError('Visual start service timed out')
                    response = future.result()
                    if response.success or not response.message.startswith('No fresh joint state'):
                        break
                    if time.monotonic() >= start_deadline:
                        break
                    settle = time.monotonic() + 0.5
                    wait_until(lambda: time.monotonic() >= settle, 1.0)
                result['start_response'] = dict(success=response.success, message=response.message)
                if not response.success:
                    raise RuntimeError('Start refused: ' + response.message)

                injected = False
                def complete():
                    nonlocal injected
                    case = args.negative_case
                    stage = current['grasp']
                    if not injected and case in ('stop', 'estop') and stage == 'DIAGONAL_SIDE_APPROACH_EXECUTING':
                        injected = True
                        result['negative_injected_at'] = time.monotonic() - started
                        result['positions_at_stop'] = current.get('arm_positions')
                        if case == 'estop':
                            current['estop_publisher'] = estop_publisher
                            estop_publisher.publish(Bool(data=True))
                        else:
                            current['stop_future'] = stop_client.call_async(Trigger.Request())
                    if not injected and case == 'target-loss' and current['visual'] in ('SEARCH','ALIGN'):
                        injected = True
                        os.killpg(detector_process.pid, signal.SIGINT)
                        result['negative_injected_at'] = time.monotonic() - started
                    if case == 'estop' and injected and current['visual'] != 'FAULT':
                        current['estop_publisher'].publish(Bool(data=True))
                    if case == 'stop' and injected and current['visual'] == 'STOPPED':
                        return True
                    if case == 'estop' and injected and current['visual'] == 'FAULT':
                        return True
                    if case == 'target-loss' and injected and current['visual'] == 'FAULT':
                        return True
                    if case in ('stop', 'estop') and injected:
                        return False  # Wait for the controller's independently delivered stop state.
                    if current['visual'] == 'FAULT' or current['grasp'].startswith('FAULT'):
                        raise RuntimeError('Task fault: ' + current['grasp'] + ' / ' + current['reason'])
                    return current['grasp'] == 'COMPLETE'

            if not wait_until(complete, args.timeout):
                raise RuntimeError('Task completion timed out')
            terminal_positions = current.get('arm_positions')
            terminal_time = time.monotonic()
            end_wait = time.monotonic() + 2.0
            wait_until(lambda: time.monotonic() >= end_wait, 3.0)
            result['final_xyz'] = current['pose']
            target = [0.4, 0.12, result['initial_xyz'][2]]
            result['placement_error_m'] = math.dist(result['final_xyz'], target)
            result['peak_lift_height_m'] = result['maximum_z'] - result['initial_xyz'][2]
            result['object_tilt_rad'] = current.get('object_tilt_rad')
            result['home_error_rad'] = max(abs(x) for x in current.get('arm_positions', [999]))
            result['nonzero_jogs_while_owned'] = result.get('nonzero_jogs_while_owned', 0)
            result['passed'] = (result['placement_error_m'] < 0.03 and result['peak_lift_height_m'] >= 0.05
                                and result['home_error_rad'] < .02 and not result['nonzero_jogs_while_owned']
                                and result['object_tilt_rad'] < math.radians(10)
                                and current['visual'] == 'IDLE' and not current.get('owned', False))
            if args.negative_case in ('stop', 'estop', 'target-loss'):
                # Allow cancellation to settle for 0.5 s, then inspect all position
                # samples in the remaining window rather than net displacement.
                samples = [(t, p) for t, p in joint_samples if t >= terminal_time + .5]
                speeds = []
                if samples:
                    previous_t, previous_p = samples[0]
                    for t, p in samples[1:]:
                        dt = t - previous_t
                        if dt >= .01:
                            speeds.append(max(abs(a-b) for a,b in zip(p, previous_p)) / dt)
                            previous_t, previous_p = t, p
                coverage = samples[-1][0] - samples[0][0] if samples else 0.
                result['stop_measurement_coverage_s'] = coverage
                result['stopped_velocity_rad_s'] = max(speeds, default=999.)
                result['stop_joint_feedback_fresh'] = bool(samples and time.monotonic()-samples[-1][0] < .25)
                result['stop_net_velocity_rad_s'] = (max(abs(a-b) for a,b in zip(terminal_positions, current.get('arm_positions', []))) / 2.0 if terminal_positions else 999)
                result['passed'] = ('negative_injected_at' in result and result['stopped_velocity_rad_s'] < .02 and
                    coverage >= 1.0 and result['stop_joint_feedback_fresh'] and
                    result['peak_lift_height_m'] < .05 and
                    (current['visual'] == 'STOPPED' if args.negative_case == 'stop' else
                     current.get('reason') == 'EOG_OR_EXTERNAL_EMERGENCY_STOP' if args.negative_case == 'estop' else
                     current.get('reason') in ('RECOVERY_LIMIT_REACHED', 'MISSION_TIMEOUT_180S')))
                result['validation_kind'] = 'negative_case_' + args.negative_case
            if args.negative_case == 'stop':
                stop_future = current.get('stop_future')
                result['stop_service_confirmed'] = bool(stop_future and stop_future.done() and stop_future.result().success)
                result['passed'] = result['passed'] and result['stop_service_confirmed']
            if args.negative_case == 'unreachable':
                result['passed'] = current['grasp'].startswith('FAULT_') and result['peak_lift_height_m'] < .005
                result['validation_kind'] = 'negative_case_unreachable'
            if not result['passed']:
                result['error'] = 'Terminal task state did not satisfy measured object movement'
            result['elapsed_s'] = round(time.monotonic() - started, 3)
            result['repetition'] = repetition + 1
            trial_results.append(json.loads(json.dumps(result)))
            (args.output / ('trial_%02d.json' % (repetition + 1))).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
            print('TRIAL_RESULT ' + json.dumps({k:result.get(k) for k in ['task','repetition','passed','elapsed_s','final_xyz','placement_error_m','peak_lift_height_m','home_error_rad','error']},ensure_ascii=False),flush=True)
            if not result['passed']:
                raise RuntimeError(result.get('error', 'Trial failed'))
    except (Exception, KeyboardInterrupt) as exc:
        result['error'] = str(exc) or type(exc).__name__
    finally:
        result['last_arm_positions'] = current.get('arm_positions')
        result['last_arm_velocities'] = current.get('arm_velocities')
        result['elapsed_s'] = round(time.monotonic() - started, 3)
        result.setdefault('final_xyz', current['pose'])
        if result['model_samples']:
            result.setdefault('maximum_z', max(sample['xyz'][2] for sample in result['model_samples']))
        if 'initial_xyz' in result and result['final_xyz'] is not None:
            result.setdefault('lift_height_m', result['final_xyz'][2] - result['initial_xyz'][2])
        result['process_exit_before_cleanup'] = {label: process.poll() for label, process in processes}
        for _, process in reversed(processes):
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 10.0
        while any(process.poll() is None for _, process in processes) and time.monotonic() < deadline:
            time.sleep(0.1)
        for _, process in reversed(processes):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        for handle in handles:
            handle.close()
        result['trial_results'] = trial_results
        result['requested_repetitions'] = args.repetitions
        result['group_elapsed_s'] = round(time.monotonic() - group_started, 3)
        result['passed'] = result['passed'] and len(trial_results) == args.repetitions and all(item['passed'] for item in trial_results)
        (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        print(json.dumps({key: value for key, value in result.items()
                          if key not in ('events', 'model_samples', 'trial_results')}, ensure_ascii=False), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
