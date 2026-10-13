import copy
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

DIRECTORY = Path(__file__).parent
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location('camera_alignment', DIRECTORY / 'review_camera_jaw_alignment.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_tf_wait_keeps_exact_original_image_stamp():
    stamp, expected, calls = object(), object(), []

    class DelayedBuffer:
        received = False

        def can_transform(self, target, source, requested):
            calls.append((target, source, requested))
            return self.received

        def lookup_transform(self, target, source, requested):
            assert requested is stamp
            return expected

    buffer = DelayedBuffer()
    result = module.wait_for_stamped_transform(buffer, 'base', 'camera', stamp,
        lambda: setattr(buffer, 'received', True))
    assert result is expected
    assert len(calls) == 2 and all(call[2] is stamp for call in calls)


def test_tf_wait_times_out_without_latest_fallback():
    class MissingBuffer:
        def can_transform(self, target, source, stamp):
            return False

        def lookup_transform(self, *args):
            raise AssertionError('Missing transform must never be substituted')

    with pytest.raises(RuntimeError, match='Exact image-time TF'):
        module.wait_for_stamped_transform(MissingBuffer(), 'base', 'camera', object(),
                                         lambda: None, timeout_s=.001)


def test_listener_warmup_never_returns_a_latest_transform():
    class StartingBuffer:
        ready = False

        def can_transform(self, target, source, stamp):
            assert stamp.nanoseconds == 0  # discovery only, not image lookup
            return self.ready

        def lookup_transform(self, *args):
            raise AssertionError('Warmup must not supply any planning transform')

    buffer = StartingBuffer()
    assert module.wait_for_tf_initialization(buffer, 'base', 'camera',
        lambda: setattr(buffer, 'ready', True)) is None


def test_listener_warmup_remains_bounded():
    class MissingBuffer:
        def can_transform(self, *args):
            return False

    with pytest.raises(RuntimeError, match='TF listener initialization'):
        module.wait_for_tf_initialization(MissingBuffer(), 'base', 'camera',
                                         lambda: None, timeout_s=.001)


@pytest.fixture
def params():
    return {'color_calibration_width': 640, 'color_calibration_height': 480,
            'color_fx': 488.8685, 'color_fy': 488.8685,
            'color_cx': 310.7305, 'color_cy': 209.0377,
            'color_mirror_horizontal': False,
            'depth_to_color_rotation': [1., 0., 0., 0., 1., 0., 0., 0., 1.]}


def projected_after(pixel, delta, depth, params):
    focal = np.array([params['color_fx'] * 319 / 639, params['color_fy'] * 239 / 479])
    centre = np.array([params['color_cx'] * 319 / 639, params['color_cy'] * 239 / 479])
    xy = (np.array(pixel) - centre) / focal * depth
    return (xy - delta[:2]) / (depth - delta[2]) * focal + centre


def test_lateral_step_contracts_actual_image_error_without_forward_motion(params):
    pixel, goal = [120., 161.], [150.5, 155.5]
    delta = module.color_plane_translation(pixel, goal, .15, [320, 240], params, .015)
    assert np.linalg.norm(delta) == pytest.approx(.015)
    assert delta[2] == 0
    after = projected_after(pixel, delta, .15, params)
    assert np.linalg.norm(after - goal) < np.linalg.norm(np.array(pixel) - goal)


def test_small_forward_step_keeps_same_physical_target_on_desired_image_ray(params):
    pixel, goal = [142., 159.], [150.5, 155.5]
    delta = module.color_plane_translation(pixel, goal, .15, [320, 240], params, .015, .010)
    assert np.linalg.norm(delta) < .015
    assert delta[2] == pytest.approx(.010)
    np.testing.assert_allclose(projected_after(pixel, delta, .15, params), goal, atol=1e-12)


def test_mirror_changes_horizontal_sign_only(params):
    mirrored = copy.deepcopy(params)
    mirrored['color_mirror_horizontal'] = True
    a = module.color_plane_translation([120., 161.], [150.5, 155.5], .15, [320, 240], params, .015)
    b = module.color_plane_translation([120., 161.], [150.5, 155.5], .15, [320, 240], mirrored, .015)
    np.testing.assert_allclose(b, [-a[0], a[1], a[2]], atol=1e-12)


@pytest.mark.parametrize('depth', [0., -.1, float('nan'), float('inf')])
def test_invalid_depth_rejected(params, depth):
    with pytest.raises(ValueError):
        module.color_plane_translation([120, 160], [150, 155], depth, [320, 240], params, .015)


@pytest.mark.parametrize('maximum,forward', [(.016, 0), (0, 0), (.015, .011), (.015, -.01)])
def test_diagnostic_range_cannot_be_expanded(params, maximum, forward):
    with pytest.raises(ValueError):
        module.color_plane_translation([120, 160], [150, 155], .15, [320, 240], params, maximum, forward)
