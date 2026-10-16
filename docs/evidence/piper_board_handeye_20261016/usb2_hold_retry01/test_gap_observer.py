"""Offline tests: extract pure diagnostic helper, never import ROS/CAN wrapper."""
import ast
import difflib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'run_hold.py'
tree=ast.parse(SOURCE.read_text())
helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='observe_feedback_gap')
namespace={}
exec(compile(ast.fix_missing_locations(ast.Module(body=[helper],type_ignores=[])),str(SOURCE),'exec'),namespace)
observe=namespace['observe_feedback_gap']

class GapObserverTest(unittest.TestCase):
    def state(self):return {'feedback_gap_events':[],'open_feedback_gap':None}

    def test_fresh_does_not_create_gap(self):
        s=self.state()
        for age in [0,.01,.499,.5]:observe(s,age,100)
        self.assertEqual(s,self.state())

    def test_original_transient_does_not_raise(self):
        s=self.state()
        observe(s,.678535,100)
        self.assertIsNotNone(s['open_feedback_gap'])
        observe(s,.868145,100.19)
        observe(s,.005,100.2)
        self.assertIsNone(s['open_feedback_gap'])
        self.assertEqual(len(s['feedback_gap_events']),1)
        self.assertEqual(s['feedback_gap_events'][0]['maximum_observed_age_s'],.868145)

    def test_long_gap_observer_never_controls_timeout(self):
        s=self.state()
        for age in [.6,1,24.9,25,26]:observe(s,age,100+age)
        self.assertEqual(s['open_feedback_gap']['maximum_observed_age_s'],26)
        self.assertEqual(s['feedback_gap_events'],[])

    def test_repeated_gaps_and_unrecovered_end_are_retained(self):
        s=self.state()
        for age in [.6,.9,.01,.7,.02,1]:observe(s,age,100+age)
        self.assertEqual(len(s['feedback_gap_events']),2)
        self.assertIsNotNone(s['open_feedback_gap'])

    def test_original_control_and_fresh_start_invariants(self):
        text=SOURCE.read_text()
        self.assertIn("assert armed_status is True, 'Original adapter disarmed'",text)
        self.assertIn("params.values[1].double_value == 25.",text)
        self.assertIn("time.time()-latest['epoch'] < .5 and armed_status is False",text)
        self.assertNotIn("assert time.time()-latest['epoch'] <= .5",text)
        for n in ast.walk(tree):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute):
                self.assertNotIn(n.func.attr,('create_publisher','JointCtrl','GripperCtrl','ResetPiper','MasterSlaveConfig','DisableArm'))

if __name__=='__main__':
    old=Path('/mnt/hgfs/ub/docs/evidence/piper_board_handeye_20261016/usb2_hold01/run_hold.py')
    (ROOT/'harness_change.diff').write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),SOURCE.read_text().splitlines(True),fromfile='usb2_hold01/run_hold.py',tofile='usb2_hold_retry01/run_hold.py')))
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(GapObserverTest)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (ROOT/'offline_test_result.json').write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'success':result.wasSuccessful(),'ROS_CAN_or_motion_access':False},indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 2)
