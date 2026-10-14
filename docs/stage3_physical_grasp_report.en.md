# Stage 3: independent physical grasp development and acceptance

Original acceptance date: 2026-10-13. Scope: the independent `simulation/` workspace. This stage follows the randomized, camera-guided pose-following demonstration. For installation and operation, use the [English reproduction guide](simulation/README.en.md) or [中文运行指南](simulation/README.zh-CN.md). The [Chinese stage report](第三步_物理抓取开发与验收.md) preserves the same acceptance results.

## 1. Purpose and scope

The previous stages established camera search, localization, planning, transport and return home. Objects had gravity disabled and were moved by a pose-following program. Those trials demonstrated the task sequence without establishing frictional retention.

This stage introduces a separate `physics_grasp` mode. Objects retain gravity, contact and friction. Their forced-pose plugin is omitted and the follower rejects enable requests. Finger contact must carry the object; opening the jaws releases it under gravity.

Acceptance covers physical simulation of two known geometric objects. The arm uses position PID force actuation and ideal gravity compensation; finger collisions use simplified pads. This does not validate real motor dynamics, finger material, force control, calibration or real-hardware grasping.

## 2. Implemented changes

| Previous limitation | Implementation |
| --- | --- |
| Forced object poses and following | Physical mode omits the pose plugin and rejects following. Exactly one of flow/physics mode must be selected |
| Geometric proximity treated as contact | Two Gazebo pad contact sensors identify contact with the current target. Missing bilateral contact prevents lifting |
| Direct joint position updates weakened physical transport | All eight joints use Gazebo position PID force actuation in physical mode; flow mode retains the previous interface |
| Asynchronous mirrored fingers | Disable the old mirror node in physical mode; send both jaw trajectories with one future start time and duration and verify feedback |
| Closing retained positive clearance | Use the known specimen diameter with an inward preload; this is position control producing contact, not measured-force feedback control |
| Visible surface points biased object centres | Fit known sphere centres, cylinder side circles or complete top circles from red RGB-D points; remove Gazebo XY substitution from grasp targets |
| Matching image-time TF arrived later | Queue at most six image pairs, wait for their exact-time TF, and discard data older than 0.3 seconds without a latest-TF fallback |
| Descent could rotate the wrist excessively | Bound candidate total joint excursion and duration, test a ±0.001 rad starting neighbourhood and recompute from fresh measured state |
| Trajectory completion did not prove landing accuracy | Check measured-joint FK before closing; permit at most one bounded correction and reject an invalid landing |
| Successful arm motion without a carried object | Monitor actual Gazebo object height, bilateral contact and feedback age during holding, transport and lowering |
| Table pressure or residual jaw contact at release | Open with 25 mm placement clearance, retreat, then verify no jaw contact and a settled object |
| Insufficient physical evidence | Record fitted centres, actual trajectories, contact force, state, simulated time, refusals and software versions; add an offline CSV exporter |

The object is attached only in the MoveIt collision scene during transport. This accounts for carried volume without adding a Gazebo constraint or object drive. After release, rebuild its world collision representation around the actual settled position.

### 2.1 Algorithm overview

1. RGB-D fitting: a red mask selects pixels; depth and camera intrinsics produce points transformed into world coordinates at the image timestamp. Fit the sphere using its known radius. Fit a vertical cylinder's XY using a side circle or full circular cap, with known height/tabletop priors.
2. KDL IK and OMPL: solve target jaw poses and plan collision-aware arm motion. Short descent, lift and retreat segments use Cartesian paths.
3. Position PID: use joint position error to generate force in the dynamics simulation, allowing the contact solver to calculate motion and friction. No real gripper-force controller is claimed.
4. Contact and holding: bilateral target contact permits lift. Actual elevated object height throughout holding demonstrates retention; a HOLDING/COMPLETE label alone is insufficient.
5. State machine: the visual controller owns search motion and hands control to the executor for grasping. Busy start/reset/zone requests are rejected. Stopping requires an explicit reset before restarting.

No neural-network training, YOLO, multiple-object selection or BCI decoding was implemented in this stage.

### 2.2 Specimens and control parameters

