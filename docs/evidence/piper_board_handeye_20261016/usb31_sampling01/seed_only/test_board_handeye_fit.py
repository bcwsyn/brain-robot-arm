import unittest
import numpy as np
from scipy.spatial.transform import Rotation
from board_handeye_fit import transform,solve,synthetic,compare,excitation,metrics

class HandEyeTests(unittest.TestCase):
    def setUp(self):
        self.gs=[transform(Rotation.from_euler('xyz',r,degrees=True).as_matrix(),t)
          for r,t in [([0,0,0],[0,0,0]),([6,0,0],[.01,0,0]),([-6,0,0],[0,.01,0]),
                      ([0,8,0],[0,0,.01]),([0,0,-8],[.01,.02,0]),([4,-6,6],[0,.01,.02])]]
    def test_known_transform(self):self.assertTrue(synthetic(self.gs)['passed'])
    def test_nonparallel_axes(self):self.assertEqual(excitation(self.gs)['translation_rank'],3)
    def test_single_axis_rejected(self):
        gs=[transform(Rotation.from_euler('x',r,degrees=True).as_matrix()) for r in [0,6,-6]]
        with self.assertRaises(ValueError):solve(gs,[np.eye(4)]*3)
    def test_wrong_pair_count(self):
        with self.assertRaises(ValueError):solve(self.gs,[np.eye(4)])
    def test_error_meters_and_degrees(self):
        d=compare(np.eye(4),transform(Rotation.from_euler('z',5,degrees=True).as_matrix(),[.003,.004,0]))
        self.assertAlmostEqual(d['translation_m'],.005);self.assertAlmostEqual(d['rotation_deg'],5)
    def test_heldout_not_fit(self):
        x=transform(Rotation.from_euler('xyz',[12,-25,7],degrees=True).as_matrix(),[-.04,.01,.03])
        w=transform(xyz=[.3,-.12,.05]);cs=[np.linalg.inv(g@x)@w for g in self.gs]
        fit,_=solve(self.gs[:-1],cs[:-1]);cs[-1][:3,3]+=[.03,0,0]
        err=metrics(self.gs[-1],cs[-1],fit,w,np.array([[0,0,0],[.032,0,0],[0,.032,0]]))
        self.assertGreater(err['board_corner_max_m'],.025)
        self.assertLess(compare(fit,x)['translation_m'],1e-7)

if __name__=='__main__':unittest.main(verbosity=2)
