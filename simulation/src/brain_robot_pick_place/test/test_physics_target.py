"""Known surface fits with independent synthetic clouds, without ROS nodes."""
import ast
from pathlib import Path
import unittest
import numpy as np

source = Path(__file__).resolve().parents[1] / 'scripts' / 'physics_target_node.py'
tree = ast.parse(source.read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'fit_center')
namespace = {'np': np}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
fit_center = namespace['fit_center']


class SurfaceFitTests(unittest.TestCase):
    def test_partial_sphere_with_depth_noise(self):
        rng = np.random.default_rng(42)
        direction = rng.normal(size=(1200, 3))
        direction /= np.linalg.norm(direction, axis=1)[:, None]
        direction = direction[direction[:, 0] < -.15]
        reference = np.array([.4, -.11, .0175])
        points = reference + .0175 * direction + rng.normal(0, .0004, direction.shape)
        center, residual, count = fit_center(points, 'sphere', .0175, .1)
        self.assertLess(np.linalg.norm(center-reference), .001)
        self.assertLess(residual, .0015)
        self.assertGreater(count, 60)

    def test_upright_cylinder_ignores_top(self):
        rng = np.random.default_rng(7)
        angle = rng.uniform(2., 4.3, 600)
        points = np.column_stack((.41+.025*np.cos(angle), -.09+.025*np.sin(angle),
                                  rng.uniform(.01, .095, len(angle))))
        points += rng.normal(0, .0003, points.shape)
        top = np.column_stack((rng.uniform(.39, .43, 200), rng.uniform(-.1, -.08, 200),
                               np.full(200, .1)))
        center, _, _ = fit_center(np.vstack((points, top)), 'cylinder', .025, .1)
        self.assertLess(np.linalg.norm(center-[.41, -.09, .05]), .001)

    def test_sparse_or_inconsistent_depth_is_rejected(self):
        with self.assertRaises(ValueError):
            fit_center(np.zeros((10, 3)), 'sphere', .0175, .1)
        rng = np.random.default_rng(8)
        with self.assertRaises(ValueError):
            fit_center(rng.uniform([.3, -.2, 0], [.5, 0, .1], (400, 3)), 'sphere', .0175, .1)

    def test_cylinder_top_cap_without_visible_sides(self):
        rng = np.random.default_rng(12)
        angle = rng.uniform(0, 2*np.pi, 2200)
        radius = .025*np.sqrt(rng.uniform(0, 1, len(angle)))
        points = np.column_stack((.39+radius*np.cos(angle), -.1+radius*np.sin(angle),
                                  .1+rng.normal(0, .0004, len(angle))))
        center, _, _ = fit_center(points, 'cylinder', .025, .1)
        self.assertLess(np.linalg.norm(center-[.39, -.1, .05]), .001)


if __name__ == '__main__':
    unittest.main()