| Parameter | Ball | Solid cylinder |
| --- | --- | --- |
| Diameter | 35 mm | 50 mm |
| Height | 35 mm | 100 mm |
| Mass | 15 g | 80 g |
| Inward jaw preload, per side | 2 mm | 4 mm |
| Object friction μ / μ2 | 1.2 / 1.2 | 1.2 / 1.2 |
| Contact kp / kd | 100000 / 10 | 100000 / 10 |
| Linear / angular velocity decay | 0.2 / 0.2 | 0.2 / 0.2 |
| Release clearance above placement height | 25 mm | 25 mm |

The cylinder is solid, not a validated hollow cup. Its physical diameter is 50 mm to leave clearance within the original 70 mm total jaw opening. The flow demonstration retains its 70 mm cylinder. Robot joint travel was not enlarged.

Physical pad collisions are 20 × 62 × 8 mm boxes inside the original finger-mesh envelope. Rendering and MoveIt retain the original meshes. The grasp centre is 123.8 mm along the tool axis from `gripper_base`, 12 mm inward from the original 135.8 mm tip position. The cylinder grip is 20 mm above its fitted centre to avoid wrist interference; the sphere target remains its centre. These are simulation assumptions without physical TCP/pad calibration.

Arm and gripper links have ideal gravity compensation; object gravity is enabled. Joint P/D gains are J1 2000/30, J2 3000/40, J3 2000/25, J4 100/0.3, J5 300/1, J6 30/0.05, ball jaws 300/0.2 and cylinder jaws 600/1.0. Do not transfer these gains directly to physical motors.

## 3. Retained development failures

| Failure | Observation and resolution |
| --- | --- |
| Partial jaw PID caused joint drift | Model startup failed or MoveIt rejected a colliding start. Use the full physical control configuration and explicit ideal gravity compensation |
| Bilateral ball contact without lifting the ball | Direct-position motion and asynchronous mirroring did not maintain transport. Use force PID and synchronized jaw trajectories |
| New jaw feedback wait failed | Use the installed controller's `feedback` fields and release the mutex while waiting for callbacks |
| Missing cylinder centre estimates | The camera mainly saw the top; add full-cap fitting and bounded image-time TF waiting |
| Cylinder slip | Increase the known specimen's inward preload and use its jaw PID profile while retaining actual height/contact thresholds |
| Residual single-jaw contact after placement | Release with clearance and check actual detachment after retreat |
| Contact lost during cylinder transport | The arm's unconstrained joint plan changed tool attitude. The monitor stopped transport; use orientation-controlled Cartesian transport |
| Cylinder descent only 37.5% complete | Reject execution; use an upper-middle grip and suitable tilt candidates while preserving collision checks |
| Ball pushed away on the third planned randomized trial | Keep the entire first attempt, then add descent excursion/time/start-neighbourhood and measured-state checks before rerunning the full plan |

The first ball batch was `ball-20261013-214246-081409`: two successes followed by a third-trial failure. Keep `attempt01_*` evidence separately and exclude it from the corrected acceptance denominator. Initial cylinder transport failure was `cylinder-20261013-221337-157785`; subsequent lowering/slip failures remain in development records.

The accepted ball batch uses revision02. Cylinder-specific Cartesian transport, upper-middle grip, tilt preference and jaw gain changes use a later version. Final normalized sphere dynamics match the accepted ball model exactly, and the accepted sphere arm-control branch remains unchanged. Preserve both source/binary versions rather than reporting forty trials on one binary. See the [version change list](../simulation/validation/physics_grasp/final_revision_changes.json) and [model comparison](../simulation/validation/physics_grasp/final_model_integrity.json). A final-binary sphere GUI regression is reported separately.

## 4. Acceptance protocol and results

### 4.1 Predeclared positive trials

The [saved plan](../simulation/validation/physics_grasp/trial_plan.json) declares 20 trials per object, seed 20261013, x ∈ [0.38,0.42] m and y ∈ [-0.12,-0.08] m. Zones A/B alternate, ten each. A moving-trial failure stops the batch without retry. Only an explicit pre-motion missing-fresh-joint refusal allows bounded waiting on the same scene.

Each trial requires:

1. Object gravity enabled, following disabled, and camera-estimated target XY.
2. Bilateral contact before lifting; actual object lift at least 5 cm.
3. A 3.3-second simulated-clock hold, sampled for at least three simulated seconds, always meeting the height criterion.
4. After opening and retreat, no jaw contact, object speed below 1 cm/s and settled checks for at least 0.5 seconds.
5. Actual final centre within 3 cm of the selected placement centre; maximum six-axis home error below 0.02 rad.
6. COMPLETE, released control, visual IDLE and no nonzero Servo jog while the executor owns motion.

