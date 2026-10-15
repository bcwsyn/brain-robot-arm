"""Synthetic recorder regression tests only; never connect ROS/CAN/camera."""
import json
from pathlib import Path
from types import SimpleNamespace as Obj
import sys
import cv2
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).parent))
from native_depth_diagnostic import NativeDepthRecorder, checked_native_packet, encode_native_array


def header(seconds,frame='camera_depth_optical_frame'):
    sec=int(seconds)
    return Obj(stamp=Obj(sec=sec,nanosec=round((seconds-sec)*1e9)),frame_id=frame)


def messages(seconds=4.,q=None):
    depth=Obj(header=header(seconds),width=2,height=2,encoding='16UC1')
    info=Obj(header=header(seconds),width=2,height=2,k=[1.,0,1,0,1.,1,0,0,1],
             d=[0.]*5,r=[1.,0,0,0,1,0,0,0,1],p=[0.]*12,distortion_model='plumb_bob',
             binning_x=0,binning_y=0,roi=Obj(x_offset=0,y_offset=0,height=0,width=0,do_rectify=False))
    feedback=Obj(header=header(seconds,''),name=[f'joint{i}' for i in range(1,7)],
                 position=q or [0.]*6,velocity=[0.]*6,effort=[])
    return depth,info,feedback


def recorder(tmp_path):
    pixels=np.array([[0,217],[0,242]],dtype=np.uint16)
    rec=NativeDepthRecorder(tmp_path/'native',encoder=lambda _:encode_native_array(pixels,2,2))
    for second in (1,2,3,4):
        rec.receive('feedback',messages(second)[2],second*10**9,float(second))
    return rec,pixels


@pytest.mark.parametrize('order',[('depth','info'),('info','depth')])
def test_saves_without_any_rgb_and_preserves_raw_zeros(tmp_path,order):
    rec,pixels=recorder(tmp_path)
    depth,info,_=messages()
    for name in order:
        rec.receive(name,depth if name=='depth' else info,4*10**9,4.)
    rec.finish()
    saved=cv2.imread(str(tmp_path/'native/evidence/0001_depth.png'),cv2.IMREAD_UNCHANGED)
    assert np.array_equal(saved,pixels) and saved.dtype==np.uint16
    row=json.loads((tmp_path/'native/observer.jsonl').read_text())
    assert row['diagnostic_only'] and row['stamps_ns']['depth']==row['stamps_ns']['depth_info']
    assert row['depth_info']['k']==info.k and row['feedback']['raw_positions']==[0.]*6
    ready=json.loads((tmp_path/'native/ready.json').read_text())
    assert ready['stamps_ns']['depth']==ready['stamps_ns']['depth_info']


def test_mismatched_info_is_never_substituted(tmp_path):
    rec,_=recorder(tmp_path)
    rec.receive('depth',messages(4.)[0],4*10**9,4.)
    rec.receive('info',messages(4.01)[1],4_010_000_000,4.01)
    assert rec.finish()['saved_frames']==0
    assert not (tmp_path/'native/ready.json').exists()


@pytest.mark.parametrize('mutation,reason',[
    ('stamp','depth_info_not_same_stamp'),('frame','depth_Info_frame_or_size_mismatch'),
    ('encoding','invalid_native_depth_format'),('intrinsics','invalid_native_intrinsics')])
def test_bad_native_packets_rejected(mutation,reason):
    d,i,f=messages()
    if mutation=='stamp':i.header=header(4.01)
    elif mutation=='frame':i.header.frame_id='wrong'
    elif mutation=='encoding':d.encoding='32FC1'
    else:i.k[0]=0
    with pytest.raises(ValueError,match=reason):
        checked_native_packet(d,i,f,4_020_000_000)


def test_stale_and_future_feedback_not_refreshed_by_observer_time():
    d,i,f=messages()
    with pytest.raises(ValueError,match='stale_or_future_input'):
        checked_native_packet(d,i,f,5_000_000_000)
    with pytest.raises(ValueError,match='stale_or_future_input'):
        checked_native_packet(d,i,f,3_999_000_000)


def test_float_depth_not_guessed_or_converted():
    with pytest.raises(ValueError,match='dtype_or_shape'):
        encode_native_array(np.zeros((2,2),dtype=np.float32),2,2)


def test_cache_and_capacity_are_bounded(tmp_path):
    rec,_=recorder(tmp_path)
    for number in range(100):
        second=5+number*.01
        rec.receive('depth',messages(second)[0],round(second*1e9),second)
    assert len(rec.depths)==64 and len(rec.infos)==0
    rec.finish()


def test_image_capacity_stops_diagnostic_not_motion(tmp_path):
    rec,_=recorder(tmp_path)
    rec.summary['max_image_bytes']=1
    d,i,_=messages()
    rec.receive('depth',d,4*10**9,4.)
    rec.receive('info',i,4*10**9,4.)
    summary=rec.finish()
    assert summary['saved_frames']==0 and summary['stop_reason']=='diagnostic_image_budget_exhausted'
    assert not list((tmp_path/'native/evidence').iterdir())


def test_existing_output_not_overwritten(tmp_path):
    output=tmp_path/'existing';output.mkdir()
    with pytest.raises(FileExistsError):NativeDepthRecorder(output)


def test_native_frame_limit_does_not_require_rgb(tmp_path):
    rec,_=recorder(tmp_path)
    rec.summary['saved_frames']=60
    d,i,_=messages()
    rec.receive('depth',d,4*10**9,4.)
    rec.receive('info',i,4*10**9,4.)
    assert rec.finish()['saved_frames']==60
    assert not list((tmp_path/'native/evidence').iterdir())


def test_ignores_duplicate_feedback_and_stops_on_original_feedback_loss(tmp_path):
    rec,_=recorder(tmp_path)
    rec.receive('feedback',messages(4.)[2],4*10**9,4.)
    assert len(rec.history)==4
    assert rec.lost(4_600_000_000,5.)
    assert not rec.lost(4_100_000_000,5.)
    rec.finish()
