"""Fit an unknown local diameter from a masked, calibrated world RGB-D cloud.

No specimen radius/height or Gazebo object pose is an input. This estimator
assumes an upright circular cross-section; other shapes need a different fit.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class DiameterEstimate:
    diameter_m: float
    sigma_m: float
    center_xy_m: tuple
    support_count: int
    arc_rad: float
    residual_p90_m: float


def fit_local_diameter(world_points, grasp_height_m, *, camera_origin_world, band_m=.012):
    points = np.asarray(world_points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(grasp_height_m) or band_m <= 0:
        raise ValueError('invalid calibrated cloud or height band')
    data = points[np.isfinite(points).all(axis=1) &
                  (np.abs(points[:, 2]-grasp_height_m) <= band_m), :2]
    if len(data) < 60:
        raise ValueError('insufficient local depth support')
    camera = np.asarray(camera_origin_world, dtype=float)
    if camera.shape != (3,) or not np.isfinite(camera).all():
        raise ValueError('a calibrated camera origin is required for outer-wall selection')
    initial = _fit_circle(data)
    center = np.asarray(initial.center_xy_m)
    toward_camera = camera[:2]-center
    distance = np.linalg.norm(toward_camera)
    if distance < initial.diameter_m:
        raise ValueError('overhead view cannot distinguish outer and inner walls')
    # Only the near-facing half of the shell is an external surface. The far
    # inner wall can be visible through the mouth and must not shrink the fit.
    front = (data-center)@(toward_camera/distance) > .1*initial.diameter_m
    if int(front.sum()) < 60:
        raise ValueError('insufficient visible outer-wall support')
    return _fit_circle(data[front])


def _fit_circle(data):
    # Deterministic RANSAC rejects mask-edge/background points before fitting.
    rng = np.random.default_rng(20261014)
    best = None
    best_count = 0
    for _ in range(128):
        tri = data[rng.choice(len(data), 3, replace=False)]
        origin = tri[0]
        a = 2*(tri[1:]-origin)
        if np.linalg.cond(a) > 1000:
            continue
        center = origin+np.linalg.solve(a, ((tri[1:]-origin)**2).sum(axis=1))
        radius = np.linalg.norm(tri[0]-center)
        if not .005 < radius < .060:
            continue
        residual = np.abs(np.linalg.norm(data-center, axis=1)-radius)
        inliers = residual < .0015
        count = int(inliers.sum())
        if count > best_count:
            best, best_count = (center, radius, inliers), count
    if best is None or best_count < max(60, .65*len(data)):
        raise ValueError('no well-supported circular cross-section')
    center, radius, inliers = best
    selected = data[inliers]
    for _ in range(12):
        delta = selected-center
        distance = np.linalg.norm(delta, axis=1)
        residual = distance-radius
        jac = np.column_stack((-delta/np.maximum(distance[:, None], 1e-9), -np.ones(len(selected))))
        weights = np.minimum(1., .0008/np.maximum(np.abs(residual), 1e-9))
        step = np.linalg.lstsq(jac*weights[:, None], -residual*weights, rcond=None)[0]
        center += step[:2]
        radius += step[2]
        if np.linalg.norm(step) < 1e-8:
            break
    if not .005 < radius < .060 or not np.isfinite(center).all():
        raise ValueError('invalid fitted cross-section')
    residual = np.linalg.norm(selected-center, axis=1)-radius
    angles = np.mod(np.arctan2(selected[:, 1]-center[1], selected[:, 0]-center[0]), 2*np.pi)
    ordered = np.sort(angles)
    arc = 2*np.pi-float(np.max(np.diff(np.r_[ordered, ordered[0]+2*np.pi])))
    if arc < np.deg2rad(70):
        raise ValueError('visible arc is too small to estimate diameter')
    if np.linalg.cond(jac) > 50 or np.quantile(np.abs(residual), .9) > .0015:
        raise ValueError('ill-conditioned or inconsistent local diameter fit')
    covariance = np.linalg.inv(jac.T@jac)*max(float(np.mean(residual**2)), 1e-10)
    # 1 mm floor accounts for depth/mask/model effects that independent-point
    # least-squares covariance does not represent. This is not a calibrated CI.
    sigma = max(.001, 2*float(np.sqrt(covariance[2, 2])))
    return DiameterEstimate(float(2*radius), sigma, tuple(map(float, center)),
                            len(selected), arc, float(np.quantile(np.abs(residual), .9)))
