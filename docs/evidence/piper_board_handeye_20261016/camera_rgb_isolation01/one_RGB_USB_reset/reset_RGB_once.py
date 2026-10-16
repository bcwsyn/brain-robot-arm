"""One exact RGB USB reset; no CAN or robot device writes."""
from pathlib import Path
import fcntl,json,os,subprocess,time
ROOT=Path(__file__).resolve().parent
assert not (ROOT/'RGB_reset.json').exists(), 'Never repeat reset in this session'
report={'target_vendor_product':'2bc5:0557','expected_serial':'CC1365304DG',
        'only_camera_USB_reset':True,'robot_CAN_reset_enable_disable_or_motion':False,'error':None}
def cmd(argv):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=5)
    return {'argv':argv,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
try:
    candidates=[]
    for p in Path('/sys/bus/usb/devices').glob('*'):
        if all((p/k).exists() for k in ['idVendor','idProduct','serial']):
            if (p/'idVendor').read_text().strip()=='2bc5' and (p/'idProduct').read_text().strip()=='0557' and (p/'serial').read_text().strip()=='CC1365304DG':candidates.append(p)
    assert len(candidates)==1
    p=candidates[0];bus=int((p/'busnum').read_text());dev=int((p/'devnum').read_text())
    assert bus==2 and p.name=='2-2'
    target=f'/dev/bus/usb/{bus:03d}/{dev:03d}'
    report.update(target=target,sysfs=str(p.resolve()),before_epoch=time.time(),kernel_before=cmd(['dmesg','-T']))
    occupied=cmd(['fuser','/dev/video0']);report['RGB_device_users']=occupied
    assert occupied['rc']==1 and not occupied['stdout'].strip(), 'A live RGB user exists; no reset'
    report['CAN_before']=cmd(['ip','-json','-details','-statistics','link','show','can0'])
    fd=os.open(target,os.O_WRONLY)
    try:fcntl.ioctl(fd,0x5514,0)
    finally:os.close(fd)
    report['reset_ioctl_rc']=0;report['after_epoch']=time.time()
    report['USB_after']=cmd(['lsusb','-t']);report['kernel_after']=cmd(['dmesg','-T'])
    report['CAN_after']=cmd(['ip','-json','-details','-statistics','link','show','can0'])
except BaseException as e:report['error']=repr(e)
(ROOT/'RGB_reset.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:report.get(k) for k in ['target','reset_ioctl_rc','error']}))
raise SystemExit(0 if report.get('reset_ioctl_rc')==0 and report['error'] is None else 2)
