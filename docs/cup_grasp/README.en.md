# Cup sizing and force-feedback pick-and-place: reproduction guide

This simulation connects the frozen cup segmentation model to RGB-D local-diameter estimation, conservative preopening, bilateral measured contact-force control, MoveIt motion, physical lifting/holding, placement and homing. The stage 4 five-view viewer remains a separate read-only perception replay.

## 1. Workspace and prerequisites

Local workspace: `/home/young1x/robot_projects/piper_robot/simulation`. Published workspace: `brain-robot-arm/simulation_cup_grasp`, separate from the preserved `simulation/` and `simulation_cup/` versions. Build one workspace at a time.

Validated environment: Ubuntu 22.04.5, ROS 2 Humble, Gazebo Classic 11, MoveIt 2 with OMPL, system Python 3.10 and a pinned project `.venv-yolo`. Headless depth-camera rendering still needs a graphics environment; validation used the local desktop with `DISPLAY=:0`. A display-less SSH setup is not validated.

```bash
git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation_cup_grasp
```

For an existing clone, run `git pull --ff-only` at repository root, then enter the new workspace. Do not source an older workspace install. System dependency and ROS initialization instructions are in the [simulation setup guide](../simulation/README.en.md) and [vision environment guide](../cup_simulation/README.en.md).

```bash
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1
python3 -s scripts/check_sim_environment.py
```

Deactivate Conda and use a fresh Ubuntu terminal. Resolve missing system dependencies using the linked guides; project scripts do not install system packages automatically.

## 2. Build and vision setup

Run inside the selected cup workspace:

```bash
bash scripts/build_simulation.sh
bash scripts/setup_cup_vision_env.sh
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
colcon test --packages-select brain_robot_pick_place
colcon test-result --test-result-base build/brain_robot_pick_place --verbose
sha256sum models/cup_yolov8n_seg_v2.pt
```

The build covers seven local packages. Vision setup installs only in `.venv-yolo`, using Torch 2.6.0+cpu, torchvision 0.21.0+cpu and pinned `config/cup_vision_requirements.txt`. No retraining or GPU is required. Model SHA-256: `8f7afc15dd047edabc3fc0459e539e11220b19adbcc28c2da955aa07043cbeef`.

Core results are 91 aggregate checks, zero failures/errors/skips: 81 algorithm/bridge cases and 10 CTest targets. Broader vendor copyright/style checks have 74 aggregate failures, preserved with evidence that their sources match stage 4. Core success must not be described as every upstream check passing.

## 3. Visual reproduction

```bash
bash scripts/run_cup_grasp_sim.sh --seed 20261015
```

Wait for the five startup steps and the ready message. Gazebo and RViz show the arm, physical cup and fixed RGB-D image. A separate large “Cup Detection and Grip Force” panel shows segmentation, measured opening and left/right force in N; move the panel as needed.

**Type keys in the launching terminal, not in Gazebo/RViz. No Enter is needed.**

| Key | Action |
| --- | --- |
| `1` / `2` | Select placement A (0.43, 0.12) or B (0.44, 0.16) m while ready |
| `S` | Start one camera-sized physical pick-and-place |
| `R` | Recreate this simulation with the next randomized start after completion/stop; wait for startup again |
| `X` | Stop arm motion and freeze jaw commands; bounded overload relief can continue |
| `Q` / `Ctrl+C` | Exit and clean up only owned processes |

Recommended sequence: ready → `1` → `S` → completed → `R` → ready → `2` → `S` → completed → `Q`. Changing zones, resetting or starting again during motion is rejected. After a fault/stop, use `R` before another attempt.

For the 75 mm specimen, estimated diameter is about 75 mm and preopening about 83 mm. Measured closed opening stays near the body diameter; pad forces settle within 2.5–3.5 N. Commanded opening can be smaller than measured opening to generate position-PID preload; this does not mean the rigid cup has been compressed to the commanded diameter.

