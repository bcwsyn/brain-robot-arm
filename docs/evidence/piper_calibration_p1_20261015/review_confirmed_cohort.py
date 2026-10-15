"""Offline P1 delta summary: trust original quality reports, never fit or move."""
import hashlib,json,sys
from pathlib import Path
REPO=Path('/mnt/hgfs/ub');BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(REPO/'brain_robot_arm/piper_ws/src/brain_robot_pick_place/test'))
from export_calibration_bundle import verify_bundle
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())

def readiness(rows):
    if len(rows)!=6 or len({r['pair_id'] for r in rows})!=6:
        raise ValueError('Exactly six distinct pair IDs required')
    fit=[r for r in rows if r['role']=='fit'];held=[r for r in rows if r['role']=='held_out']
    if len(fit)!=5 or len(held)!=1 or held[0]['pair_id']!='new_pair07':
        raise ValueError('Keep the predefined5fit+new_pair07holdout split')
    good_fit=[r for r in fit if r['original_good_top_frames']>=20]
    good_held=[r for r in held if r['original_good_top_frames']>=20]
    return {'training_ids_with_quality_A':[r['pair_id'] for r in good_fit],
        'held_out_ids_with_quality_A':[r['pair_id'] for r in good_held],
        'training_ids_needing_new_quality_A':[r['pair_id'] for r in fit if r not in good_fit],
        'necessary_image_quality_for_5plus1_met':len(good_fit)==5 and len(good_held)==1,
        'formal_calibration_approved':False,'fit_performed':False}

def main(output):
    if output.exists():raise FileExistsError('Do not overwrite a prior summary')
    registry=load(BASE/'P1_registry.json');inputs={}
    def record(path,expected=None):
        digest=sha(path)
        if expected is not None and digest!=expected:raise ValueError('Source SHA mismatch: '+str(path))
        inputs[str(path.relative_to(REPO))]=digest
        return load(path)
    record(BASE/'P1_registry.json')
    prior=record(BASE/'offline_recovery_audit/results/report.json')
    # Reuse the existing19-source audit; don't repeat its geometry experiments.
    for rel,digest in prior['input_SHA'].items():
        if rel!='docs/evidence/piper_calibration_p1_20261015/P1_registry.json':record(REPO/rel,digest)
    rows=[]
    for original in registry['rows']:
        source=original
        alternatives=[r for r in registry.get('supplemental_A_candidates',[]) if r['pair_id']==original['pair_id']]
        if alternatives:source=max(alternatives,key=lambda r:r['attempt'])
        if source['role']!=original['role']:raise ValueError('Supplement cannot change fit/holdout role')
        report=record(REPO/source['source'],source['source_sha256']);summary=report['summary']
        if summary['good_top_frames']!=source['original_good_top_frames']:raise ValueError('Registry count mismatch')
        rows.append({'pair_id':source['pair_id'],'role':source['role'],'current_source':source['source'],
            'original_good_top_frames':summary['good_top_frames'],'original_raw_A_frames':summary['frames'],
            'old_primary_good_frames_preserved':original['original_good_top_frames'],
            'formal_pair_approved':False})
    grip=BASE/'new_pair07/attempt03/grip_capture';observe=BASE/'new_pair07/attempt03/observe_capture'
    for bundle in [observe/'portable_good20',grip/'portable']:
        manifest=record(bundle/'manifest.json');verify_bundle(bundle,manifest)
    confirmation=record(grip/'operator_confirmation.json');pair=record(grip/'paired_sources.json')
    assessment=record(grip/'assessment.json')
    flags=['explicit_same_point_confirmed','actual_contact_explicitly_confirmed','still_on_table_explicitly_confirmed']
    if not all(confirmation[k] is True for k in flags):raise ValueError('New A/B operator confirmation is incomplete')
    assert pair['A_B_same_physical_point_confirmed'] and not pair['old_B8f8eed6_used']
    assert assessment['SDK_quality']['static_three_seconds_and_thirty_samples'] and assessment['B_raw_capture_complete']
    record(observe/'portable_good20/manifest.json',pair['A_manifest_sha256'])
    record(observe/'quality_all60/report.json',pair['A_quality_sha256'])
    result={'offline_only':True,'ROS_initialized':False,'CAN_accessed':False,'camera_started':False,
        'robot_control_or_production_TF_changed':False,'quality_thresholds_changed':False,
        'input_SHA':inputs,'rows':rows,'readiness':readiness(rows),
        'current_held_out_raw_AB_correspondence_complete':True,'operator_quote':confirmation['explicit_confirmation_quote'],
        'do_not_recapture_or_reask_current_held_out':True,'existing_pose_excitation_audit_reused_not_refit':True,
        'next':'P1 still needs new qualified A at new_pair03/04/05/06; new positions require new B. Prepare original release/observe only after explicit authorization, preview A before asking manual grip. No automatic motion or P2 fitting.'}
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({'verified_source_SHA':len(inputs),'held_out_correspondence_complete':True,**result['readiness']}))

if __name__=='__main__':main(Path(sys.argv[1]))
