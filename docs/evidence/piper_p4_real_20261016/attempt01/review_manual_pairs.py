"""Reuse existing hand-placed pairs to DIAGNOSE current geometry, no adoption."""
import hashlib,json,sys,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
REPO=Path('/mnt/hgfs/ub');ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import load_installed_model,base_tool_fk
urdf,_=load_installed_model();model=ET.fromstring(urdf)
X=np.array(json.loads((REPO/'docs/evidence/piper_board_handeye_20261016/usb31_sampling01/full_ROI/handeye_fit_report.json').read_text())['T_gripperBase_colorOptical_candidate'])
base=REPO/'docs/evidence/piper_calibration_p1_20261015'
inputs=[('new_pair02',base/'new_pair02/attempt02/observe_capture/p0_report.json',base/'new_pair02/attempt02/grip_capture/portable'),
 ('new_pair07',base/'new_pair07/attempt03/observe_capture/quality_all60/report.json',base/'new_pair07/attempt03/grip_capture/portable')]
result=[]
for name,afile,bdir in inputs:
    a=json.loads(afile.read_text());b=json.loads((bdir/'sdk_review.json').read_text())
    good=[r for r in a['frames'] if r.get('good_top_frame') and r.get('top_candidate')]
    bs=[r for r in b['samples'] if r.get('feedback_fresh') and r.get('q_driver_rad')]
    if not good or not bs:raise RuntimeError(name+' missing actual candidate source')
    qB=np.median([r['q_driver_rad'] for r in bs],axis=0);GB=np.array(base_tool_fk(model,qB))
    centers=[]
    for row in good:
        GA=np.array(base_tool_fk(model,row['actual_q_rad']))
        centers.append((GA@X@np.r_[row['top_candidate']['cube_center_color_m'],1])[:3])
    point=np.median(centers,axis=0);tcp=np.linalg.inv(GB)@np.r_[point,1]
    result.append({'pair':name,'A_quality_source':str(afile),'A_sha256':hashlib.sha256(afile.read_bytes()).hexdigest(),
      'B_source':str(bdir/'sdk_review.json'),'B_sha256':hashlib.sha256((bdir/'sdk_review.json').read_bytes()).hexdigest(),
      'good_A_frames':len(good),'fresh_B_samples':len(bs),'actual_B_q_rad':qB.tolist(),
      'A_candidate_center_base_m':point.tolist(),'implied_tool_center_m_under_NEW_X':tcp[:3].tolist(),
      'difference_from_nominal_tip_m':(tcp[:3]-[0,0,.1358]).tolist(),
      'candidate_only_not_a_verified_TCP':True})
report={'offline_only':True,'manual_records_actually_consumed':True,'TF_TCP_or_control_changed':False,
 'pairs':result,'inter_pair_implied_TCP_difference_m':float(np.linalg.norm(
   np.array(result[0]['implied_tool_center_m_under_NEW_X'])-result[1]['implied_tool_center_m_under_NEW_X'])),
 'limitations':['Assumes camera mounting unchanged since manual sessions.',
   'A centres are original high-support nominal29mm face/normal candidates, not external metrology.',
   'B actual contact was operator-confirmed; unknown axial grip depth remains.',
   'These implied points may absorb FK/hand-eye errors and are NOT adopted as a physical TCP.']}
with (ROOT/'manual_pair_geometry_review.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps(report))
