#!/usr/bin/env python3
"""Diagnostic-only native depth/Info/real-feedback storage, independent of RGB.

No ROS graph/device imports until encoding an actual message. Does not change
formal RGB-D acquisition, registration, quality or physical motion decisions.
"""
from collections import Counter, deque
import hashlib
import json
import math
from pathlib import Path

from collect_static_rgbd import (stamp_ns, joint_positions, settled_feedback,
                                full_camera_info, feedback_lost, SLOP_NS, MAX_AGE_NS)

TOPICS = ('/camera/depth/image_raw', '/camera/depth/camera_info', '/joint_states_feedback')


def checked_native_packet(depth, info, feedback, now_ns):
    stamps = [stamp_ns(m) for m in (depth, info, feedback)]
    if stamps[0] != stamps[1]:
        raise ValueError('depth_info_not_same_stamp')
    if max(stamps)-min(stamps) > SLOP_NS:
        raise ValueError('feedback_span_exceeds_original_120ms')
    if max(stamps) > now_ns or now_ns-min(stamps) > MAX_AGE_NS:
        raise ValueError('stale_or_future_input')
    if depth.header.frame_id != info.header.frame_id or (depth.width,depth.height)!=(info.width,info.height):
        raise ValueError('depth_Info_frame_or_size_mismatch')
    if depth.width <= 0 or depth.height <= 0 or depth.encoding not in ('16UC1','mono16'):
        raise ValueError('invalid_native_depth_format')
    if len(info.k)!=9 or not all(math.isfinite(x) for x in info.k) or info.k[0]<=0 or info.k[4]<=0:
        raise ValueError('invalid_native_intrinsics')
    return {'stamps_ns':dict(zip(('depth','depth_info','feedback'),map(str,stamps))),
            'stamp_span_s':(max(stamps)-min(stamps))/1e9,'oldest_age_s':(now_ns-min(stamps))/1e9,
            'q_rad':joint_positions(feedback)}


def encode_native_array(image, width, height):
    import cv2
    import numpy as np
    if image.dtype!=np.uint16 or image.shape!=(height,width):
        raise ValueError('passthrough_depth_dtype_or_shape_mismatch')
    ok, encoded=cv2.imencode('.png',image)
    if not ok:
        raise RuntimeError('native_depth_png_encoding_failed')
    return encoded.tobytes()


def encode_message(message):
    from cv_bridge import CvBridge
    image=CvBridge().imgmsg_to_cv2(message,'passthrough')
    return encode_native_array(image,message.width,message.height)


class NativeDepthRecorder:
    def __init__(self, output, encoder=encode_message):
        self.output=Path(output)
        self.output.mkdir(exist_ok=False)
        (self.output/'evidence').mkdir()
        self.stream=(self.output/'observer.jsonl').open('x')
        self.encoder=encoder
        self.depths,self.infos={},{}
        self.history=deque(maxlen=1000)
        self.feedback=None
        self.last_saved_ns=0
        self.start_q=None
        self.summary={'schema':'piper_native_depth_diagnostic_v1','diagnostic_only':True,
                      'formal_calibration_pair':False,'RGB_required':False,
                      'motion_commands_sent':False,'topics':list(TOPICS),'max_frames':60,
                      'interval_s':.5,'max_image_bytes':32<<20,'cache_per_topic_limit':64,
                      'static_window_s':3.,'same_stamp_depth_Info':True,
                      'hardware_synchronized':False,'saved_frames':0,'image_bytes':0,
                      'received':Counter(),'rejected':Counter(),'stop_reason':None,
                      'first_received_pair':None}

    def receive(self, kind, message, now_ns, epoch):
        self.summary['received'][kind]+=1
        try:
            stamp=stamp_ns(message)
            if kind=='feedback':
                q=joint_positions(message)
                if self.history and stamp<=self.history[-1][0]:
                    raise ValueError('duplicate_or_out_of_order_feedback')
                self.history.append((stamp,q))
                self.feedback=message
                return
            cache=self.depths if kind=='depth' else self.infos
            cache[stamp]=message
            while len(cache)>64:
                del cache[min(cache)]
                self.summary['rejected'][kind+'_cache_eviction']+=1
            if stamp not in self.depths or stamp not in self.infos or self.feedback is None:
                return
            depth,info=self.depths.pop(stamp),self.infos.pop(stamp)
            if self.summary['stop_reason'] or self.summary['saved_frames']>=60 or stamp-self.last_saved_ns<500_000_000:
                return
            packet=checked_native_packet(depth,info,self.feedback,now_ns)
            if self.summary['first_received_pair'] is None:
                first={'epoch':epoch,'stamps_ns':packet['stamps_ns'],
                       'depth_frame':depth.header.frame_id,'depth_size':[depth.width,depth.height],
                       'scope':'Actual depth+same-stamp Info+fresh feedback received; not top quality or calibration acceptance'}
                with (self.output/'ready.json').open('x') as stream:
                    json.dump(first,stream,indent=2,allow_nan=False)
                self.summary['first_received_pair']=first
            if not settled_feedback(self.history,packet['q_rad'],stamp_ns(self.feedback),3.):
                raise ValueError('feedback_not_settled_for_original_3s')
            if self.start_q is not None and any(abs(a-b)>.001 for a,b in zip(packet['q_rad'],self.start_q)):
                self.summary['stop_reason']='actual_static_pose_changed'
                return
            encoded=self.encoder(depth)
            if self.summary['image_bytes']+len(encoded)>self.summary['max_image_bytes']:
                self.summary['stop_reason']='diagnostic_image_budget_exhausted'
                return
            number=self.summary['saved_frames']+1
            relative=f'evidence/{number:04d}_depth.png'
            with (self.output/relative).open('xb') as stream:
                stream.write(encoded)
            fb=self.feedback
            row={'epoch':epoch,'snapshot':number,'diagnostic_only':True,
                 'timestamp_paired_not_hardware_sync':True,**packet,
                 'depth_info':full_camera_info(info),
                 'feedback':{'raw_names':list(fb.name),'raw_positions':list(fb.position),
                             'raw_velocity':list(fb.velocity),'raw_effort':list(fb.effort),
                             'frame':fb.header.frame_id},
                 'images':{'depth':{'path':relative,'sha256':hashlib.sha256(encoded).hexdigest(),
                                    'source_encoding':depth.encoding,'frame':depth.header.frame_id,
                                    'size':[depth.width,depth.height]}}}
            self.stream.write(json.dumps(row,allow_nan=False)+'\n');self.stream.flush()
            self.summary['saved_frames']=number
            self.summary['image_bytes']+=len(encoded)
            self.last_saved_ns=stamp
            self.start_q=packet['q_rad']
        except (ValueError,KeyError) as exc:
            self.summary['rejected'][str(exc)]+=1

    def lost(self,now_ns,elapsed_s):
        return feedback_lost(self.history,now_ns,elapsed_s)

    def finish(self):
        self.stream.close()
        self.summary['unmatched_cached_depths']=len(self.depths)
        self.summary['unmatched_cached_Info']=len(self.infos)
        with (self.output/'summary.json').open('x') as stream:
            json.dump(self.summary,stream,indent=2,allow_nan=False)
        return self.summary
