# Stage 6: Random start/goal cup baseline and RL environment

Date:2026-10-15. Scope:simulation only; release workspace `simulation_cup_random_rl/`. Builds on the [wrist-tilt report](stage5_wrist_camera_tilt_update.en.md). This stage delivers a random-task baseline and reproducible RL environment/training entry, not a converged manipulation policy.

**The random baseline, RL environment, training/recovery entry and independent release reproduction are complete. The learned policy remains unconverged at0/20.**

## 1. Task and implementation

Retain the confirmed75×160 mm body,63 mm outer diameter×40 mm mouth,200 mm overall height,100 mm gripper stroke and single inward-tilted19.81° Gemini2 wrist camera. Mass80 g and wall2 mm remain assumptions. Frozen YOLO weights and wrist-camera mounting are unchanged.

Seeded tabletop tasks randomize cup origins X380–420 mm/Y−120 to−80 mm and destinations X420–440 mm/Y100–160 mm in `world`. CLI supports random or user-specified destinations; task-time updates remain locked. This does not cover arbitrary arm poses, workspace points or6D placements.

One development origin produced duplicate cup masks. Merge only with maskIoU≥0.75 and independently fitted3D centre, diameter and height agreement within2 mm. Distinct valid cups remain ambiguous. Per-generation RGB-D evidence avoids name collisions when simulation clocks restart.

The initial20-task batch completed6 successful trials and failed on trial7 before grasp motion because a MoveIt scene response was lost;13 tasks were unattempted. Replace initial unbounded scene reads with a persistent client and2-second response waits plus bounded read-only requery. Preserve the failed batch; do not retry failed moving trials or relax acceptance gates.

## 2. Physical RL environment

Generate MuJoCo MJCF from the current simulation URDF, preserving link kinematics/inertia, limits, wrist mounting and100 mm jaws. Do not run legacy `mujoco_py` controllers or use legacy MJCF. Fifteen randomized joint configurations match independent URDF forward kinematics link by link.

The hollow stepped cup shell and contact dynamics are approximations. Ideal robot gravity compensation is retained; independent gravity/contact/friction carry the cup. Only reset initializes object pose; step neither teleports nor attaches it. MuJoCo results do not establish Gazebo or hardware policy transfer.

- Observations:33 state scalars,7 achieved-goal and7 desired-goal scalars, with simulator cup truth; no pixels.
- Actions:XYZ increments up to±4 mm and bounded gripper request; fixed1.2 rad tilt and radial yaw prior.
- Timing:20×2 ms physics steps per action,25 Hz; proportional joint-request limiting to0.3 rad/s.
- Force/stroke:2.5–3.5 N targets,5 N hard termination,100 mm maximum opening.
- Reset:random cup and goal, then IK initialization above the cup; observation/search learning remains pending.
- Success:bilateral-contact lift≥50 mm, upright low-speed release within15 mm, no pad contact, settled for10 consecutive steps.
- Failure:collision, overforce, drop/tip;2000-step time limit. Optional mass/friction randomization±20%, fixed cup dimensions.

## 3. Independent evidence

All88 ROS-core test cases in11 CTest groups pass. Independent RL checks:19/19, covering reset, model kinematics, bounds, physical stepping, HER reward batching, timeout, overforce backoff and randomization.

Frozen scripted-controller environment validation:3/3 at seeds100/101/102, errors0.666/0.548/0.533 mm, bilateral peak forces below5 N. Zero-action throughput is approximately500 steps per wall second; this excludes network optimization and active-task workload. **These are scripted environment checks, not RL success.**

Frozen SAC+HER pipeline run:seed20261015,5000 steps,2800 optimizer updates,0 successful training episodes. Independent evaluation at seeds2026101600–2026101619: **0/20**, all2000-step timeouts. Model, replay buffer, config, source snapshot and all failures are retained. The policy has not learned complete manipulation.

Resume check adds3000 steps, reaching8000 steps/5800 updates, stored separately. It verifies weight/replay recovery and is not counted as part of the frozen5000-step policy evaluation.

