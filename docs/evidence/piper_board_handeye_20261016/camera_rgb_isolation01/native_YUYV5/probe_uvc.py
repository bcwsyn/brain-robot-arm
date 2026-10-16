"""One bounded native YUYV 320x240@5 capture, then restore exact prior mode."""
from pathlib import Path
import hashlib,json,os,re,signal,subprocess,time

ROOT=Path(__file__).resolve().parent
r={'baseline_commit':'ba08b62','scope':'Native UVC read-frame diagnostic only; no ROS, depth, motion or exposure changes',
   'commands':[],'camera_mode_restored':False,'error':None}
def run(argv):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=5)
    r['commands'].append({'argv':argv,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'epoch':time.time()})
    if p.returncode:raise RuntimeError(str(argv)+': '+p.stderr)
    return p.stdout
def can():return json.loads(run(['ip','-json','-details','-statistics','link','show','can0']))[0]
p=None;log=None;restore=None
try:
    before=can();text=run(['v4l2-ctl','-d','/dev/video0','--get-fmt-video','--get-parm'])
    wh=re.search(r'Width/Height\s*:\s*(\d+)/(\d+)',text)
    fmt=re.search(r"Pixel Format\s*:\s*'([A-Z0-9]+)'",text)
    fps=re.search(r'Frames per second\s*:\s*([\d.]+)',text)
    assert wh and fmt and fps and fmt[1] in ['YUYV','MJPG']
    restore=['v4l2-ctl','-d','/dev/video0',f'--set-fmt-video=width={int(wh[1])},height={int(wh[2])},pixelformat={fmt[1]}',f'--set-parm={float(fps[1])}']
    argv=['v4l2-ctl','-d','/dev/video0','--set-fmt-video=width=320,height=240,pixelformat=YUYV',
          '--set-parm=5','--verbose','--stream-mmap=3','--stream-poll','--stream-count=3','--stream-to='+str(ROOT/'frames.YUYV')]
    log=(ROOT/'v4l2_stream.log').open('xb')
    p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    r['capture_argv']=argv;began=time.monotonic()
    try:p.wait(timeout=8)
    except subprocess.TimeoutExpired:
        r['capture_timeout']=True;os.killpg(p.pid,signal.SIGINT)
        try:p.wait(timeout=1)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=1)
    r['capture_elapsed_s']=time.monotonic()-began;r['capture_rc']=p.returncode;log.close();log=None
    r['configured_mode_readback']=run(['v4l2-ctl','-d','/dev/video0','--get-fmt-video','--get-parm'])
    data=(ROOT/'frames.YUYV').read_bytes() if (ROOT/'frames.YUYV').exists() else b''
    r['raw_bytes']=len(data);r['complete_320x240_YUYV_frames']=len(data)//(320*240*2)
    if len(data)>=320*240*2:
        import cv2,numpy as np
        rgb=cv2.cvtColor(np.frombuffer(data[:320*240*2],dtype=np.uint8).reshape(240,320,2),cv2.COLOR_YUV2BGR_YUY2)
        assert cv2.imwrite(str(ROOT/'first_RGB.png'),rgb)
        r['first_RGB_SHA256']=hashlib.sha256((ROOT/'first_RGB.png').read_bytes()).hexdigest()
except BaseException as e:r['error']=repr(e)
finally:
    if p is not None and p.poll() is None:
        os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
    if log is not None:log.close()
    if restore is not None:
        try:
            run(restore);r['restored_mode_readback']=run(['v4l2-ctl','-d','/dev/video0','--get-fmt-video','--get-parm']);r['camera_mode_restored']=True
        except BaseException as e:r['restore_error']=repr(e)
    after=can();r['TX_unchanged']=before['stats64']['tx']['packets']==after['stats64']['tx']['packets']
    r['all_owned_sources_exited']=p is None or p.poll() is not None
    (ROOT/'native_probe.json').write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:r.get(k) for k in ['raw_bytes','complete_320x240_YUYV_frames','capture_rc','capture_timeout','camera_mode_restored','TX_unchanged','error']}))