| Object | Complete trials passed | Cycle elapsed time | Actual peak lift | Maximum placement error | Minimum sampled holding span |
| --- | --- | --- | --- | --- | --- |
| Ball | 20 / 20 | 51.42–54.98 s | 13.32–14.84 cm | 0.70 mm | 3.00 simulated seconds |
| Cylinder | 20 / 20 | 46.38–49.63 s | 14.21–14.48 cm | 20.68 mm | 3.00 simulated seconds |

Mean/P95 fitted-centre horizontal differences from the static Gazebo centre were 0.54/0.56 mm for the ball and 0.49/0.60 mm for the cylinder. These describe known geometry and the ideal simulated camera in a small region, not physical hand-eye calibration.

The cylinder batch preserved one initial pre-motion joint-discovery refusal; all twenty moving trials passed on their first attempts. Maximum home errors were approximately 0.0000994/0.0001029 rad. Executor-owned nonzero jog counts were zero for both batches.

Review the [trial CSV](../simulation/validation/physics_grasp/acceptance/trials.csv), [summary](../simulation/validation/physics_grasp/acceptance/summary.json), and [batch verification](../simulation/validation/physics_grasp/batch_validation.json).

![Measured object height during representative accepted trials](images/physics_grasp_height.png)

One representative trial per object is plotted. Height is the actual Gazebo centre's displacement from its initial height; the horizontal axis is elapsed wall time. Green regions indicate holding state. The acceptance holding interval is checked using simulated time separately.

The affected packages built successfully. All 45 existing GTest cases and four new Python fitting cases passed, across seven CTest targets; colcon reports 56 tests, zero errors/failures/skips. New cases cover noisy partial sphere surfaces, cylinder sides, top-only cylinders and insufficient/inconsistent input. Preserve [build output](../simulation/validation/physics_grasp/build_final_revision.log) and the [test summary](../simulation/validation/physics_grasp/unit_test_summary_final_revision.txt).

### 4.2 Failure-handling trials

| One-trial ball injection | Measured observation | Expected result |
| --- | --- | --- |
| Offset target Y by 60 mm | Bilateral contact missing; possible single-jaw contact; actual peak lift below 0.001 mm | FAULT_GRASP_MISSED; no transport |
| Open the jaws after lifting | At least 21.9 mm actual downward motion and contact loss recorded | FAULT_PHYSICAL_OBJECT_LOST_OR_FEEDBACK_STALE; no transport. It was not reported as already landing on the table |
| Stop during actual lift | Object had risen about 26.8 mm. Record 1024 joint samples across 2.046 s; after a 0.5 s settling allowance, observe 1.546 s with maximum inferred speed about 0.0000024 rad/s | Visual STOPPED and control released; no transport or completion |

All three matched the expected rejection. [Negative-test evidence](../simulation/validation/physics_grasp/negative_checks.json) identifies each session. Their batch processes intentionally exit with code 1 and do not count as successful pick-and-place trials. Cancellation during lift still produces FAULT_PHYSICAL_LIFT_FAILED in the executor; finer distinction between user cancellation and execution failure remains a known issue. No real emergency-stop latency is inferred from these tests.

### 4.3 Supplemental final-binary and flow regressions

| Check | Result |
| --- | --- |
| Final-binary ball GUI trial | 1/1 physical trial; 14.16 cm peak lift, 3.20 simulated seconds sampled holding, 0.39 mm placement error, about 0.0000995 rad home error |
| R reset, then Q | Second random scene ready; parent exit 0 and owned groups cleaned |
| Historical ball flow entry point | 1/1; three pre-motion fresh-joint refusals retained separately; moving trial passed once |
| Historical cylinder flow entry point | 1/1; no start refusal |

See [supplemental regression evidence](../simulation/validation/physics_grasp/supplemental_regression.json). These do not increase the denominator of either twenty-trial batch. The GUI check verifies startup, state/data, reset and shutdown, not new interface styling or hardware vision. Some older ROS/MoveIt children emit exceptions on shutdown; parent exit 0 and process-group cleanup do not imply every child exits with code 0.

## 5. Operation and main source files

