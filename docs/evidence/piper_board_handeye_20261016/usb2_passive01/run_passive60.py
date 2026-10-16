"""Approved USB2-path 60s passive receive trial; no robot TX/control APIs."""
from pathlib import Path
import collections
import json
import os
import re
import socket
import struct
import subprocess
import time

ROOT=Path(__file__).resolve().parent
SDK=Path('/mnt/hgfs/ub/brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/collect_calibration_sdk.py')
report={'operator_quote':'已完成','authorization_commit':'1cf2bf9',
        'duration_requested_s':60,'robot_TX_or_control_commands':False,
        'USB_reset_module_reload_or_driver_started':False,'camera_started':False,
        'commands':[],'windows':[],'error':None}
sdk=None;log=None;receiver=None
def put(name,value):
    (ROOT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def run(argv):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=8)
    row={'argv':argv,'epoch':time.time(),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    report['commands'].append(row)
    if p.returncode:raise RuntimeError(str(row))
    return p.stdout
def state():return json.loads(run(['ip','-json','-details','-statistics','link','show','can0']))[0]
try:
    assert not (ROOT/'result.json').exists(), 'Do not overwrite evidence or repeat trial'
    report['before']=state()
    interface=Path('/sys/class/net/can0/device').resolve()
    device=interface.parent
    assert (device/'idVendor').read_text().strip()=='1d50'
    assert (device/'idProduct').read_text().strip()=='606f'
    assert (device/'serial').read_text().strip()=='003F001E5246570520323934'
    bus=next(p for p in interface.parents if re.fullmatch(r'usb\d+',p.name))
    controller=(bus.parent/'driver').resolve().name
    assert controller in ('uhci_hcd','ehci-pci','ehci_hcd'), 'USB2-route trial has not changed the controller'
    report['actual_USB_route']={'interface_sysfs':str(interface),'bus':bus.name,'host_controller_driver':controller,'same_expected_CAN_adapter':True}
    run(['lsusb','-t']);report['kernel_before']=run(['sudo','-n','dmesg','-T'])
    if 'UP' not in report['before']['flags']:
        for argv in (['sudo','-n','ip','link','set','can0','type','can','bitrate','1000000','sample-point','0.75'],['sudo','-n','ip','link','set','can0','txqueuelen','1000'],['sudo','-n','ip','link','set','can0','up']):run(argv)
    report['active_start']=state()
    receiver=socket.socket(socket.AF_CAN,socket.SOCK_RAW,socket.CAN_RAW)
    receiver.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1<<20)
    receiver.bind(('can0',));receiver.settimeout(.03)
    bins=[collections.Counter() for _ in range(60)]
    began=time.monotonic();report['receive_start_epoch']=time.time();last=None;maxgap=0.;total=0
    while time.monotonic()-began<60:
        elapsed=time.monotonic()-began
        if elapsed>=50 and sdk is None:
            log=(ROOT/'sdk.log').open('xb')
            sdk=subprocess.Popen(['/usr/bin/python3',str(SDK),'--output',str(ROOT/'sdk.json'),'--duration-s','6'],stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1'))
            report['SDK_invocation']={'pid':sdk.pid,'start_epoch':time.time(),'piper_init':False,'passive_original_tool':str(SDK)}
        try:data=receiver.recv(72)
        except socket.timeout:continue
        now=time.monotonic();elapsed=now-began
        if last is not None:maxgap=max(maxgap,now-last)
        last=now;total+=1
        if len(data)>=16:
            canid=struct.unpack_from('=I',data)[0]
            bins[min(int(elapsed),59)][hex(canid)]+=1
    report['receive_elapsed_s']=time.monotonic()-began
    report['received_frames']=total
    report['maximum_observed_interframe_gap_s']=maxgap
    report['trailing_no_frame_s']=time.monotonic()-last if last else report['receive_elapsed_s']
    report['windows']=[{'second':i+1,'frames':sum(c.values()),'IDs':dict(c)} for i,c in enumerate(bins)]
    report['new_frames_every_second']=all(sum(c.values())>0 for c in bins)
except BaseException as e:report['error']=repr(e)
finally:
    if receiver:receiver.close()
    if sdk is not None:
        try:sdk.wait(timeout=2)
        except subprocess.TimeoutExpired:
            sdk.terminate()
            try:sdk.wait(timeout=2)
            except subprocess.TimeoutExpired:sdk.kill();sdk.wait(timeout=2)
        report['SDK_exit_code']=sdk.returncode;log.close()
    try:
        report['after']=state();report['kernel_after']=run(['sudo','-n','dmesg','-T'])
        report['TX_packets_unchanged']=report['after']['stats64']['tx']['packets']==report.get('active_start',report['before'])['stats64']['tx']['packets']
    except BaseException as e:report['final_check_error']=repr(e)
    report['no_owned_receiver_or_SDK_left_running']=sdk is None or sdk.poll() is not None
    report['passive_trial_passed']=bool(report.get('receive_elapsed_s',0)>=60 and report.get('new_frames_every_second') and report.get('TX_packets_unchanged') and not report['error'])
    put('result.json',report)
print(json.dumps({k:report.get(k) for k in ('actual_USB_route','receive_elapsed_s','received_frames','new_frames_every_second','maximum_observed_interframe_gap_s','TX_packets_unchanged','SDK_exit_code','passive_trial_passed','error')},indent=2))
raise SystemExit(0 if report['passive_trial_passed'] else 2)
