"""Unknown-diameter, hollow-model and force-unit checks before ROS integration."""
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1]/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


geometry, widths, forces = map(load, ['cup_geometry', 'cup_width_estimation', 'contact_force_feedback'])


def surface(diameter, z, arc=2.5, count=240):
    rng = np.random.default_rng(12)
    theta = np.linspace(-arc/2, arc/2, count)
    xy = np.column_stack((.4+diameter/2*np.cos(theta), -.1+diameter/2*np.sin(theta)))
    xy += rng.normal(0, .0002, xy.shape)
    return np.column_stack((xy, z+rng.uniform(-.010, .010, count)))


@pytest.mark.parametrize('diameter', [.055, .063, .075, .088])
def test_unknown_diameter_fit_with_mask_outliers(diameter):
    cloud = surface(diameter, .1)
    rng = np.random.default_rng(3)
    outliers = np.column_stack((rng.uniform(.36, .44, 30), rng.uniform(-.15, -.05, 30), np.full(30, .1)))
    result = widths.fit_local_diameter(np.vstack((cloud, outliers)), .1,
                                      camera_origin_world=(.55, -.1, .3))
    assert abs(result.diameter_m-diameter) < .001
    assert .001 <= result.sigma_m <= .004


def test_body_and_mouth_are_estimated_at_the_selected_local_height():
    cloud = np.vstack((surface(.075, .100), surface(.063, .180)))
    body = widths.fit_local_diameter(cloud, .1, camera_origin_world=(.55, -.1, .3))
    mouth = widths.fit_local_diameter(cloud, .18, camera_origin_world=(.55, -.1, .3))
    assert abs(body.diameter_m-.075) < .001
    assert abs(mouth.diameter_m-.063) < .001
    assert body.diameter_m-mouth.diameter_m > .010


def test_sparse_or_narrow_arc_is_rejected():
    for cloud in [surface(.075, .1, count=20), surface(.075, .1, arc=.08)]:
        with pytest.raises(ValueError):
            widths.fit_local_diameter(cloud, .1, camera_origin_world=(.55, -.1, .3))


def test_visible_far_inner_wall_does_not_shrink_outer_diameter():
    external = surface(.063, .18, arc=2.5)
    internal = surface(.059, .18, arc=2.5)
    internal[:, 0] = .8-internal[:, 0]  # far wall, visible through the open mouth
    result = widths.fit_local_diameter(np.vstack((external, internal)), .18,
                                      camera_origin_world=(.55, -.1, .3))
    assert abs(result.diameter_m-.063) < .001
    with pytest.raises(ValueError):
        widths.fit_local_diameter(external, .18, camera_origin_world=(.4, -.1, .4))


def test_cup_shell_has_open_mouth_correct_mass_and_positive_inertia(tmp_path):
    spec = geometry.CupSpec()
    sections = spec.sections()
    assert sections[-1][0] > 0  # neck has an opening, not a solid cap
    assert sections[-1][2:] == (.160, .200)
    assert spec.height_m == .200
    center, ixy, iz = spec.inertial()
    assert 0 < center < spec.height_m and ixy > 0 and iz > 0
    root = ET.parse(geometry.write_model(tmp_path, spec))
    assert float(root.findtext('.//mass')) == .080
    assert len(root.findall('.//collision')) == 4*spec.segments
    vertices = [tuple(map(float, line.split()[1:])) for line in
                (tmp_path/'cup_visual.stl').read_text().splitlines() if line.startswith('vertex ')]
    assert max(v[2] for v in vertices)-min(v[2] for v in vertices) == pytest.approx(.2)
    rim = [math.hypot(v[0], v[1]) for v in vertices if v[2] == .1]
    assert min(rim) == pytest.approx(.0295) and max(rim) == pytest.approx(.0315)


def test_nonphysical_geometry_is_rejected():
    for kwargs in [{'wall_m': .040}, {'mass_kg': float('nan')}, {'mouth_diameter_m': .09}]:
        with pytest.raises(ValueError):
            geometry.CupSpec(**kwargs)


def contact(name='stepped_cup::cup_link::shell', force=(2, 3, 0), normal=(1, 0, 0)):
    return NS(collision1_name='piper::link7::pad', collision2_name=name,
              wrenches=[NS(force=NS(x=force[0], y=force[1], z=force[2]))],
              contact_normals=[NS(x=normal[0], y=normal[1], z=normal[2])],
              total_wrench=NS(force=NS(x=2, y=3, z=0)))


def test_normal_force_excludes_friction_total_wrench_and_other_objects():
    result, count = forces.target_normal_force(NS(states=[contact(), contact('stepped_cup_extra::link::shell')]), 'stepped_cup')
    assert result == 2 and count == 1
    assert forces.target_normal_force(NS(states=[contact(normal=(-1, 0, 0))]), 'stepped_cup')[0] == 2
    assert forces.target_normal_force(NS(states=[]), 'stepped_cup') == (0, 0)


def test_corrupt_contact_feedback_is_rejected():
    for c in [contact(force=(float('nan'), 0, 0)), contact(normal=(0, 0, 0))]:
        with pytest.raises(ValueError):
            forces.target_normal_force(NS(states=[c]), 'stepped_cup')
    c = contact()
    c.contact_normals.clear()
    with pytest.raises(ValueError):
        forces.target_normal_force(NS(states=[c]), 'stepped_cup')


def test_sensor_batch_does_not_add_forces_across_physics_steps():
    older, latest_a, latest_b = contact(force=(8, 0, 0)), contact(force=(1.3, 0, 0)), contact(force=(.4, 0, 0))
    older.info = 'time: [10.9000000]'
    latest_a.info = latest_b.info = 'time: [10.10000000]'
    value, points = forces.target_normal_force(NS(states=[older, latest_a, latest_b]),
                                             'stepped_cup', require_step_time=True)
    assert value == pytest.approx(1.7) and points == 2


def test_batched_missing_timestamp_is_rejected_in_live_force_mode():
    with pytest.raises(ValueError):
        forces.target_normal_force(NS(states=[contact()]), 'stepped_cup', require_step_time=True)


def test_whole_pad_axis_force_cancels_opposing_edge_loads():
    a, b = contact(force=(6, 0, 0), normal=(1, 0, 0)), contact(force=(-6, 2, 0), normal=(-1, 0, 0))
    a.info = b.info = 'time: [10.10000000]'
    message = NS(states=[a, b])
    assert forces.target_normal_force(message, 'stepped_cup')[0] == 12
    assert forces.target_axis_force(message, 'stepped_cup', (0, 1, 0)) == (2, 2)
