"""Meaningful control-interface, reset, kinematics, reward and safety checks."""
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[2]/'scripts'))
from piper_cup_rl.env import PiperCupEnv
from piper_cup_rl.task_sampling import make_plan
from build_cup_rl_model import rotation, generate


@pytest.fixture
def env():
    environment = PiperCupEnv()
    yield environment
    environment.close()


def test_random_plan_reproducible_and_both_positions_vary():
    a = make_plan(10, 20)
    assert a == make_plan(10, 20)
    assert a != make_plan(11, 20)
    assert len({tuple(t['start_xy']) for t in a['trials']}) == 20
    assert len({tuple(t['goal_xy']) for t in a['trials']}) == 20


def test_legacy_70mm_model_cannot_be_labeled_as_100mm(tmp_path):
    root = ET.parse(Path(__file__).parents[1]/'assets/source_robot.urdf').getroot()
    root.find("joint[@name='joint7']/limit").set('upper', '.035')
    with pytest.raises(ValueError, match='100 mm'):
        generate(ET.tostring(root), tmp_path/'rejected.xml')
    assert not (tmp_path/'rejected.xml').exists()


@pytest.mark.parametrize('goal', [[float('nan'), .12], [.45, .12], [.43, .09], [.43], [.43, float('inf')]])
def test_invalid_goals_rejected_before_start(goal):
    with pytest.raises(ValueError):
        make_plan(1, 1, goal)


def test_reset_reproducibility_and_valid_state(env):
    first, _ = env.reset(seed=100)
    env.step(np.zeros(4))
    second, info = env.reset(seed=100)
    for key in first:
        assert np.array_equal(first[key], second[key])
    assert env.observation_space.contains(second)
    assert not info['collision'] and not info['is_success']


def test_current_urdf_fk_and_joint_limits_match_mjcf(env):
    root = ET.parse(Path(__file__).parents[1]/'assets/source_robot.urdf')
    rng = np.random.default_rng(42)
    for trial in range(15):
        values = {}
        for n in range(1, 9):
            joint = root.find(f"joint[@name='joint{n}']")
            limit = joint.find('limit')
            bounds = [float(limit.get('lower')), float(limit.get('upper'))]
            assert np.allclose(env.model.joint(f'joint{n}').range, bounds, atol=1e-12)
            values[f'joint{n}'] = rng.uniform(*bounds)
            env.data.qpos[env.model.joint(f'joint{n}').qposadr[0]] = values[f'joint{n}']
        mujoco.mj_forward(env.model, env.data)
        transforms = {'world': np.eye(4)}
        pending = list(root.findall('joint'))
        while pending:
            ready = [j for j in pending if j.find('parent').get('link') in transforms]
            assert ready
            for joint in ready:
                parent, child = joint.find('parent').get('link'), joint.find('child').get('link')
                origin = joint.find('origin')
                transform = np.eye(4)
                if origin is not None:
                    transform[:3, :3] = rotation(origin.get('rpy', '0 0 0'))
                    transform[:3, 3] = [float(v) for v in origin.get('xyz', '0 0 0').split()]
                motion = np.eye(4)
                if joint.get('type') != 'fixed':
                    axis = np.array([float(v) for v in joint.find('axis').get('xyz').split()])
                    q = values[joint.get('name')]
                    if joint.get('type') == 'prismatic':
                        motion[:3, 3] = axis*q
                    else:
                        x, y, z = axis
                        skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
                        motion[:3, :3] = np.eye(3)+math.sin(q)*skew+(1-math.cos(q))*skew@skew
                expected = transforms[parent]@transform@motion
                transforms[child] = expected
                body_id = env.model.body(child).id
                assert np.allclose(env.data.xpos[body_id], expected[:3, 3], atol=1e-9)
                assert np.allclose(env.data.xmat[body_id].reshape(3, 3), expected[:3, :3], atol=1e-9)
                pending.remove(joint)