Frozen Gazebo batch `cup-20261015-010128-299621`, seed2026101510: **20/20** with20 distinct origins and20 distinct goals, source hashes unchanged. Keep the earlier6/7 failed batch and4-trial development success separate.

| Gazebo metric | Result |
| --- | --- |
| Maximum3D placement error | 1.331 mm; predefined gate30 mm |
| Minimum actual lift | 144.794 mm |
| Minimum holding duration | 3.150 simulated seconds |
| Bilateral holding-force range | 2.656–3.201 N |
| Maximum final tilt | 0.000527 rad |
| Maximum home-joint error | 0.000099 rad |

An independent release built all7 packages from empty build/install and passed88 core cases/11 test groups and19 RL checks. Regenerated MJCF matches the development model XML. GUI reproduction at the explicitly specified destination `(0.43,0.14)` m passes1/1, error0.900 mm, hold3.23 simulated seconds; R restores observation/detection readiness and Q exits cleanly. This is a separate trial.

![Sampled tasks and measured errors](random_cup_rl/random_baseline.png)

![Frozen short-run returns; no successful training episodes](random_cup_rl/training_curve.png)

Only4 complete training episodes were collected in5000 steps. Normal reward is−1, settled placement0 and faults−200; HER preserves fault information, and a fault on the last settling step cannot count as success. Complete successful scripted transitions are retained for later demonstration-assisted exploration. More steps alone do not guarantee convergence.

## 4. Reproduction and visualization

See the complete [English guide](random_cup_rl/README.en.md) / [中文指南](random_cup_rl/README.zh-CN.md).

```bash
bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --random-goal
bash scripts/run_cup_grasp_sim.sh --seed 2026101510 --goal-xy 0.43 0.14
```

Run one entry at a time. Wait for READY, S execute, R rebuild, Q exit.

```bash
bash scripts/setup_cup_rl_env.sh
bash scripts/run_cup_rl.sh --steps 5000 --seed 20261015 --output artifacts/cup_rl/my_smoke
.venv-rl/bin/python -s scripts/evaluate_cup_rl.py --run artifacts/cup_rl/my_smoke \
  --episodes 20 --seed 2026101600 --output validation/my_policy_evaluation
```

Recorded scripted success versus learned-policy failure:

```bash
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/stage6_random_rl/final_environment --episode 1
.venv-rl/bin/python -s scripts/replay_cup_rl.py validation/stage6_random_rl/final_policy_evaluation --episode 1
```

Replay is not another physical trial. Third-person monitoring is not a perception input; wrist-view and overview videos are retained.

![Gazebo wrist detection and feedback](random_cup_rl/gazebo_wrist_detection.png)

![Scripted MuJoCo lift, not a learned-policy success](random_cup_rl/holding.png)

The RViz green cylinder is conservative planning geometry; Gazebo appearance and the MuJoCo shell are stepped cups.

## 5. Retention, limitations and next work

Preserve every development failure, frozen batch, training prototype, checkpoint/replay buffer, resume check and held-out evaluation using per-fileSHA-256 archives and independent restore verification. Archive:10880 files,275531560 bytes combined,6 parts of at most45 MiB. Parts-only recovery verified every file SHA-256. Combined SHA-256:`a55848eceaa960ba450ee6881d2de09cfdd12387e3f91c2f2c173c8cc18820f3`. The original combined archive remains local; GitHub includes all six parts, manifest and checksums. Publication receipts are recorded separately. Earlier repository versions and parallel calibration work are preserved.

No real images or hardware are used. The RL policy uses ideal state and starts at pregrasp; wrist perception, occlusion/depth-loss state updates and real feedback integration remain pending. Duplicate-mask handling does not establish cluttered real-camera robustness.

Next:use scripted demonstrations and staged tasks to improve sparse-reward exploration; obtain learning curves across multiple seeds and frozen held-out tasks, comparing success, placement error, duration and failures with the traditional baseline. Then replace truth inputs with wrist RGB-D estimates, randomize observation error/delay and expand the validated workspace.
