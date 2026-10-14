"""Exercise the real capture encoder helper without starting ROS or a camera."""
import ast
from pathlib import Path
import cv2
import numpy as np


def helper(limit):
    source = Path(__file__).with_name('capture_scale_frames.py')
    tree = ast.parse(source.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'save_image_with_budget')
    namespace = {'cv2': cv2, 'saved_bytes': 0, 'saved_sizes': {}, 'max_bytes': limit,
                 'image_budget_exhausted': False}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace


def test_rejects_oversized_image_before_write(tmp_path):
    n = helper(1)
    path = tmp_path / 'rgb.png'
    assert not n['save_image_with_budget'](path, np.zeros((4, 4, 3), np.uint8))
    assert not path.exists() and n['saved_bytes'] == 0 and n['image_budget_exhausted']


def test_png_preserves_original_pixels(tmp_path):
    n = helper(1024)
    pixels = np.full((4, 4, 3), 128, np.uint8)
    path = tmp_path / 'rgb.png'
    assert n['save_image_with_budget'](path, pixels)
    assert np.array_equal(cv2.imread(str(path)), pixels)
    assert n['saved_bytes'] == path.stat().st_size <= 1024


def test_same_path_is_not_double_counted(tmp_path):
    n = helper(1024)
    path = tmp_path / 'depth.png'
    pixels = np.zeros((4, 4), np.uint16)
    assert n['save_image_with_budget'](path, pixels)
    initial = n['saved_bytes']
    assert n['save_image_with_budget'](path, pixels)
    assert n['saved_bytes'] == initial


def test_native_uint16_depth_is_preserved(tmp_path):
    n = helper(1024)
    pixels = np.array([[0, 150], [1000, 65535]], dtype=np.uint16)
    path = tmp_path / 'depth_raw.png'
    assert n['save_image_with_budget'](path, pixels)
    decoded = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    assert decoded.dtype == np.uint16 and np.array_equal(decoded, pixels)


def test_next_image_cannot_overrun_total_budget(tmp_path):
    pixels = np.zeros((4, 4, 3), np.uint8)
    _, encoded = cv2.imencode('.png', pixels)
    n = helper(int(encoded.size))
    first, second = tmp_path/'first.png', tmp_path/'second.png'
    assert n['save_image_with_budget'](first, pixels)
    assert not n['save_image_with_budget'](second, pixels)
    assert not second.exists() and n['saved_bytes'] == encoded.size
