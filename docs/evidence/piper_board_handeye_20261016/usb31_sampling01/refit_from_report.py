"""Portable offline re-fit from provided actual-FK/PnP matrices, no ROS or CAN.

This checks the fit, not raw FK correctness or detector/calibration accuracy.
"""
import json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'full_ROI'))
from board_handeye_fit import solve,compare,metrics,synthetic
path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'full_ROI/handeye_fit_report.json'
report=json.loads(path.read_text());samples=report['samples']
gs=[np.asarray(s['T_base_gripper_mean']) for s in samples]
cs=[np.asarray(s['T_color_board_mean']) for s in samples]
fit=[i for i,s in enumerate(samples) if s['role']=='fit'];held=[i for i,s in enumerate(samples) if s['role']=='heldout']
assert len(fit)==9 and len(held)==1
fg=[gs[i] for i in fit];fc=[cs[i] for i in fit]
x,w=solve(fg,fc);check=synthetic(fg)
seed=json.loads((ROOT/'full_ROI/session_seed.json').read_text())
err=metrics(gs[held[0]],cs[held[0]],x,w,np.asarray(seed['object_points_m']))
difference=compare(x,np.asarray(report['T_gripperBase_colorOptical_candidate']))
assert check['passed'] and difference['translation_m']<1e-10 and difference['rotation_deg']<1e-8
print(json.dumps({'offline_only':True,'robot_model_FK_provided_not_recomputed':True,'fit_count':9,'heldout_count':1,
    'reproduced_X_difference':difference,'heldout':err,'no_production_or_hardware_access':True},indent=2))
