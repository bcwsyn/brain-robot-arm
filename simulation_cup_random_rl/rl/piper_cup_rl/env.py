"""Physical state-input goal-conditioned Piper cup environment (no ROS/hardware).

Object truth is deliberately exposed for first-stage state-policy research.
This environment does not claim wrist-image control or Gazebo transfer.
"""
import math
from pathlib import Path
import random

import gymnasium as gym
from gymnasium import spaces
import mujoco
import numpy as np

from .task_sampling import TaskRegion

WS = Path(__file__).resolve().parents[2]


def orientation(yaw, tilt=1.2):
    # Same RPY convention as the Gazebo executor: (0, pi-tilt, yaw).
    p = math.pi-tilt
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(p), math.sin(p)
    return np.array([[cy*cp, -sy, cy*sp], [sy*cp, cy, sy*sp], [-sp, 0., cp]])


class PiperCupEnv(gym.Env):
    metadata = {'render_modes': ['rgb_array'], 'render_fps': 25}

    def __init__(self, render_mode=None, max_episode_steps=2000, randomize_dynamics=False):
        self.render_mode = render_mode
        self.max_episode_steps = max_episode_steps
        self.randomize_dynamics = randomize_dynamics
        self.model = mujoco.MjModel.from_xml_path(str(WS/'rl/assets/piper_cup.xml'))
        self.data = mujoco.MjData(self.model)
        self.ik_data = mujoco.MjData(self.model)
        self.arm_q = np.array([self.model.joint(f'joint{i}').qposadr[0] for i in range(1, 7)])
        self.arm_v = np.array([self.model.joint(f'joint{i}').dofadr[0] for i in range(1, 7)])
        self.jaw_q = np.array([self.model.joint(f'joint{i}').qposadr[0] for i in (7, 8)])
        self.cup_q = self.model.joint('cup_free').qposadr[0]
        self.cup_v = self.model.joint('cup_free').dofadr[0]
        self.cup_id = self.model.body('cup').id
        self.tcp_id = self.model.site('tcp').id
        self.jaw_bodies = [self.model.body('link7').id, self.model.body('link8').id]
        self.ranges = np.array([self.model.joint(f'joint{i}').range for i in range(1, 7)])
        self.base_mass = self.model.body_mass[self.cup_id]
        self.base_inertia = self.model.body_inertia[self.cup_id].copy()
        self.base_friction = self.model.geom_friction.copy()
        self.renderer = None
        self.action_space = spaces.Box(-1., 1., shape=(4,), dtype=np.float32)
        self.observation_space = spaces.Dict({
            'observation': spaces.Box(-np.inf, np.inf, shape=(33,), dtype=np.float32),
            'achieved_goal': spaces.Box(-np.inf, np.inf, shape=(7,), dtype=np.float32),
            'desired_goal': spaces.Box(-np.inf, np.inf, shape=(7,), dtype=np.float32)})
        self.region = TaskRegion()
        self.reset_done = False

    def inverse_kinematics(self, target, rotation, seed, iterations=60):
        scratch = self.ik_data
        scratch.qpos[:] = self.data.qpos
        scratch.qpos[self.arm_q] = seed
        jp, jr = np.zeros((3, self.model.nv)), np.zeros((3, self.model.nv))
        for _ in range(iterations):
            mujoco.mj_forward(self.model, scratch)
            current_r = scratch.site_xmat[self.tcp_id].reshape(3, 3)
            error_p = target-scratch.site_xpos[self.tcp_id]
            error_r = .5*sum(np.cross(current_r[:, i], rotation[:, i]) for i in range(3))
            if np.linalg.norm(error_p) < .0008 and np.linalg.norm(error_r) < .01:
                return scratch.qpos[self.arm_q].copy(), True
            mujoco.mj_jacSite(self.model, scratch, jp, jr, self.tcp_id)
            jac = np.vstack((jp[:, self.arm_v], .15*jr[:, self.arm_v]))
            error = np.r_[error_p, .15*error_r]
            delta = jac.T@np.linalg.solve(jac@jac.T+.0001*np.eye(6), error)
            scratch.qpos[self.arm_q] = np.clip(scratch.qpos[self.arm_q]+np.clip(delta, -.12, .12),
                                              self.ranges[:, 0]+.002, self.ranges[:, 1]-.002)
        return scratch.qpos[self.arm_q].copy(), False

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        options = options or {}
        task = self.region.sample(random.Random(int(self.np_random.integers(0, 2**32))))
        for key in ('start_xy', 'goal_xy'):
            if key in options:
                task[key] = list(options[key])
        self.region.validate_goal(task['goal_xy'])
        start = np.asarray(task['start_xy'], dtype=float)
        if start.shape != (2,) or not np.isfinite(start).all() or not (
                .38 <= start[0] <= .42 and -.12 <= start[1] <= -.08):
            raise ValueError('Start outside the bounded tabletop region')
        mujoco.mj_resetData(self.model, self.data)
        self.model.body_mass[self.cup_id] = self.base_mass
        self.model.body_inertia[self.cup_id] = self.base_inertia
        self.model.geom_friction[:] = self.base_friction
        if self.randomize_dynamics:
            scale = self.np_random.uniform(.8, 1.2)
            self.model.body_mass[self.cup_id] *= scale
            self.model.body_inertia[self.cup_id] *= scale
            self.model.geom_friction[:, 0] *= self.np_random.uniform(.8, 1.2)
        mujoco.mj_setConst(self.model, self.data)
        # Reset alone initializes poses; step never teleports or attaches the cup.
        self.data.qpos[self.cup_q:self.cup_q+7] = [*start, .1005, 1., 0., 0., 0.]
        self.yaw = math.atan2(start[1], start[0])
        self.target_tcp = np.r_[start, .22]
        self.data.qpos[self.jaw_q] = [.045, -.045]
        mujoco.mj_forward(self.model, self.data)
        candidate, reachable = self.inverse_kinematics(self.target_tcp, orientation(self.yaw),
                                                       np.array([self.yaw, 1., -1.2, 0., 1., 0.]), 180)
        if not reachable:
            raise RuntimeError('Initial pregrasp IK unavailable; reject reset')
        self.data.qpos[self.arm_q] = candidate
        self.data.ctrl[:6] = candidate
        self.commanded_opening = .09
        self.data.ctrl[6:] = [.045, -.045]
        self.data.qvel[:] = 0.
        mujoco.mj_forward(self.model, self.data)
        for _ in range(50):
            mujoco.mj_step(self.model, self.data)
        self.goal = np.array([*task['goal_xy'], .1005, 0., 0., .100, 1.], dtype=np.float32)
        self.model.site_pos[self.model.site('goal').id] = [*task['goal_xy'], .001]
        self.initial_cup_z = float(self.data.xpos[self.cup_id, 2])
        self.steps, self.ever_lifted, self.settle_steps = 0, False, 0
        self.peak_force_n = np.zeros(2)
        self.hard_fault = ''
        self.reset_done = True
        self.task = task
        return self._observation(), self._info()

    def forces_and_collisions(self):
        forces = np.zeros(2)
        bad_contact = False
        contact_force = np.zeros(6)
        for i in range(self.data.ncon):
            contact = self.data.contact[i]
            b1, b2 = self.model.geom_bodyid[[contact.geom1, contact.geom2]]
            if self.cup_id in (b1, b2):
                other = b2 if b1 == self.cup_id else b1
                if other in self.jaw_bodies:
                    mujoco.mj_contactForce(self.model, self.data, i, contact_force)
                    forces[self.jaw_bodies.index(other)] += max(0., contact_force[0])
                elif other != 0:
                    bad_contact = True
            elif b1 != 0 and b2 != 0:
                # Parent-child contacts are excluded by MuJoCo; remaining robot
                # self contacts are reported instead of silently ignored.
                bad_contact = True
            elif (b1 == 0 or b2 == 0) and max(b1, b2) not in (self.model.body('base_link').id,):
                bad_contact = True
        return forces, bad_contact

    def _achieved(self):
        cup = self.data.xpos[self.cup_id]
        tilt = math.acos(np.clip(self.data.xmat[self.cup_id].reshape(3, 3)[2, 2], -1., 1.))
        opening = self.data.qpos[self.jaw_q[0]]-self.data.qpos[self.jaw_q[1]]
        speed = np.linalg.norm(self.data.qvel[self.cup_v:self.cup_v+3])
        # Pose, tilt, speed, actual release opening and ever-lifted indicator.
        return np.r_[cup, tilt, speed, opening, float(self.ever_lifted)].astype(np.float32)

    def _observation(self):
        force, _ = self.forces_and_collisions()
        tcp = self.data.site_xpos[self.tcp_id]
        achieved = self._achieved()
        state = np.r_[self.data.qpos[self.arm_q], self.data.qvel[self.arm_v], tcp,
                      achieved[:3], achieved[:3]-tcp, self.data.qpos[self.jaw_q], force,
                      achieved[3:5], math.sin(self.yaw), math.cos(self.yaw),
                      float(self.ever_lifted), self.commanded_opening, .075, .200]
        return dict(observation=state.astype(np.float32), achieved_goal=achieved, desired_goal=self.goal.copy())

    @staticmethod
    def compute_reward(achieved_goal, desired_goal, info):
        a, g = np.asarray(achieved_goal), np.asarray(desired_goal)
        # Goal-dependent fields are recomputed from the supplied goal for HER.
        distance = np.linalg.norm(a[..., :3]-g[..., :3], axis=-1)
        placed = ((distance < .015) & (a[..., 3] < .12) & (a[..., 4] < .025)
                  & (a[..., 5] > .083) & (a[..., 6] > .5))
        if isinstance(info, dict):
            fault = bool(info.get('hard_fault'))
        else:
            fault = np.array([bool(item.get('hard_fault')) for item in info]).reshape(distance.shape)
        # With -1 per step, an early collision must not be cheaper than a long
        # successful episode. At gamma=.99 the infinite step cost is -100.
        # Preserve this goal-independent penalty when HER relabels goals.
        return np.where(fault, -200., np.where(placed, 0., -1.)).astype(np.float32)

    def _info(self):
        a = self._achieved()
        force, contact = self.forces_and_collisions()
        return dict(is_success=bool(self.settle_steps >= 10 and not self.hard_fault),
                    placement_error_m=float(np.linalg.norm(a[:3]-self.goal[:3])),
                    cup_tilt_rad=float(a[3]), cup_speed_m_s=float(a[4]),
                    ever_lifted=bool(self.ever_lifted), force_n=force.tolist(), collision=bool(contact),
                    peak_force_n=self.peak_force_n.tolist(),
                    hard_fault=self.hard_fault, sim_time_s=float(self.data.time),
                    observation_source='simulation_truth_state_not_wrist_vision', task=self.task)

    def step(self, action):
        if not self.reset_done:
            raise RuntimeError('Call reset before step or after episode completion')
        action = np.asarray(action, dtype=float)
        if action.shape != (4,) or not np.isfinite(action).all() or np.any(np.abs(action) > 1.00001):
            raise ValueError('Action must be a finite four-element vector in [-1,1]')
        previous_tcp, previous_yaw = self.target_tcp.copy(), self.yaw
        self.target_tcp = np.clip(self.data.site_xpos[self.tcp_id]+action[:3]*.004, [.30, -.20, .11], [.50, .22, .38])
        # Upright-cup prior: horizontal jaw axis, fixed tilt, radial tool yaw.
        # The policy learns XYZ and gripping; arbitrary 6-D orientation is out of scope.
        self.yaw = math.atan2(self.target_tcp[1], self.target_tcp[0])
        joints, reachable = self.inverse_kinematics(self.target_tcp, orientation(self.yaw), self.data.qpos[self.arm_q], 25)
        if not reachable:
            self.target_tcp, self.yaw = previous_tcp, previous_yaw
            joints = self.data.qpos[self.arm_q].copy()
        # Bound each joint's requested change; physics executes the motion.
        start_joints = self.data.qpos[self.arm_q].copy()
        delta = joints-start_joints
        # Scale the complete vector to preserve IK direction while enforcing
        # .3 rad/s; independent joint clipping distorts the requested TCP path.
        delta *= min(1., .012/max(1e-12, np.max(np.abs(delta))))
        joint_goal = start_joints+delta
        for tick in range(20):
            self.data.ctrl[:6] = start_joints+(joint_goal-start_joints)*(tick+1)/20
            force, collision = self.forces_and_collisions()
            self.peak_force_n = np.maximum(self.peak_force_n, force)
            if max(force) > 5.:
                self.hard_fault = 'OVERFORCE'
                self.commanded_opening = min(.1, self.commanded_opening+.0001)
            elif action[3] > .1:
                # One owner: continuous grip request, bounded force-limited closure.
                low, high = min(force), max(force)
                if high > 3.5:
                    self.commanded_opening += min(.00004, (high-3.5)*.000004)
                elif low < 2.5:
                    self.commanded_opening -= .00004
            elif action[3] < -.1:
                self.commanded_opening += .00008
            self.commanded_opening = float(np.clip(self.commanded_opening, 0., .1))
            self.data.ctrl[6:] = [self.commanded_opening/2, -self.commanded_opening/2]
            mujoco.mj_step(self.model, self.data)
            if collision:
                self.hard_fault = self.hard_fault or 'COLLISION'
        self.steps += 1
        lift_force, _ = self.forces_and_collisions()
        self.ever_lifted |= (self.data.xpos[self.cup_id, 2] > self.initial_cup_z+.05
                            and min(lift_force) >= 1.)
        achieved = self._achieved()
        immediate_success = bool(self.compute_reward(achieved, self.goal, {}) == 0.)
        force, _ = self.forces_and_collisions()
        immediate_success &= max(force) < .1
        self.settle_steps = self.settle_steps+1 if immediate_success else 0
        if achieved[2] < .07 or achieved[3] > .5:
            self.hard_fault = self.hard_fault or 'DROP_OR_TIP'
        if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all():
            self.hard_fault = 'NONFINITE_PHYSICS'
        terminated = bool(self.hard_fault or self.settle_steps >= 10)
        truncated = self.steps >= self.max_episode_steps and not terminated
        observation, info = self._observation(), self._info()
        reward = float(self.compute_reward(observation['achieved_goal'], self.goal, info))
        if terminated or truncated:
            self.reset_done = False
        return observation, reward, terminated, truncated, info

    def render(self):
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=480, width=640)
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [.3, 0., .15]
        camera.distance, camera.azimuth, camera.elevation = 1., 130., -25.
        self.renderer.update_scene(self.data, camera=camera)
        return self.renderer.render().copy()

    def close(self):
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
