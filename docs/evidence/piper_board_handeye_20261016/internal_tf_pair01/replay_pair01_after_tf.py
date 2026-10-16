"""Replay all 30 immutable pair01 RGB-D pairs using old versus corrected live TF."""
import copy,hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parent;REPO=Path('/mnt/hgfs/ub')
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from review_depth_registration import calibration,color_mask,project_measured,read_config
CAP=REPO/'docs/evidence/piper_calibration_20261014/pair01/pair01_observe_remeasure_20261014_rgbd'
OLD=REPO/'docs/evidence/piper_board_handeye_20261016/usb31_mount_deploy01'
p=read_config(Path('/home/johnwick/piper_ws/src/brain_robot_ball_pick/config/cube_detector.yaml'))
base=calibration(p)
oldT=np.array(json.loads((OLD/'live_composition_review.json').read_text())['live_T_colorOptical_depthOptical'])
v=json.loads((ROOT/'live_mount_verification.json').read_text())
t=v['samples'][0]['transforms'][3]['transform'];q=t['rotation'];z=t['translation']
newT=np.eye(4);newT[:3,:3]=Rotation.from_quat([q[k] for k in ['x','y','z','w']]).as_matrix();newT[:3,3]=[z[k] for k in ['x','y','z']]
options={'unchanged_detector':base}
for name,T in [('old_live_TF',oldT),('corrected_live_TF',newT)]:
    c=copy.deepcopy(base);c['r'],c['t']=T[:3,:3],T[:3,3];options[name]=c
previous=json.loads((OLD/'recorded_rgbd_direction_check.json').read_text())
high={r['snapshot']:r['prior_high_support'] for r in previous['frames']}
rows=[];examples={}
for line in (CAP/'observer.jsonl').read_text().splitlines():
    row=json.loads(line);i=row['snapshot'];rp=CAP/'evidence'/f'{i:04d}_rgb.png';dp=CAP/'evidence'/f'{i:04d}_depth.png'
    rgb=cv2.imread(str(rp));depth=cv2.imread(str(dp),cv2.IMREAD_UNCHANGED)
    kd=np.array(row['latest']['/camera/depth/camera_info']['k']).reshape(3,3)
    mask,_=color_mask(rgb,p);stats={};surfaces={}
    for label,c in options.items():
        uv,pixel,valid=project_measured(depth,kd,c,(rgb.shape[1],rgb.shape[0]),p)
        keep=valid&(depth>=425)&(depth<=450);px=pixel[keep]
        hit=np.zeros(mask.shape,np.uint8)
        if len(px):hit[px[:,1],px[:,0]]=1
        stats[label]={'cube_mask_coverage':float(((hit>0)&(mask>0)).sum()/max(1,(mask>0).sum())),
            'native_points_inside_mask':int((mask[px[:,1],px[:,0]]>0).sum())}
        if i in [1,2]:surfaces[label]=(uv[keep],depth[keep]*.001)
    rows.append({'snapshot':i,'prior_high_support':high[i],
        'RGB_SHA256':hashlib.sha256(rp.read_bytes()).hexdigest(),
        'depth_SHA256':hashlib.sha256(dp.read_bytes()).hexdigest(),'comparison':stats})
    if i in [1,2]:examples[i]=(rgb,mask,surfaces)
summary={label:{group:{'frames':len(selected),
    'coverage_median':float(np.median([r['comparison'][label]['cube_mask_coverage'] for r in selected])),
    'coverage_min':min(r['comparison'][label]['cube_mask_coverage'] for r in selected),
    'coverage_max':max(r['comparison'][label]['cube_mask_coverage'] for r in selected)}
    for group,selected in [('all_30',rows),('prior_high_support_10',[r for r in rows if r['prior_high_support']])]} for label in options}
max_diff=max(abs(r['comparison']['unchanged_detector']['cube_mask_coverage']-r['comparison']['corrected_live_TF']['cube_mask_coverage']) for r in rows)
assert max_diff==0
report={'offline_only':True,'hardware_opened':False,'all_30_original_pairs_included':True,
    'slab_m':[.425,.450],'slab_from_previously_published_surface_not_optimized':True,
    'same_high_support_selection_bias_as_prior_report':True,'summary':summary,
    'corrected_vs_unchanged_detector_max_coverage_difference':max_diff,'frames':rows,
    'scope':'Local saved surface correspondence and transform consistency, not global absolute accuracy or TCP/grasp verification.'}
with (ROOT/'pair01_corrected_TF_replay.json').open('x') as f:json.dump(report,f,indent=2,allow_nan=False)
fig,axes=plt.subplots(2,3,figsize=(11,6))
for y,i in enumerate([2,1]):
    rgb,mask,surfaces=examples[i]
    for x,label in enumerate(['raw_RGB','old_live_TF','corrected_live_TF']):
        ax=axes[y,x];ax.imshow(cv2.cvtColor(rgb,cv2.COLOR_BGR2RGB))
        ax.contour(mask,levels=[127],colors=['lime'],linewidths=.8)
        if label in surfaces:
            uv,dep=surfaces[label];ax.scatter(uv[:,0],uv[:,1],c=dep,s=1,cmap='turbo',vmin=.425,vmax=.450,alpha=.7)
        ax.set_xlim(108,176);ax.set_ylim(155,100);ax.set_title(f'pair01 frame {i}: {label}',fontsize=9)
fig.suptitle('Fixed 425-450mm native surface points; green = unchanged RGB cube mask. No depth filling.')
fig.tight_layout();fig.savefig(ROOT/'pair01_TF_comparison.png',dpi=130);plt.close(fig)
print(json.dumps({'summary':summary,'corrected_matches_detector_all_30':max_diff==0},indent=2))
