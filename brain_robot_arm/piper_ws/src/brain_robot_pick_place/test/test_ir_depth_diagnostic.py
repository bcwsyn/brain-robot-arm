"""Offline IR-only additions must preserve original depth recording behavior."""
import ast
import json
from pathlib import Path
import cv2
import numpy as np
import pytest

from test_native_depth_diagnostic import messages
from native_depth_diagnostic import NativeDepthRecorder, checked_native_packet, encode_ir_array
from collect_ir_depth_diagnostic import validate, deliver_feedback, process_ready_then_feedback_lost, result_code
from types import SimpleNamespace as Obj


def test_ir_untouched_pixels_and_original_static_rule(tmp_path):
    pixels=np.array([[0,255],[30,200]],dtype=np.uint8)
    rec=NativeDepthRecorder(tmp_path/'ir',encoder=lambda _:encode_ir_array(pixels,2,2),stream_kind='ir')
    for second in (1,2,3,4):
        rec.receive('feedback',messages(second)[2],second*10**9,float(second))
    d,i,_=messages();d.encoding='mono8'
    d.header.frame_id=i.header.frame_id='camera_ir_optical_frame'
    rec.receive('ir',d,4*10**9,4.)
    rec.receive('info',i,4*10**9,4.)
    assert rec.finish()['saved_frames']==1
    saved=cv2.imread(str(tmp_path/'ir/evidence/0001_ir.png'),cv2.IMREAD_UNCHANGED)
    assert saved.dtype==np.uint8 and np.array_equal(saved,pixels)
    row=json.loads((tmp_path/'ir/observer.jsonl').read_text())
    assert row['stamps_ns']['ir']==row['stamps_ns']['ir_info']
    assert 'depth' not in row['images'] and 'ir_info' in row
    assert row['images']['ir']['frame']=='camera_ir_optical_frame'


def test_ir_never_reinterprets_depth_or_guesses_float_format():
    d,i,f=messages()
    with pytest.raises(ValueError):checked_native_packet(d,i,f,4*10**9,'ir')
    d.encoding='mono8'
    with pytest.raises(ValueError):checked_native_packet(d,i,f,4*10**9)
    with pytest.raises(ValueError):encode_ir_array(np.zeros((2,2),dtype=np.uint16),2,2)


@pytest.mark.parametrize('duration',[0,27,float('nan'),float('inf')])
def test_bounds_before_ros(tmp_path,duration):
    with pytest.raises(ValueError):validate(tmp_path/'new',duration)


def test_no_overwrite_before_ros(tmp_path):
    with pytest.raises(FileExistsError):validate(tmp_path,24.)


def test_passive_observer_has_no_publishers_or_service_calls():
    source=(Path(__file__).parent/'collect_ir_depth_diagnostic.py').read_text()
    attrs={n.attr for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Attribute)}
    assert not attrs & {'create_client','create_publisher','call_async','publish'}


def test_one_feedback_callback_distributes_exact_original_message():
    rows=[]
    recorders={kind:Obj(receive=lambda *args,kind=kind:rows.append((kind,args))) for kind in ('depth','ir')}
    message=object()
    deliver_feedback(recorders,message,42,1.5)
    assert rows==[(kind,('feedback',message,42,1.5)) for kind in ('depth','ir')]


@pytest.mark.parametrize('fresh_callback_ready',[True,False])
def test_pending_callback_drained_but_genuine_loss_still_stops(fresh_callback_ready):
    state={'stamp':1.,'spins':0}
    now_ns=2_000_000_000
    node=Obj(get_clock=lambda:Obj(now=lambda:Obj(nanoseconds=now_ns)))
    def spin_once(node,timeout_sec):
        assert timeout_sec==0.
        state['spins']+=1
        if fresh_callback_ready and state['spins']==1:state['stamp']=1.95
    rec=Obj(lost=lambda ns,elapsed: ns/1e9-state['stamp']>.5)
    assert process_ready_then_feedback_lost(node,{'depth':rec,'ir':rec},4.,spin_once)==(not fresh_callback_ready)
    assert state['spins']==32


@pytest.mark.parametrize('reason,frames,expected',[(None,4,0),('feedback_lost_original_500ms_rule',4,2),(None,0,2)])
def test_partial_images_never_hide_feedback_stop(reason,frames,expected):
    report={'error':None,'stop_reason':reason,'streams':{k:{'saved_frames':frames,'stop_reason':None} for k in ('ir','depth')}}
    assert result_code(report)==expected
