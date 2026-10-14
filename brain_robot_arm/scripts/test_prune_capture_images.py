import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('image_pruner', Path(__file__).with_name('prune_capture_images.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def rows(count=20, age=100000):
    now = 1000000
    return [{'path': f'/logs/run/rgb_{i:04d}.png', 'size': 100, 'mtime_ns': int((now-age+i)*1e9)}
            for i in range(count)]


def test_no_delete_under_budget():
    selected, remaining = module.choose_deletions(rows(), set(), 3000, 1000000)
    assert selected == [] and remaining == 2000


def test_first_last_and_reference_retained():
    selected, remaining = module.choose_deletions(rows(), {'rgb_0009.png'}, 100, 1000000)
    names = {Path(r['path']).name for r in selected}
    assert names
    assert not names & {'rgb_0000.png', 'rgb_0001.png', 'rgb_0002.png',
                        'rgb_0017.png', 'rgb_0018.png', 'rgb_0019.png', 'rgb_0009.png'}
    assert remaining >= 700  # Never discard protected evidence to meet quota.


def test_recent_images_never_deleted():
    selected, remaining = module.choose_deletions(rows(age=100), set(), 100, 1000000)
    assert selected == [] and remaining == 2000


def test_separate_streams_keep_their_ends():
    data = rows() + [dict(r, path=r['path'].replace('rgb_', 'debug_')) for r in rows()]
    selected, _ = module.choose_deletions(data, set(), 100, 1000000)
    names = {Path(r['path']).name for r in selected}
    assert not names & {'rgb_0000.png', 'rgb_0019.png', 'debug_0000.png', 'debug_0019.png'}
