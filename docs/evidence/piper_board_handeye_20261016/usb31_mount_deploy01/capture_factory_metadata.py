"""One-off bounded read-only camera metadata capture; no arm interfaces."""
import json
from pathlib import Path
import sys
import time
import rclpy
from rosidl_runtime_py.convert import message_to_ordereddict
from astra_camera_msgs.srv import GetCameraInfo, GetCameraParams, GetDeviceInfo
from tf2_ros import Buffer, TransformListener

output = Path(sys.argv[1])
if output.exists():
    raise FileExistsError(output)
rclpy.init()
node = rclpy.create_node('calibration_camera_factory_readonly')
buffer = Buffer()
listener = TransformListener(buffer, node)
result = {'read_epoch': time.time(), 'read_only': True, 'motion_commands_sent': False}
try:
    for label, kind in [('get_device_info', GetDeviceInfo), ('get_camera_info', GetCameraInfo),
                        ('get_camera_params', GetCameraParams)]:
        client = node.create_client(kind, '/camera/' + label)
        if not client.wait_for_service(timeout_sec=6.):
            raise RuntimeError('Missing read-only service ' + label)
        future = client.call_async(kind.Request())
        rclpy.spin_until_future_complete(node, future, timeout_sec=3.)
        if not future.done() or future.result() is None:
            raise RuntimeError('Timed out ' + label)
        response = future.result()
        if not response.success:
            raise RuntimeError('Read-only camera query failed: ' + label)
        result[label] = message_to_ordereddict(response)
    deadline = time.monotonic() + 4.
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=.05)
        if buffer.can_transform('camera_link', 'camera_depth_optical_frame', rclpy.time.Time()):
            transform = buffer.lookup_transform('camera_link', 'camera_depth_optical_frame', rclpy.time.Time())
            result['camera_link_from_depth_optical'] = message_to_ordereddict(transform)
            result['internal_tf_scope'] = 'Latest camera-internal transform only; not image-time robot mounting TF'
            break
    if 'camera_link_from_depth_optical' not in result:
        raise RuntimeError('Missing camera-internal optical TF')
except Exception as error:
    result['error'] = repr(error)
finally:
    node.destroy_node()
    rclpy.shutdown()
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
print(json.dumps({'complete': 'error' not in result, 'serial': result.get('get_device_info', {}).get('info', {}).get('serial_number'),
                  'internal_tf_captured': 'camera_link_from_depth_optical' in result, 'error': result.get('error')}))
raise SystemExit(2 if 'error' in result else 0)
