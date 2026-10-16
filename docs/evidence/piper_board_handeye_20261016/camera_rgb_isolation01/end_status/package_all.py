"""Offline package of distinct bounded RGB probes and one exact camera reset."""
from pathlib import Path
import ast,hashlib,json,shutil,tarfile

ROOT=Path(__file__).resolve().parent
REPO=Path('/mnt/hgfs/ub')
OUT=REPO/'docs/evidence/piper_board_handeye_20261016/camera_rgb_isolation01'
sources={'original_RGB_only':Path('/home/johnwick/brain_robot_logs/rgb_startup_20261016.Lvktgg'),
         'V4L2_preferred_RGB_only':Path('/home/johnwick/brain_robot_logs/rgb_v4l2_20261016.OLU0C4'),
         'native_YUYV5':Path('/home/johnwick/brain_robot_logs/uvc_low_rate_20261016.OPAuCw'),
         'one_RGB_USB_reset':Path('/home/johnwick/brain_robot_logs/rgb_reset_once_20261016.Oc3wQe'),
         'end_status':ROOT}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
orig=load(sources['original_RGB_only']/'probe_result.json')
v4l=load(sources['V4L2_preferred_RGB_only']/'probe_result.json')
native=load(sources['native_YUYV5']/'native_probe.json')
reset=load(sources['one_RGB_USB_reset']/'RGB_reset.json')
post=load(sources['one_RGB_USB_reset']/'native_probe.json')
final=load(ROOT/'final_status.json');sdk=load(ROOT/'SDK_final.json')
fresh=[s for s in sdk['samples'] if s['fresh_after_passive_connection']]
assert not orig['frames'] and not v4l['frames']
assert all(s['TX_unchanged'] and s['all_owned_sources_exited'] for s in [orig,v4l,native,post])
assert native['raw_bytes']==post['raw_bytes']==0 and native['camera_mode_restored'] and post['camera_mode_restored']
assert reset['reset_ioctl_rc']==0 and reset['error'] is None
assert not final['robot_or_camera_sources'] and fresh and all(fresh[-1]['enabled'])
frozen=load(REPO/'docs/evidence/piper_board_handeye_20261016/usb2_observe01/production_SHA_after.json')
assert all(sha(Path(p))==v for p,v in frozen.items())
can=json.loads(next(c['stdout'] for c in final['commands'] if c['argv'][0]=='ip'))[0]
assessment={'baseline_commit':'ba08b62','operator_instruction':'自主完成，仅真正需要实机操作时再叫用户',
    'original_RGB_only':{'requested_s':8,'frames':0,'source_cleanup_exit_code':orig['source_exit_code']},
    'GStreamer_disabled_only_in_capture_process':{'requested_s':8,'frames':0,'source_cleanup_exit_code':v4l['source_exit_code'],'production_or_shell_environment_changed':False},
    'native_YUYV_320x240_sensor_5fps':{'raw_bytes':0,'capture_rc':native['capture_rc'],'mode_restored':True},
    'one_exact_RGB_reset':{'target':reset['target'],'vendor_product':reset['target_vendor_product'],'serial':reset['expected_serial'],'ioctl_rc':0,'CAN_device_touched':False},
    'native_after_reset':{'raw_bytes':0,'capture_rc':post['capture_rc'],'mode_restored':True},
    'empty_stream_file_is_not_a_valid_black_image_or_success':True,
    'state_of_knowledge':'The guest enumerates RGB correctly but obtains no complete frames through original ROS, V4L2-preferred ROS, or native low-rate UVC, with depth stopped. Backend/ROS and sensor-rate alternatives did not restore frames. Exact RGB USB reset returned success but did not fix this.',
    'cleanup_warning_caveat':'Original GStreamer warnings and V4L2 EBUSY were logged after the bounded SIGINT cleanup; do not claim they prove a pre-existing conflict or that GStreamer alone is the root cause.',
    'official_primary_sources':[
        {'url':'https://raw.githubusercontent.com/ros2/demos/humble/image_tools/src/cam2image.cpp','fact':'cap.open precedes width/height configuration; frequency governs publication timer, not a CAP_PROP_FPS setter.'},
        {'url':'https://raw.githubusercontent.com/opencv/opencv/4.5.4/modules/videoio/src/videoio_registry.cpp','fact':'Per-backend priority zero disables that backend; used only in the bounded diagnostic child, and did not restore frames.'}],
    'production_six_SHA_unchanged':True,'CAN_final':can,'final_passive_SDK_exit_code':final['passive_SDK']['rc'],
    'final_passive_SDK_whole_quality':sdk['quality'],'last_fresh_SDK_not_continuous_monitoring':fresh[-1],
    'all_control_and_capture_sources_exited':True,'robot_TX_stayed_9974':can['stats64']['tx']['packets']==9974,
    'final_UVC_mode_readback':final['commands'][-1]['stdout'],
    'no_robot_enable_disable_reset_gripper_or_motion_after_observation':True,
    'camera_exposure_gains_TF_detector_gates_or_VM_compatibility_changed':False,
    'raw_data_or_firmware_deleted_or_modified':False,
    'next_required_external_observation':'On Windows host, disconnect only Orbbec/Dabai RGB 2bc5:0557 from this VM to host, open Windows Camera and select Dabai DC1, report whether a live color image appears, then close the app and reconnect only RGB to this VM. Leave depth, CAN, USB compatibility, arm and board unchanged.',
    'why_external':'Guest-side stream alternatives and one precise reset did not restore frames; native host RGB reception is not observable or controllable from this Ubuntu session. Host test distinguishes camera/host reception from VM passthrough without guessing a new controller setting.',
    'not_established':'No proof of hardware failure or USB2 incompatibility, and no proof which host/guest/UVC transport layer loses image data. Do not repeatedly reset or reopen identical captures.',
    'calibration':'Observation return succeeded; no new images/board reference, old candidates 2/10 unchanged. Production TF/approach/gates remain frozen.',
    'Git_sync':'Local only; existing divergent-main/history-review/publication-scope blocker unchanged.'}
OUT.mkdir(exist_ok=False);put(OUT/'assessment.json',assessment);put(OUT/'production_SHA_after.json',frozen)
files=[(label,p,p.relative_to(directory)) for label,directory in sources.items() for p in sorted(directory.rglob('*')) if p.is_file()]
for _,p,_ in files:
    if p.suffix=='.py':ast.parse(p.read_text())
archive=OUT/'runtime_originals.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for label,p,relative in files:t.add(p,arcname=str(Path(label)/relative),recursive=False)
with tarfile.open(archive,'r:gz') as t:
    for label,p,relative in files:assert hashlib.sha256(t.extractfile(str(Path(label)/relative)).read()).hexdigest()==sha(p)
put(OUT/'runtime_manifest.json',{'archive':archive.name,'SHA256':sha(archive),
    'files':[{'path':str(Path(label)/relative),'bytes':p.stat().st_size,'SHA256':sha(p)} for label,p,relative in files],
    'all_member_SHA_readback_verified':True})
for label,p,relative in files:
    if p.suffix in ('.py','.json'):
        dest=OUT/label/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
print(json.dumps({'files':len(files),'archive_bytes':archive.stat().st_size,'CAN_TX':can['stats64']['tx']['packets'],'SDK_fresh':len(fresh),'six_enabled':fresh[-1]['enabled'],'RGB_frames':0,'all_sources_exited':True}))
