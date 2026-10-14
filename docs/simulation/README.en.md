# Piper Stage 3 physical simulation: download, build and run

[中文](README.zh-CN.md) · [English stage report](../stage3_physical_grasp_report.en.md) · [中文阶段报告](../第三步_物理抓取开发与验收.md)

This guide uses the independent `simulation/` directory at the repository root. It runs camera-guided physical pick-and-place for a ball and a solid cylinder. Contact and friction carry the object; opening the jaws releases it under object gravity. The existing `brain_robot_arm/` tree is the historical workspace. Run every build and launch command below from the new `simulation/` workspace.

## 1. Supported environment and scope

| Component | Requirement |
| --- | --- |
| OS | Ubuntu 22.04; validated on 22.04.5 amd64 |
| ROS | ROS 2 Humble, system Python 3.10 |
| Simulator | Gazebo Classic 11, not the Fortress/Harmonic/Jazzy Gazebo interfaces |
| Planning/control | MoveIt 2 OMPL, MoveIt Servo, ros2_control, Gazebo ROS plugins |
| Graphics | A local Ubuntu desktop with an accessible `DISPLAY` and OpenGL; RGB-D rendering needs graphics even without windows |
| Resources | The validated machine has an approximately 8 GB GPU; CUDA is not required. Build scripts limit compilation to two jobs. Runtime depends on CPU and graphics performance |

This release does not use YOLO or neural-network weights. Perception uses a red image region and RGB-D fitting of known geometry. A physical arm, CAN interface, physical camera and training dataset are not required.

Historical acceptance: 20/20 randomized physical trials per object, ten placements per A/B zone. Miss, object-loss and stop-during-lift checks passed. The two batches have separately retained software versions; do not describe them as forty trials on one binary. Simplified finger pads and ideal arm gravity compensation are explicit model assumptions; object gravity remains enabled.

## 2. Install dependencies

Use a fresh Ubuntu Bash terminal, deactivate Conda, and do not source another robot workspace. If Humble is not installed, first configure the ROS repository and install Humble following the [official Ubuntu installation guide](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html). The following commands install system dependencies on the reader's machine; launch scripts never install software automatically.

```bash
sudo apt update
sudo apt install -y \
  git build-essential cmake libopencv-dev \
  python3-colcon-common-extensions python3-rosdep \
  python3-numpy python3-opencv python3-scipy python3-yaml python3-pytest python3-tk \
  ros-humble-desktop ros-humble-moveit ros-humble-moveit-servo \
  ros-humble-gazebo-ros-pkgs ros-humble-gazebo-ros2-control \
  ros-humble-ros2-control ros-humble-ros2-controllers \
  ros-humble-rmw-fastrtps-cpp ros-humble-cv-bridge ros-humble-xacro \
  ros-humble-ament-cmake-gtest ros-humble-ament-cmake-pytest
```

Check the Humble setup file, then clone:

```bash
test -f /opt/ros/humble/setup.bash
cd ~
git clone https://github.com/bcwsyn/brain-robot-arm.git
cd brain-robot-arm/simulation
```

Run `sudo rosdep init` once if rosdep has never been initialized. If it reports an existing source list, do not initialize again. Then, from `simulation/`:

```bash
source /opt/ros/humble/setup.bash
rosdep update --rosdistro humble
rosdep install --from-paths src --ignore-src --rosdistro humble -r -y
/usr/bin/python3 -s scripts/check_sim_environment.py
```

The last command is read-only and should end with `Environment checks: PASSED`. It checks Python modules, ROS/MoveIt/Gazebo/controller packages and required plugin files without starting nodes or motion. Resolve failed checks before building.

Use Ubuntu's NumPy rather than installing a replacement with pip: the validated Humble `cv_bridge` binary uses NumPy 1.x. Entry points use system Python, `-s`, and `PYTHONNOUSERSITE=1` to exclude user-site NumPy 2 and Conda interference. `simulation/validation/physics_grasp/publish_environment_packages.json` records the validated installed versions; it is an environment record, not a package lock requiring every listed package.

## 3. Build only the independent simulation workspace

From `brain-robot-arm/simulation`:

```bash
bash scripts/build_simulation.sh
```

The script clears other ROS overlay paths, sources Humble, checks dependencies, and builds sequentially with at most two compilation jobs. Expect `Summary: 7 packages finished`: `piper_description`, `piper_msgs`, `piper_gazebo`, two Piper MoveIt configuration packages, `brain_robot_pick_place`, and `brain_robot_ball_pick`.