def test_zero_action_steps_do_not_teleport_or_create_success(env):
    env.reset(seed=10)
    before = env.data.xpos[env.cup_id].copy()
    time_before = env.data.time
    for _ in range(30):
        obs, reward, done, timeout, info = env.step(np.zeros(4))
        assert reward == -1 and not done and not timeout
    assert env.data.time-time_before == pytest.approx(30*.04)
    assert np.linalg.norm(env.data.xpos[env.cup_id]-before) < .001
    assert not info['ever_lifted']


@pytest.mark.parametrize('action', [[0, 0, 0], [0, 0, 0, float('nan')], [0, 0, 0, 2.]])
def test_invalid_actions_leave_physics_unchanged(env, action):
    env.reset(seed=10)
    before = env.data.qpos.copy()
    with pytest.raises(ValueError):
        env.step(action)
    assert np.array_equal(before, env.data.qpos)


def test_reward_requires_lift_release_upright_and_settled_and_supports_her_batch():
    goal = np.array([.43, .12, .1, 0, 0, .1, 1])
    valid = goal.copy()
    failures = []
    for field, value in [(0, .46), (3, .2), (4, .1), (5, .075), (6, 0.)]:
        row = valid.copy()
        row[field] = value
        failures.append(row)
    a = np.vstack([valid, *failures])
    reward = PiperCupEnv.compute_reward(a, np.repeat(goal[None], len(a), axis=0), {})
    assert np.array_equal(reward, [0, -1, -1, -1, -1, -1])
    moved_goal = goal.copy(); moved_goal[0] += .04
    assert PiperCupEnv.compute_reward(valid, moved_goal, {}) == -1


def test_timeout_requires_reset_before_another_step():
    env = PiperCupEnv(max_episode_steps=1)
    try:
        env.reset(seed=10)
        _, _, done, timeout, _ = env.step(np.zeros(4))
        assert timeout and not done
        with pytest.raises(RuntimeError):
            env.step(np.zeros(4))
    finally:
        env.close()


def test_failure_penalty_survives_her_goal_relabeling_and_batching():
    achieved = np.array([.43, .12, .1, 0, 0, .1, 1])
    goal = achieved.copy()
    assert PiperCupEnv.compute_reward(achieved, goal, {'hard_fault': 'COLLISION'}) == -200
    batch = np.repeat(achieved[None], 3, axis=0)
    rewards = PiperCupEnv.compute_reward(batch, batch, [{}, {'hard_fault': 'OVERFORCE'}, {}])
    assert np.array_equal(rewards, [0, -200, 0])


def test_overforce_terminates_and_backs_off_instead_of_closing(env, monkeypatch):
    env.reset(seed=10)
    opening = env.commanded_opening
    monkeypatch.setattr(env, 'forces_and_collisions', lambda: (np.array([6., 2.]), False))
    _, _, terminated, truncated, info = env.step([0, 0, 0, 1.])
    assert terminated and not truncated and info['hard_fault'] == 'OVERFORCE'
    assert env.commanded_opening > opening
    assert info['peak_force_n'][0] == 6.


def test_a_fault_on_the_final_settling_step_cannot_count_as_success(env, monkeypatch):
    env.reset(seed=10)
    env.settle_steps = 9
    env.ever_lifted = True
    monkeypatch.setattr(env, '_achieved', lambda: env.goal.copy())
    monkeypatch.setattr(env, 'forces_and_collisions', lambda: (np.zeros(2), True))
    _, reward, terminated, _, info = env.step(np.zeros(4))
    assert terminated and reward == -200 and info['hard_fault'] == 'COLLISION'
    assert not info['is_success']


def test_dynamics_randomization_restores_same_seed_and_changes_other_seed():
    env = PiperCupEnv(randomize_dynamics=True)
    try:
        env.reset(seed=11); mass = env.model.body_mass[env.cup_id]
        env.reset(seed=11); assert env.model.body_mass[env.cup_id] == mass
        env.reset(seed=12); assert env.model.body_mass[env.cup_id] != mass
    finally:
        env.close()
