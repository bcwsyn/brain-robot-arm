"""Save at most six genuine original color messages in a bounded diagnostic."""
import hashlib,json,sys,time
from pathlib import Path
import cv2,numpy as np,rclpy
from sensor_msgs.msg import Image
ROOT=Path(sys.argv[1]);rows=[]
rclpy.init();node=rclpy.create_node('bounded_color_only_receiver')
def receive(m):
    if len(rows)>=6:return
    raw=np.frombuffer(bytes(m.data),np.uint8).reshape(m.height,m.step)[:,:m.width*3].reshape(m.height,m.width,3)
    if m.encoding=='rgb8':raw=cv2.cvtColor(raw,cv2.COLOR_RGB2BGR)
    path=ROOT/f'{len(rows)+1:04d}_rgb.png';assert not path.exists();assert cv2.imwrite(str(path),raw)
    rows.append({'stamp_ns':m.header.stamp.sec*10**9+m.header.stamp.nanosec,
        'frame':m.header.frame_id,'encoding':m.encoding,'size':[m.width,m.height],
        'path':str(path),'SHA256':hashlib.sha256(path.read_bytes()).hexdigest()})
node.create_subscription(Image,'/camera/color/image_raw',receive,10)
with (ROOT/'listening.json').open('x') as f:json.dump({'listening':True},f)
end=time.monotonic()+10
try:
    while rclpy.ok() and time.monotonic()<end and len(rows)<6:rclpy.spin_once(node,timeout_sec=.05)
finally:
    node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
    with (ROOT/'color_result.json').open('x') as f:json.dump({'rows':rows,'frames':len(rows)},f,indent=2)
raise SystemExit(0 if len(rows)==6 else 2)