The [English reproduction guide](simulation/README.en.md) documents dependency installation, clean build, preflight, keys, automated trials, export and troubleshooting. From `simulation/`, use `bash scripts/run_ball_physics_sim.sh` or `bash scripts/run_cylinder_physics_sim.sh`. Wait for ready, select 1/2, start with S, reset with R, stop with X and quit with Q. The two entry points cannot run concurrently.

| File under simulation/ | Purpose |
| --- | --- |
| scripts/visual_sim_console.py | Mode profiles, keyboard, randomized scenes, bounded acceptance and raw data |
| scripts/check_sim_environment.py / build_simulation.sh | Publication preflight and isolated build |
| src/brain_robot_pick_place/scripts/physics_target_node.py | Known geometry centre estimation from RGB-D |
| src/brain_robot_pick_place/src/grasp_lift_executor.cpp | Ownership, candidates, synchronized jaws, contact, holding, release and home |
| src/brain_robot_pick_place/urdf/piper_with_wrist_camera_gazebo.xacro | Wrist camera and pad contact sensors |
| src/piper_description/urdf/piper_description_gazebo.xacro | Physical pad model and position PID gains |
| Both scene-manager scripts | Object gravity, friction and pose-plugin mode selection |
| scripts/analyze_physics_grasp.py | Offline physical trial CSV/summary export |

## 6. Evidence and limitations

Accepted sessions are `ball-20261013-215208-707208` and `cylinder-20261013-225235-997677`, originally under `simulation/log/visual_sim/`. Committed evidence is under `simulation/validation/physics_grasp/`; raw sessions are retained in `raw_sessions.tar.gz`, preserving their relative log paths. Original import checksums are not rewritten to describe later adaptations.

Ball source is retained in `revision02_accepted_source.tar.gz` with binary hashes in `revision02_acceptance_source_hashes.json`. Cylinder/final-regression source uses `accepted_source.tar.gz` and `acceptance_source_hashes.json`. Those are historical machine/version records. Publication adds environment/build guards and separate fresh-directory checks; it does not reinterpret historical hash records as checksums of every current publication file.

Original stage verification found all 334 imported real-workspace files unchanged. No real workspace build, hardware operation, system package installation or system configuration change was performed for that acceptance. Publication also keeps real-hardware code outside the new workspace.

Current limitations:

- Known radius/height, vertical cylinder, fixed tabletop and ideal camera TF; no unknown geometry or general six-degree-of-freedom pose estimation.
- Simplified pads/friction and ideal arm gravity compensation; no physical material, motor or force-sensor calibration.
- Cylinder maximum placement error is 2.07 cm, within the 3 cm gate but requiring improvement.
- A 25 mm release clearance is appropriate only for these nonfragile simulated specimens; no compliant placement policy for fragile items.
- Trials cover two single-object scenes within 4 × 4 cm, not a whole table, ten categories, two real environments or two-hour continuous operation.
- Gazebo contact force is a solver result, not measured real gripper force.

Implementation references: [Gazebo ROS contact plugin](https://github.com/ros-simulation/gazebo_ros_pkgs/blob/ros2/gazebo_plugins/src/gazebo_ros_bumper.cpp) and [Humble Gazebo position PID interfaces](https://control.ros.org/humble/doc/gazebo_ros2_control/doc/index.html). Saved models and actual observations define this machine's evidence.

## 7. Next stage

Keep the two-object physical regression set and improve cylinder placement first. Select three concrete categories/specimens and sizes, evaluate an official pretrained YOLO baseline using held-out project images, and add fine-tuning only where coverage or performance requires it. Define target ID/selection, reliable depth regions, geometric rules and candidate scores before expanding classes.

Then connect simulated head-pose and grasp/stop semantic commands. Real device identification, calibration and supervised hardware tests remain separate. Behaviour cloning/DDPG follow a reliable rule baseline and meaningful feedback.

## 8. Publication verification (2026-10-14)

All seven packages were rebuilt in a fresh checkout without using the original build/install trees. All 49 algorithm cases passed (56 results including CTest targets). Relocated ball/cylinder physical smoke trials and a ball GUI trial with random reset/quit passed separately from the historical 20+20 trials. See the [bilingual publication verification](simulation/PUBLISH_VALIDATION.md) for evidence, assumptions and reproduction-only launcher/dependency changes.
