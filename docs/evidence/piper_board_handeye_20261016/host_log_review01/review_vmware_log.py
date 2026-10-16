"""Offline VMware log review: allowlisted output, no device/control APIs.

Raw input is never copied into the report. ISO Z timestamps mean UTC.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

LOCAL=timezone(timedelta(hours=8))
START=datetime(2026,10,16,5,22,tzinfo=timezone.utc)
END=datetime(2026,10,16,5,25,tzinfo=timezone.utc)
IDS={'1d50606f':'USB-CAN','2bc50557':'RGB','2bc50657':'depth'}

def review(raw):
    lines=raw.decode('utf-8-sig').splitlines()
    parsed=[];config=[];events=[];paths=[];previous={}
    version=None;hyper_v=False;mode=None
    for index,line in enumerate(lines,1):
        m=re.match(r'(\d{4}-\d\d-\d\dT[\d:.]+Z)\s',line)
        if not m:continue
        stamp=datetime.fromisoformat(m[1].replace('Z','+00:00'))
        row={'source_line':index,'source_line_SHA256':hashlib.sha256(line.encode()).hexdigest(),
             'UTC':stamp.isoformat(),'local_UTC_plus8':stamp.astimezone(LOCAL).isoformat()}
        parsed.append((stamp,row))
        v=re.search(r'Log for VMware Workstation .*?version=([\d.]+) build=build-(\d+)',line)
        if v:version={'version':v[1],'build':v[2]}
        hyper_v=hyper_v or 'Hyper-V detected by CPUID' in line
        m=re.search(r'Monitor Mode: (ULM|CPL0)',line)
        if m:mode=m[1]
        m=re.search(r'\b(usb\.present|ehci\.present|usb_xhci\.present)\s*=\s*"(TRUE|FALSE)"',line)
        if m:config.append(dict(row,key=m[1],value=m[2]))
        product=None
        d=re.search(r'DevID\(([0-9a-fA-F]+)\)',line)
        if d:product=IDS.get(d[1][-8:].lower())
        f=re.search(r'vid:([0-9a-fA-F]{4}) pid:([0-9a-fA-F]{4}) path:([\d/]+) speed:([a-z]+)',line)
        if f:
            product=IDS.get((f[1]+f[2]).lower())
            if product:
                virtual=re.search(r'virtPath:(usb_xhci:\d+)',line)
                connected=re.search(r'connected to (usb_xhci:\d+) port (\d+)',line)
                value={'host_path':f[3],'speed':f[4],
                       'virtual_path':virtual[1] if virtual else None,
                       'connected_virtual_hub':connected[1] if connected else None,
                       'connected_virtual_port':int(connected[2]) if connected else None}
                if value!=previous.get(product):
                    paths.append(dict(row,device=product,**value));previous[product]=value
        event=None
        if 'with unknown ow status(' in line:event='unknown_USB_completion_status'
        if product:
            if 'Device disconnected from host.' in line:event='host_disconnect'
            elif 'Failed to abort pipe(' in line:event='abort_pipe_warning'
            elif 'Device connected.' in line:event='connected'
            elif 'Device arrived.' in line:event='arrived'
        if event:
            e=dict(row,device=product,event=event)
            status=re.search(r"usbioerr '([A-Z_]+)'",line)
            if status:e['status']=status[1]
            ep=re.search(r'endptAddr\(([0-9a-fA-F]+)\)',line)
            if ep:e['endpoint_hex']=ep[1]
            events.append(e)
    window=[r for t,r in parsed if START<=t<END]
    before=max(((t,r) for t,r in parsed if t<START),default=None,key=lambda x:x[0])
    after=min(((t,r) for t,r in parsed if t>=END),default=None,key=lambda x:x[0])
    return {'source':{'kind':'user-pasted VMware host log; original kept private','bytes':len(raw),
                     'SHA256':hashlib.sha256(raw).hexdigest(),'lines':len(lines),'raw_log_in_Git':False},
            'source_coverage':{'first':min(parsed,key=lambda x:x[0])[1] if parsed else None,
                               'last':max(parsed,key=lambda x:x[0])[1] if parsed else None,
                               'pasted_contiguity_or_original_disk_file_not_independently_verified':True},
            'target_window':{'UTC_start':START.isoformat(),'UTC_end_exclusive':END.isoformat(),
                             'local_start':START.astimezone(LOCAL).isoformat(),'local_end_exclusive':END.astimezone(LOCAL).isoformat(),
                             'all_record_count':len(window),'records':window,
                             'nearest_before':before[1] if before else None,'nearest_after':after[1] if after else None,
                             'absence_of_log_records_is_not_absence_of_USB_fault':True},
            'host_configuration':{'workstation':version,'Hyper_V_detected':hyper_v,'monitor_mode':mode,
                                  'allowlisted_controller_config':config,'Hyper_V_ULM_not_proven_failure_cause':True},
            'device_path_changes':paths,'device_events':events,
            'privacy_policy':'Only timestamps, source hashes/lines, known camera/CAN categories, USB topology and allowlisted status/config. No hostnames, IPs, Windows paths, unrelated devices, serial or instance IDs.'}

def self_test():
    raw=(
        '2026-10-16T05:14:23.742Z In(05) vmx USBGA: DevID(100000091d50606f): Device disconnected from host.\n'
        '2026-10-16T05:14:36.818Z In(05) vmx USB: Found device [name:SECRET_NAME vid:1d50 pid:606f path:1/0/1 speed:full family:vendor virtPath:usb_xhci:9 instanceId:SECRET_ID serialnum:SECRET_SERIAL ownertarget:C:\\Users\\SECRET_USER], connected to usb_xhci:4 port 1.\n'
        '2026-10-16T05:23:00.000Z In(05) vmx Hostname=SECRET_HOST IP=192.0.2.99\n').encode()
    r=review(raw);encoded=json.dumps(r)
    assert r['target_window']['all_record_count']==1
    assert r['target_window']['records'][0]['local_UTC_plus8']=='2026-10-16T13:23:00+08:00'
    assert r['device_events'][0]['device']=='USB-CAN'
    assert r['device_path_changes'][0]['host_path']=='1/0/1'
    assert not any(s in encoded for s in ('SECRET_','192.0.2.99','C:\\Users'))
    return {'UTC_window_device_mapping_privacy':'passed'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    tests=self_test();result=review(a.source.read_bytes());result['synthetic_checks']=tests
    with a.output.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False,allow_nan=False)
    print(json.dumps({'source_SHA256':result['source']['SHA256'],'lines':result['source']['lines'],
                      'window_record_count':result['target_window']['all_record_count'],
                      'events':len(result['device_events']),'path_changes':len(result['device_path_changes']),'tests':tests},indent=2))
