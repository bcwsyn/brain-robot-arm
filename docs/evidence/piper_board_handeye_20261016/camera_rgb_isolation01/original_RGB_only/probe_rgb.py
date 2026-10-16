"""One bounded RGB-only original-source probe with syscall evidence; no setters."""
from pathlib import Path
import hashlib,json,os,signal,subprocess,time
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2

ROOT=Path(__file__).resolve().parent
report={'baseline_commit':'ba08b62','role':'RGB_only_original_cam2image_8s',
        'motion_commands':False,'camera_setters':False,'depth_started':False,'commands':[],
        'frames':[],'error':None}
def read(argv):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=6)
    report['commands'].append({'argv':argv,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'epoch':time.time()})
    return p.stdout
def can():return json.loads(read(['ip','-json','-details','-statistics','link','show','can0']))[0]
before=can()
read(['v4l2-ctl','--device','/dev/video0','--all','--list-formats-ext'])
read(['dpkg-query','-W','ros-humble-image-tools'])
report['kernel_before']=read(['sudo','-n','dmesg','-T'])
rclpy.init();node=rclpy.create_node('readonly_original_RGB_startup_probe');bridge=CvBridge()
def image(msg):
    index=len(report['frames']);row={'receipt_epoch':time.time(),'stamp_ns':msg.header.stamp.sec*10**9+msg.header.stamp.nanosec,
        'width':msg.width,'height':msg.height,'encoding':msg.encoding,'frame_id':msg.header.frame_id}
    if index<3:
        rgb=bridge.imgmsg_to_cv2(msg,'bgr8');dest=ROOT/f'RGB_{index:02d}.png'
        assert cv2.imwrite(str(dest),rgb)
        row.update(image=dest.name,SHA256=hashlib.sha256(dest.read_bytes()).hexdigest())
    report['frames'].append(row)
node.create_subscription(Image,'/camera/color/image_raw',image,qos_profile_sensor_data)
argv=['strace','-f','-tt','-e','trace=ioctl,openat,poll,ppoll,select,pselect6','-o',str(ROOT/'original_cam2image.strace'),
      '/opt/ros/humble/lib/image_tools/cam2image','--ros-args','-p','burger_mode:=false','-p','device_id:=0',
      '-p','frequency:=5.0','-p','width:=320','-p','height:=240','-p','frame_id:=camera_color_optical_frame','-r','image:=/camera/color/image_raw']
log=(ROOT/'original_cam2image.log').open('xb');p=None
try:
    p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    report['source']={'argv':argv,'pid':p.pid,'epoch':time.time()}
    began=time.monotonic()
    while time.monotonic()-began<8 and p.poll() is None:rclpy.spin_once(node,timeout_sec=.02)
    report['elapsed_s']=time.monotonic()-began
except BaseException as e:report['error']=repr(e)
finally:
    if p is not None and p.poll() is None:
        os.killpg(p.pid,signal.SIGINT)
        try:p.wait(timeout=2)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
    log.close();report['source_exit_code']=None if p is None else p.returncode
    report['all_owned_sources_exited']=p is None or p.poll() is not None
    node.destroy_node()
    if rclpy.ok():rclpy.shutdown()
    read(['v4l2-ctl','--device','/dev/video0','--get-fmt-video','--get-parm'])
    after=can();report['TX_unchanged']=before['stats64']['tx']['packets']==after['stats64']['tx']['packets']
    report['kernel_after']=read(['sudo','-n','dmesg','-T'])
    (ROOT/'probe_result.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'frames':len(report['frames']),'error':report['error'],'TX_unchanged':report['TX_unchanged'],'all_owned_sources_exited':report['all_owned_sources_exited']}))