Do not run colcon at the repository root: the historical tree contains packages with the same names. Each workspace owns its `build/`, `install/`, and `log/`. No precompiled install tree is shipped; build on your machine.

The historical `warehouse_db.launch.py` requires a separately configured `warehouse_ros_mongo`/MongoDB setup and is not used by the current simulation entry points. This publication removes that mandatory dependency and declares the Gazebo controller dependencies. The rosdep steps above do not require a database plugin.

Run the accepted algorithm tests:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
colcon test --packages-select brain_robot_pick_place --event-handlers console_direct+
colcon test-result --verbose
```

Expected: 45 GTest cases and four Python geometry-fitting cases, across seven CTest targets. Colcon reports 56 tests with zero errors, failures or skips. Restricting the result scan to this package's `test_results/` reports 49 algorithm cases; 56 includes the additional seven CTest targets, not 56 distinct algorithm cases. This selects the accepted algorithm package; historical model-package lint checks are not part of that count.

## 4. Watch a physical pick-and-place in one terminal

Open a terminal on the graphical desktop, enter `simulation/`, and run one entry point:

```bash
bash scripts/run_ball_physics_sim.sh --seed 20261013
```

For the cylinder:

```bash
bash scripts/run_cylinder_physics_sim.sh --seed 20261013
```

The program loads this overlay, Gazebo, MoveIt, RViz camera panels, scene, detector and centre fitting automatically. It waits for a key; default startup does not move the arm. After environment checks and loading steps 1/5 through 5/5, expect `[就绪]` (ready). Gazebo should contain the arm, table and red object; RViz displays the robot and camera images.

| Key, without Enter | Action |
| --- | --- |
| `1` / `2` | Select placement zone A / B; A is the default |
| `S` | Start camera search, localization, grasp, transfer, release and return home |
| `R` | After success, create a new randomized object; after stop/fault, reload the owned simulation |
| `X` | Request a stop and wait for the stopped state |
| `Q` / `Ctrl+C` | Stop and clean up this program's process groups; restore the terminal |

Wait for ready before pressing S. Requests to start twice, reset or change zones while moving are rejected. A cycle usually takes about 45–60 seconds on the validated machine; slower machines may take longer, with a 200-second cycle limit. Success shows `COMPLETE`, `GRASP_CONTROL_RELEASED`, and `[完成]` (completed), with the arm at zero and the actual object in the selected zone.

Physical mode checks bilateral contact, `LIFTING_PHYSICAL_OBJECT`, `HOLDING_PHYSICAL_OBJECT`, transfer and actual release. An animation or a COMPLETE message alone does not replace recorded acceptance measurements.

`run_ball_visual_sim.sh` and `run_cylinder_visual_sim.sh` retain the nonphysical pose-following demonstration with object gravity disabled. Keep its statistics separate. All entry points explicitly select Fast DDS, ROS domain 83, Gazebo port 11483 and conflict checks. Run one at a time; the program does not terminate foreign processes.

## 5. Automated trials without windows and data export

These commands automatically move only the virtual arm. First try one trial per object, sequentially:

```bash
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 1
bash scripts/run_cylinder_physics_sim.sh --headless --seed 20261013 --batch-trials 1
```

`--headless` hides Gazebo/RViz windows; the depth camera still needs a working graphics context. The validated configuration is a local desktop running without viewer windows. A pure SSH server without an X server is not a validated configuration.

Full repeated plan:

```bash
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 20
bash scripts/run_cylinder_physics_sim.sh --headless --seed 20261013 --batch-trials 20
```

Allow about 15–20 minutes per batch, with machine-dependent timing. Starts use x=[0.38,0.42], y=[-0.12,-0.08] m; zones A=(0.38,0.12), B=(0.42,0.12) m alternate. Stop at the first moving-trial failure and retain evidence. Only the explicit pre-motion refusal `No fresh joint state` permits bounded waiting; failed moving grasps are never retried automatically.

Each trial requires bilateral target contact, at least 5 cm actual lift, at least three simulated seconds of sampled holding, no jaw contact and a settled object after opening/retreat, less than 3 cm placement error, less than 0.02 rad maximum six-axis home error, COMPLETE/control release, and no competing nonzero Servo jog.

The launch prints its session directory under `log/visual_sim/ball-timestamp/` or `cylinder-timestamp/`. `session.json` records actual trajectories, contact samples, simulated time and results; `events.jsonl` records state changes. Scene/ task YAML and image snapshots preserve the setup. Runtime `log/` is excluded from Git.

Replace the session placeholders and choose an output directory that does not exist:

```bash
/usr/bin/python3 -s scripts/analyze_physics_grasp.py \
  log/visual_sim/YOUR_BALL_SESSION log/visual_sim/YOUR_CYLINDER_SESSION \
  --output validation/physics_grasp/YOUR_NEW_RESULTS
