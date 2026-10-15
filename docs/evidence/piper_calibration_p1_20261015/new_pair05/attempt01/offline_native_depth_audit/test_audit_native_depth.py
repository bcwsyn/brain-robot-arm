"""Synthetic helper tests only; not evidence of camera accuracy."""
import unittest
import numpy as np
from audit_pair05_depth import footprint_stats, describe, factory_numbers


class NativeFootprintTests(unittest.TestCase):
    def setUp(self):
        self.mask=np.array([[True,True],[False,True]])

    def test_zeros_are_counted_not_filled(self):
        raw=np.array([[0,217],[999,217]],dtype=np.uint16)
        before=raw.copy()
        result=footprint_stats(raw,self.mask)
        self.assertEqual(result['zero_pixels'],1)
        self.assertEqual(result['nonzero_mm']['median'],217)
        self.assertTrue(np.array_equal(raw,before))

    def test_missing_region_has_no_invented_median(self):
        result=footprint_stats(np.zeros((2,2),dtype=np.uint16),self.mask)
        self.assertEqual(result['zero_fraction'],1)
        self.assertIsNone(result['nonzero_mm']['median'])

    def test_supported_region_uses_only_fixed_mask(self):
        result=footprint_stats(np.full((2,2),217,dtype=np.uint16),self.mask)
        self.assertEqual(result['zero_fraction'],0)
        self.assertEqual(result['nonzero_mm']['count'],3)
        self.assertIsNone(describe([])['median'])

    def test_factory_read_time_not_numeric_identity(self):
        packet={'read_epoch':0,'get_device_info':{'info':{'serial_number':'synthetic'}},
                'get_camera_params':{'r2l_t':[1,2,3]},
                'get_camera_info':{'info':{'k':[1]*9}},
                'camera_link_from_depth_optical':{'header':{'stamp':0},'transform':{'synthetic':True}}}
        expected=factory_numbers(packet)
        packet['read_epoch']=99
        packet['camera_link_from_depth_optical']['header']['stamp']=99
        self.assertEqual(factory_numbers(packet),expected)
        packet['get_camera_params']={'r2l_t':[1,2,4]}
        self.assertNotEqual(factory_numbers(packet),expected)


if __name__=='__main__':
    unittest.main()