Acceptance requires actual lift, at least three simulation seconds of holding, transfer, physical release/settling and homing. After lift or occlusion, upright-on-table perception may reject new frames: the executor uses its preapproach locked packet while force feedback continues, and the display retains the latest valid sizing. This is not general moving-object tracking.

Full stack recreation on `R` avoids the observed Gazebo heap error during hot deletion of the compound cup. Planned resets do not retry failed motion.

## 4. Other diameters and automatic checks

```bash
bash scripts/run_cup_grasp_sim.sh --diameter-mm 55 --seed 20261016
bash scripts/run_cup_grasp_sim.sh --diameter-mm 85 --seed 20261017
```

Run sequentially and exit the previous session first. These options change scene truth only, not the perception input. Specimens remain 200 mm tall, with mouth diameter 84% of body diameter, assumed mass 80 g and wall thickness 2 mm. Validated diameters are 55/75/85 mm; accepting a CLI range does not prove every diameter works. Diameter plus uncertainty margin and 6 mm clearance must fit the 100 mm stroke.

```bash
bash scripts/run_cup_grasp_sim.sh --headless --seed 20261015 --batch-trials 1
python3 scripts/verify_cup_grasp_suite.py --case all
```

The full frozen suite runs nine physical positives across three diameters and five fault/rejection cases, sequentially. It stops at the first failed case and retains all data. Use `--case main`, `55` or `85` for a single group. Results, frozen source hashes, plan and console logs are written to a fresh `validation/cup_grasp/acceptance_TIMESTAMP/` directory.

## 5. Fault cases

```bash
python3 scripts/verify_cup_grasp_suite.py --case miss
python3 scripts/verify_cup_grasp_suite.py --case feedback-loss
python3 scripts/verify_cup_grasp_suite.py --case overforce
python3 scripts/verify_cup_grasp_suite.py --case stop
python3 scripts/verify_cup_grasp_suite.py --case oversize
```

Missed capture must prevent lifting. Feedback loss and a synthetic 6 N signal are injected during lifting of an already-held cup and must stop arm motion. The synthetic overload is explicitly labeled and is not a measured physical overload. Stop cancels mid-lift. A 105 mm specimen must be rejected by visual sizing before the grasp executor launches. Injection services reject normal-session requests by default.

Internal negative motion sessions normally exit with code 1 because pick-and-place was aborted. The suite checks the expected fault, absence of completion and settled joint drift before determining negative-test success; return code alone is insufficient.

## 6. Evidence and troubleshooting

Each `log/visual_sim/cup-TIMESTAMP/` contains `session.json` (object/joint/force/opening traces and metrics), `events.jsonl`, node logs, generated scene/task configuration, source snapshots/hashes and `locked_frames/` with exact image-time RGB, registered depth, mask, intrinsics, camera extrinsics, estimate and model hash.

Inspect the last fault and corresponding logs. Preopening failure requires fresh-packet/trajectory checks. Lost-object/stale-feedback failure requires force/contact age and actual-height checks. Incomplete Cartesian paths are planning refusals; do not bypass collision checking. Run the environment checker for startup failures. If port 11485 is occupied, quit the existing session with `Q`; do not kill unrelated processes.

Published sessions are preserved in split archives; the archive instructions and stage report explain restoration. Stage 4 training archives remain in `simulation_cup/validation/cup_vision/archives/` and previous versions are preserved.

## 7. Scope

This is rigid hollow-cup simulation with a fixed calibrated camera, z=0 tabletop, one upright opaque empty cup, ideal arm gravity compensation, simplified pads and assumed friction/contact parameters. It does not validate plastic deformation/crushing, real force or camera calibration, multiple cups, water-filled transfer or brain-computer control.

The 100 mm stroke matches the user-specified large gripper; other dynamic/contact parameters are not factory measurements. SDK effort/torque must not be interpreted directly as this contact-force quantity in N. The next stage needs real images, camera/arm calibration, the actual gripper feedback interface and supervised physical testing.
