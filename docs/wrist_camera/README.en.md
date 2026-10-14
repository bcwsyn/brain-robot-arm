# Single wrist-mounted Gemini 2: mounting and cup-vision reproduction

This version uses one moving wrist RGB-D camera for every visual input: RGB → YOLO cup mask → registered depth → image-time robot TF → diameter/world grasp point → adaptive opening and simulated force-feedback grasp. It creates no external camera in the Gazebo world.

Use the independent GitHub workspace `simulation_cup_wrist/`. The previous fixed-camera `simulation_cup_grasp/`, training `simulation_cup/`, and ball/cylinder `simulation/` releases remain available. Build one workspace at a time.

## 1. Mounting reference

![User-provided camera/gripper mounting reference](mount_reference.png)

The supplied distances are axial measurements, not Euclidean camera-to-tip distances. The nominal camera front/optical reference plane is at `gripper_base` flange `z=30.8 mm`; the model finger-tip reference is `z=135.8 mm`. Their difference is **105 mm**, while 30.8 mm implements the approximate 30 mm flange measurement. Finger geometry and the 100 mm gripper stroke are retained.

The existing finger/base connection geometry lies around `z=59.3–63 mm`, approximately `28.5–32.2 mm` ahead of the camera front, consistent with the photograph's `d2≈30 mm` root spacing.

The lateral offset `x=-55 mm, y=0` and mounting orientation remain simulation assumptions. One photograph and two axial distances do not establish six-degree-of-freedom extrinsics or the actual RGB/IR optical centres. These values are not a physical hand-eye calibration.

The [official Gemini 2 datasheet](https://www.orbbec.com/wp-content/uploads/2023/04/ORBBEC_Datasheet_Gemini-2-3.pdf) supplies the 90×25×30 mm body, 97 g mass, and 0.15–10 m depth range. The simulated registered RGB-D view uses 640×480 RGB with approximately 63° horizontal FOV; depth is aligned to this RGB view rather than assigning the native 91° IR FOV to RGB. Active stereo processing, distortion and the vendor's D2C implementation are not reproduced.

Gazebo and MoveIt share `src/piper_description/urdf/gemini2_wrist_camera.xacro`, including the camera collision envelope. Optical `+Z` points towards the fingers. Joint feedback supplies the moving camera TF.

## 2. Setup

The environment remains Ubuntu 22.04.5, ROS 2 Humble, Gazebo Classic 11, MoveIt 2, system Python 3.10 and the private CPU vision environment. See the [simulation prerequisites](../simulation/README.en.md) and [vision setup guide](../cup_simulation/README.en.md). Gazebo depth rendering still requires a working graphics environment, including for headless runs.

```bash
git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation_cup_wrist
bash scripts/build_simulation.sh
bash scripts/setup_cup_vision_env.sh
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 -s scripts/verify_wrist_camera_model.py
```

For an existing clone, first run `git pull --ff-only` at the repository root. Local development uses `/home/young1x/robot_projects/piper_robot/simulation`. Deactivate Conda and use a fresh terminal without another workspace overlay. The final verification command expands URDFs and checks geometry/optical coordinates without commanding motion. It writes a new `validation/wrist_model_TIMESTAMP/` directory.

The unchanged weights are `models/cup_yolov8n_seg_v2.pt`, SHA-256 `8f7afc15dd047edabc3fc0459e539e11220b19adbcc28c2da955aa07043cbeef`.

## 3. Visual reproduction

Quit any old cup simulator using `Q`; this entry uses localhost ROS domain 85 and Gazebo port 11485.

```bash
bash scripts/run_cup_grasp_sim.sh --seed 20261015
```

Startup loads Gazebo, MoveIt and the hollow stepped cup, then plans a slow, collision-checked observation move to `[-0.27, 0, 0, 0, 0.44, 0] rad`. This is a fixed workspace observation configuration, independent of Gazebo cup coordinates. The grasp executor starts afterward. Wait for `[就绪]` (ready).

Inspect the camera housing beside the gripper in Gazebo/RViz. RViz's `Gemini 2 Wrist Camera` shows its raw RGB; `Cup Detection and Grip Force` shows segmentation on the same camera image. The view moves with the arm.

![RViz mounting and raw wrist image](wrist_rviz.png)

![Wrist detection panel at the observation configuration](wrist_force.png)

Enter keys in the launching terminal, without Enter:

| Key | Action |
| --- | --- |
| `S` | Execute one wrist-vision-guided cup pick-and-place |
| `1` / `2` | Choose placement A/B while ready |
| `R` | Recreate this session and return to the observation configuration |
| `X` | Request a stop during grasp execution |
| `Q` / `Ctrl+C` | Exit and clean up owned processes |

Try ready → `S` → completion → `R` → ready → `Q`. A completed grasp returns to zero; resetting re-enters the observation configuration.

The 105 mm camera-to-tip spacing is shorter than the 150 mm depth minimum. Close-range depth can therefore become invalid and fingers can occlude the cup. The executor locks a consistent mask/depth/TF/diameter/target packet while observing from farther away, then uses that packet and ongoing force feedback. A retained displayed diameter is the last valid estimate, not a new close-range measurement.

## 4. Verification and scope

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
colcon test --packages-select brain_robot_pick_place
colcon test-result --test-result-base build/brain_robot_pick_place --verbose
bash scripts/run_cup_grasp_sim.sh --headless --seed 20261015 --batch-trials 1
```

The last command automatically moves the simulated arm. New evidence appears in `log/visual_sim/cup-TIMESTAMP/`, including scope/source hashes, events, physical acceptance results, node logs and locked RGB-D/mask/TF frames. The vision frame must be `wrist_camera_optical_frame`; the generated world must contain no `cup_observer` model.

Actual results and retained evidence are recorded in the [supplemental report](../stage5_wrist_camera_update.en.md). The previous fixed-camera 9/9 positive and 5/5 negative trials remain historical evidence and are not wrist-camera acceptance. The existing full-suite runner can perform additional wrist tests; all cases need fresh execution and separate results.

The complete session archive contains 1,659 individually verified files, compressed to approximately 5.8 MB. From the workspace:

```bash
sha256sum -c validation/wrist_camera_mount_20261014/archives/SHA256SUMS
mkdir -p artifacts
mkdir artifacts/wrist_evidence
tar -xzf validation/wrist_camera_mount_20261014/archives/all_wrist_sessions.tar.gz -C artifacts/wrist_evidence
```

Choose a new destination if `artifacts/wrist_evidence` already exists. Archived SDF/log files retain historical absolute paths as evidence; use the launcher to regenerate portable runtime models/world files on your machine.

RViz retains a conservative cup collision cylinder, while Gazebo and camera images show the stepped hollow model. This update covers camera mounting and visual inputs. Physical camera calibration, real-arm execution, plastic deformation and hardware force feedback remain unvalidated.
