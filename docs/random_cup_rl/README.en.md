# Random-start/random-goal cup manipulation and RL reproduction

Two independent paths are provided: the Gazebo wrist-RGB-D/MoveIt/force-control baseline, and a MuJoCo state-input SAC+HER training environment. Their results must be reported separately. A successful scripted rollout verifies the environment, not the learned policy.

## 1. Checkout and prerequisites

Repository: [bcwsyn/brain-robot-arm](https://github.com/bcwsyn/brain-robot-arm). This stage lives in `simulation_cup_random_rl/`; earlier workspaces remain available.

```bash
git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation_cup_random_rl
```

The local development workspace is `/home/young1x/robot_projects/piper_robot/simulation`. Run subsequent commands from that workspace. Use Ubuntu 22.04, ROS 2 Humble and Python 3.10; deactivate Conda and do not source the real-robot or another release workspace.

Keep all commands in the new workspace; use the older guide only for dependency prerequisites. Gazebo prerequisites are documented in the [wrist-camera guide](../wrist_camera/README.en.md). RL needs only its private Python environment at runtime.

## 2. Visual Gazebo baseline

```bash
bash scripts/build_simulation.sh
bash scripts/setup_cup_vision_env.sh
bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --random-goal
```

Wait for READY, press **S** in the launch terminal to execute, **R** after completion to rebuild a new random scene, **X** to stop, and **Q** to exit. In random mode, keys 1/2 refer to the same sampled destination. The destination is locked during execution.

The opaque empty cup has a 75 mm diameter/160 mm high body and a 63 mm outer diameter/40 mm high mouth. Its assumed mass is 80 g and wall thickness 2 mm. The single wrist Gemini2 retains the 19.81° inward tilt, 105 mm axial tip spacing and 150 mm minimum usable depth. No external perception camera is added.

World-frame bounds in metres: start X `[0.38,0.42]`, Y `[-0.12,-0.08]`; goal X `[0.42,0.44]`, Y `[0.10,0.16]`. Both locations are on one horizontal tabletop. This conservative region does not establish reachability across the complete arm workspace.

A user-specified world destination is also supported:

```bash
bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --goal-xy 0.43 0.14
```

This is coordinate entry, not image-click selection. Out-of-region and nonfinite coordinates are rejected before startup.

## 3. Automated baseline acceptance

```bash
bash scripts/run_cup_grasp_sim.sh --headless --seed 2026101510 --batch-trials 20 --random-goal
```

Headless omits windows but still needs rendering for the Gazebo wrist camera. Rebuilding each trial can take tens of minutes. Do not run another instance on domain85/port11485.

Replace the session timestamp with the actual directory printed at startup:

```bash
python3 scripts/analyze_random_cup_session.py log/visual_sim/cup-ACTUAL-TIMESTAMP \
  --output validation/my_random_baseline.json
```

The complete start/goal plan is saved before motion. Sessions preserve source snapshots, component logs, force records and locked RGB-D frames. Independent analysis compares requested origins and destinations with measured object motion. Stop at the first failure; never silently retry a moving trial or discard failures.

Acceptance includes at least50 mm actual lift, at least3 simulated seconds holding, bilateral2.5–3.5 N holding forces, settled release without jaw contact, tilt below0.12 rad,3D destination error below30 mm and home-joint error below0.02 rad. Small measured errors do not change the predefined30 mm gate.

## 4. Private RL environment and current model

```bash
bash scripts/setup_cup_rl_env.sh
```

Only `.venv-rl/` is populated; `.venv-yolo/` and system packages are unchanged. Pins: CPU Torch2.6.0, Gymnasium1.1.1, Stable-Baselines3 2.6.0, MuJoCo3.3.2. A full environment inventory is preserved with the stage evidence.

The release includes a portable `rl/assets/piper_cup.xml` with relative mesh paths. To regenerate it from the current ROS description:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
.venv-rl/bin/python -s scripts/build_cup_rl_model.py
```

Build the ROS workspace first so xacro can find its packages. The converter uses the current physical-pad/wrist-camera URDF and preserves kinematics, inertial properties, limits and the100 mm gripper. It does not use legacy MJCF or `mujoco_py` control code. The hollow stepped shell is an approximation; MuJoCo contacts are not Gazebo-equivalent or hardware-calibrated.

## 5. Validate and train

```bash
.venv-rl/bin/python -s -m pytest -q rl/tests
.venv-rl/bin/python -s scripts/verify_cup_rl_env.py \
  --output validation/my_rl_environment --episodes 3 --seed 100
bash scripts/run_cup_rl.sh --steps 5000 --seed 20261015 \
  --output artifacts/cup_rl/my_smoke
```

Output directories must be new. Environment validation uses a scripted controller; training actually collects SAC+HER experience and runs optimization.5000 steps are a pipeline check, not convergence evidence.

Observations contain33 state scalars,7 achieved-goal scalars and7 desired-goal scalars, including simulator cup truth and bilateral contact forces. No camera pixels enter the policy. Reset randomizes cup and goal locations, then initializes the arm above that cup using IK. Learning the initial observation/search motion is not yet included.

Actions are XYZ increments up to±4 mm and a jaw open/close/hold request. A1.2 rad tilt and radial yaw are imposed as an upright-cup prior. This is not arbitrary6D orientation control. Each action advances20×2 ms physics steps, yielding25 Hz. Joint requests are proportionally limited to0.3 rad/s. Jaw commands are bounded by100 mm stroke,2.5–3.5 N target forces and5 N overforce termination.

Success requires a bilateral-contact lift of at least50 mm, then upright settled release within15 mm of the destination, without pad contact, continuously for10 steps. Step never teleports or rigidly attaches the cup. Collision, tip/drop and overforce terminate;2000 steps truncate an episode. Normal steps receive−1, settled placement0, and faults−200. HER retains goal-independent fault information; an early failure cannot earn a cheaper episode. A short run does not establish convergence.

Longer training and optional dynamics randomization:

```bash
bash scripts/run_cup_rl.sh --steps 200000 --seed 20261015 \
  --output artifacts/cup_rl/my_long_run --randomize-dynamics
```

Mass and friction vary by±20%; cup dimensions remain fixed. Choose the eventual training budget from measured speed and learning curves.

## 6. Independent evaluation and recovery

```bash
.venv-rl/bin/python -s scripts/evaluate_cup_rl.py \
  --run artifacts/cup_rl/my_smoke --episodes 20 --seed 2026101600 \
  --output validation/my_policy_evaluation
```

Evaluation uses separate seeds, counts all failures and saves termination reasons, errors, tasks and complete trajectories. It verifies both model and environment-source hashes. A0/20 result is evidence too, not grounds to show only selected successes.

Training saves `model.zip`, `replay_buffer.pkl`, configuration, results, episode logs and source snapshots/hashes. Additional checkpoints are saved every10000 steps. Ctrl+C attempts to preserve the current model and buffer. Resume into a new output directory:

```bash
bash scripts/run_cup_rl.sh --steps 3000 --seed 20261015 \
  --resume artifacts/cup_rl/my_smoke --output artifacts/cup_rl/my_resumed
```

Keep the same model, environment source and randomization setting; add `--randomize-dynamics` when resuming such a run. This restores weights and experience, with a new environment reset; it does not promise bit-identical continuation of physical state.

## 7. Visual trajectory replay

```bash
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/my_rl_environment --episode 1
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/my_policy_evaluation --episode 1
```

Close the viewer to exit. Replay displays recorded states and is not another physical acceptance trial. The third-person monitor is not a perception input. Export recorded video, optionally from the wrist view:

```bash
MUJOCO_GL=egl .venv-rl/bin/python -s scripts/replay_cup_rl.py \
  validation/my_rl_environment --episode 1 --video validation/scripted_replay.mp4
MUJOCO_GL=egl .venv-rl/bin/python -s scripts/replay_cup_rl.py \
  validation/my_rl_environment --episode 1 --wrist --video validation/wrist_replay.mp4
```

EGL requires a working EGL implementation. If unavailable, use the desktop viewer without changing system graphics configuration. Wrist replay is not a Gemini2 depth-calibration or image-policy result.

See the [stage report](../stage6_random_cup_rl_acceptance.en.md) and [Chinese guide](README.zh-CN.md) for results and retained evidence.

## 8. Restore all stage data

GitHub includes six parts of at most45 MiB, not the single large local tar.gz. Reassemble and verify every file into a new directory:

```bash
python3 scripts/restore_random_rl_stage.py \
  --archive-directory validation/stage6_random_rl/archives --output recovered_stage6
.venv-rl/bin/python -s scripts/evaluate_cup_rl.py \
  --run recovered_stage6/artifacts/cup_rl/stage6_final_policy --episodes 20 --seed 2026101600 \
  --output validation/recovered_policy_evaluation
```

The frozen policy scored0/20; reproduction verifies the pipeline and evidence, not a usable manipulation policy. Prototypes remain archived separately; mismatched old model/environment sources are rejected.
