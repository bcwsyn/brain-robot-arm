"""RGB-D sizing from a learned mask and calibrated camera transform only."""
import numpy as np

from cup_width_estimation import fit_local_diameter
from adaptive_gripper_policy import opening_from_measurement


def estimate_masked_cup(depth_m, mask, k, rotation_world_camera, camera_origin_world,
                        *, grasp_height_fraction=.55):
    """Assume a single upright cup on the z=0 tabletop; reject unobservable fits."""
    z, mask, k = np.asarray(depth_m), np.asarray(mask, dtype=bool), np.asarray(k)
    if z.ndim != 2 or mask.shape != z.shape or k.shape != (3, 3) or min(k[0, 0], k[1, 1]) <= 0:
        raise ValueError('RGB-D mask or calibrated intrinsics are invalid')
    rotation, origin = np.asarray(rotation_world_camera), np.asarray(camera_origin_world)
    if rotation.shape != (3, 3) or origin.shape != (3,) or not np.isfinite(rotation).all() or not np.isfinite(origin).all():
        raise ValueError('invalid camera transform')
    rows, cols = np.where(mask & np.isfinite(z) & (z > .05) & (z < 2))
    if len(rows) < 120:
        raise ValueError('insufficient masked depth points')
    camera_points = np.column_stack(((cols-k[0, 2])*z[rows, cols]/k[0, 0],
        (rows-k[1, 2])*z[rows, cols]/k[1, 1], z[rows, cols]))
    world_points = camera_points@rotation.T+origin
    # Remove the fixed tabletop, background and geometrically impossible cup
    # heights. These bounds are workspace assumptions, not specimen dimensions.
    world_points = world_points[(world_points[:, 2] > .005) & (world_points[:, 2] < .35)]
    if len(world_points) < 120:
        raise ValueError('insufficient upright object support above the table')
    observed_height = float(np.quantile(world_points[:, 2], .995))
    if not .06 < observed_height < .30:
        raise ValueError('observed cup height outside supported workspace')
    if not np.isfinite(grasp_height_fraction) or not .2 <= grasp_height_fraction <= .8:
        raise ValueError('unsupported body grasp height fraction')
    grasp_height = grasp_height_fraction*observed_height
    estimate = fit_local_diameter(world_points, grasp_height, camera_origin_world=origin)
    opening = opening_from_measurement(estimate.diameter_m, estimate.sigma_m, 0)
    world_target = np.r_[estimate.center_xy_m, grasp_height]
    camera_target = rotation.T@(world_target-origin)
    if camera_target[2] <= .05:
        raise ValueError('grasp centre is behind or too close to the camera')
    pixel = np.array([k[0, 0]*camera_target[0]/camera_target[2]+k[0, 2],
                      k[1, 1]*camera_target[1]/camera_target[2]+k[1, 2]])
    return dict(diameter_m=estimate.diameter_m, sigma_m=estimate.sigma_m,
        support_count=estimate.support_count, residual_p90_m=estimate.residual_p90_m,
        observed_height_m=observed_height, grasp_height_m=grasp_height,
        preopening_m=opening.opening_m, world_target=world_target.tolist(),
        camera_target=camera_target.tolist(), pixel=pixel.tolist())