```

Historical CSV, plan and summaries are committed under `validation/physics_grasp/acceptance/`. `validation/physics_grasp/raw_sessions.tar.gz` preserves both positive batches, three negative tests and supplemental GUI/flow regressions. Extracting evidence starts no motion:

```bash
mkdir -p /tmp/piper-stage3-evidence
tar -xzf validation/physics_grasp/raw_sessions.tar.gz -C /tmp/piper-stage3-evidence
```

Relative paths remain `log/visual_sim/<session>/`. Historical source archives do not contain a complete precompiled environment. Binary hashes document the validated machine; locally rebuilt binaries need not have identical hashes.

## 6. Failure-handling checks

Run these sequentially, only for one headless ball physics trial. They inject failure deliberately; the expected exit code is **1**, not a successful pick-and-place:

```bash
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 1 --physics-negative miss
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 1 --physics-negative drop
bash scripts/run_ball_physics_sim.sh --headless --seed 20261013 --batch-trials 1 --physics-negative stop
```

They check refusal to lift with a 60 mm offset, loss detection after opening while holding, and stopping during actual lift. Retain continuous measured joint samples after stopping rather than interpreting one log message as stopping performance. No real-hardware emergency-stop latency is claimed.

## 7. Troubleshooting

| Symptom | Action |
| --- | --- |
| Missing `install/setup.bash` | Build from the new simulation/ workspace and confirm seven packages finished |
| Dependency or plugin FAIL | Complete section 2 and run the system-Python preflight without another overlay |
| NumPy / cv_bridge ABI error | Deactivate Conda, use system Python with `-s`, and keep NumPy 2 out of the ROS Python environment |
| Wrong package overlay | Use a fresh terminal and this build script; launch checks require all seven local packages to resolve to this install/ |
| Missing/inaccessible DISPLAY | Run from the logged-in Ubuntu desktop; assigning a fake DISPLAY does not create an X server |
| GLX / RViz rendering error | The entry point selects Mesa software rendering for RViz only. Check the graphics session/driver; retain viewer logs and first test one headless trial on the same desktop |
| Domain 83 / port 11483 in use | Quit the corresponding simulation from its launch terminal and wait for cleanup; do not kill all ROS/Gazebo processes |
| `No fresh joint state` on S | This is a pre-motion refusal. Interactive mode permits another S later; batch mode waits only for this explicit refusal |
| Planning/contact/timeout fault | Preserve the session, request stop, and use R to reload before diagnosis. Do not bypass collision/contact gates |
| Shutdown exceptions after Q | The parent should finish cleanup. Check its owned processes; old MoveIt components may print shutdown exceptions, which do not constitute successful grasp evidence |

## 8. Model, source and future work

Ball: 35 mm diameter, 15 g. Physical cylinder: 50 mm diameter, 100 mm height, 80 g, a solid approximation. Finger pads are simplified boxes and the arm has ideal gravity compensation. Known dimensions, a fixed tabletop and the small randomized region are assumptions. Cylinder maximum placement error was 20.68 mm and still needs improvement.

Start with `scripts/visual_sim_console.py` for orchestration/data, `src/brain_robot_pick_place/scripts/physics_target_node.py` for RGB-D centres, `src/brain_robot_pick_place/src/grasp_lift_executor.cpp` for planning/physical verification, and the two Gazebo Xacro files for dynamics/contact/camera. MoveIt attachment affects collision planning only and cannot drive the Gazebo object.

Classic and modern Gazebo use different plugins; see the [Humble gazebo_ros2_control documentation](https://control.ros.org/humble/doc/gazebo_ros2_control/doc/index.html). This release preserves the current baseline; simulator migration is separate work. YOLO, multiple-class rules, BCI semantic commands and real-hardware validation are not part of this release.

See the [bilingual publication verification](PUBLISH_VALIDATION.md) for clean-directory build, dependency and headless/GUI smoke evidence.
