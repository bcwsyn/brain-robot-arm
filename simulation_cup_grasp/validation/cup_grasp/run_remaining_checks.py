from pathlib import Path
import json,subprocess,time
ws=Path(__file__).resolve().parents[2]
pub=Path('/tmp/piper-stage5-publish-20261014/simulation_cup_grasp')
v=ws/'validation/cup_grasp'
end=time.monotonic()+180
while True:
 d=json.loads((v/'acceptance_r8_final/results.json').read_text())
 if not d['passed']:raise RuntimeError('Final suite failed; stop follow-up motions')
 if d['complete']:break
 if time.monotonic()>end:raise RuntimeError('Final suite still incomplete')
 time.sleep(2)
checks=[]
for name,base,script in [('ball',ws,'run_ball_physics_sim.sh'),('cylinder',ws,'run_cylinder_physics_sim.sh'),('published-cup',pub,'run_cup_grasp_sim.sh')]:
 before=set((base/'log/visual_sim').glob('*'))
 command=['bash','scripts/'+script,'--headless','--seed','20261015','--batch-trials','1']
 print('Starting',name,flush=True)
 with (v/(name+'_final_smoke.console.log')).open('w') as log:
  result=subprocess.run(command,cwd=base,stdout=log,stderr=subprocess.STDOUT,timeout=240)
 after=set((base/'log/visual_sim').glob('*'))-before
 assert len(after)==1,(name,after)
 session=after.pop();s=json.loads((session/'session.json').read_text())
 passed=result.returncode==0 and len(s['runs'])==1 and s['runs'][0]['passed']
 checks.append(dict(name=name,session=str(session),passed=passed,returncode=result.returncode,placement_error_m=s['runs'][0].get('placement_error_m')))
 (v/'final_regression_and_publication_smoke.json').write_text(json.dumps(checks,indent=2)+'\n')
 print(name,'PASSED' if passed else 'FAILED',session,flush=True)
 if not passed:raise RuntimeError(name+' smoke check failed')
