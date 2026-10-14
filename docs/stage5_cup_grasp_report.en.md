# Stage 5: camera sizing and force-feedback cup grasp integration

Date: 2026-10-14. Local scope: `simulation/`. New GitHub workspace: `simulation_cup_grasp/`, preserving previous versions. This follows [stage 4](stage4_cup_training_report.en.md). Final frozen simulation and GUI acceptance are complete; publication/archive verification has separate receipts.

## 1. Objective and specimen

Connect the frozen learned segmentation, unknown local RGB-D diameter estimate and contact-force policy to physical simulation: visual sizing, conservative preopening, measured-force capture/hold, actual lift/transfer, release/settling and homing. The v2 model and all previous training datasets/checkpoints are unchanged; no retraining was needed.

The user specimen is an opaque empty handleless stepped cup: 75 mm outer body diameter over 160 mm, then 63 mm outer mouth diameter over 40 mm. Assumed mass is 80 g and wall thickness 2 mm. The 100 mm stroke matches the specified large gripper. Other dynamics, friction, plastic strength, physical TCP and force calibration remain simulation assumptions.

## 2. Implemented architecture

The read-only YOLO node publishes mask/depth-derived world grasp point, unknown local diameter, uncertainty, preopening and validity at the image timestamp. It never reads Gazebo object truth or commands motion. The executor requires matching nonzero point/width timestamps and fresh validity. Preopening is diameter + 2 sigma + 6 mm; uncertain/oversized objects are refused rather than clamped to the stroke limit.

After the preopening handshake, a fresh locked packet is supplied to the force node. Measured jaw opening must confirm completion before approach. Measured FK must confirm the landing before closure. The force bridge is the sole publisher to the two jaw trajectory topics. Commands are strictly symmetric: joint7=opening/2 and joint8=-opening/2, matching one total-opening interface; experimental independent midpoint translation was removed.

Streaming trajectories explicitly continue from the previous commanded endpoint. Repeated single-endpoint interpolation from blocked measured positions had erased PID preload. A smaller commanded than measured opening generates contact preload in the rigid simulation and does not imply the cup has deformed to that commanded diameter.

Both pad forces must remain in band for at least 0.5 simulation seconds before hold. Feedback control continues during lift and transfer. The executor monitors bilateral contact, fresh healthy force feedback and actual object height throughout lifting, holding, transfer and lowering. Missing/invalid/stale feedback, lost contact, low bilateral force or overload interrupts motion.

MoveIt attachment affects collision planning only. The Gazebo cup remains free under gravity, contact and friction, without following/adhesion. Release must be followed by settled height, absence of pad contact and homing. Object truth supplies independent acceptance measurements and scene collision geometry; visual XY and diameter do not come from that truth. Automatic collision reconstruction of an unknown real scene remains future work.

## 3. Parameters and force interpretation

| Item | Configuration |
| --- | --- |
| Total stroke / jaw bound | 100 mm / 50 mm |
| Sigma floor / accepted maximum | 1 mm / 4 mm |
| Image packet age | At most 0.5 s |
| Force receive age | At most 0.2 s |
| Accepted pad band / central target | 2.5–3.5 N / 3 N |
| Observed-feedback overload threshold | 5 N per pad |
| Bounded closure policy speed | 4 mm/s, simulation-time integration |
| Jaw position PID P/D | 300 / 0.5, simulation settings |
| Grasp height | 60% of observed height; read-only stage 4 default remains 55% |
| Tilt candidates / virtual grasp reference | 1.2, 1.0, 0.70 rad / 130 mm |
| Lift / hold / release clearance | 120 mm / 3.3 simulation s / 25 mm |
| Simulation clock / joint TF / RViz | 100 Hz / 50 Hz / 10 fps |
| Jaw-axis TF validity | Original 150 ms bound, prefer contact-time TF |
| Isolation | localhost ROS domain 85, Gazebo port 11485 |

The body/mouth remain hollow with 48-facet convex collision wedges. One thin bottom disk replaces coplanar bottom wedges, resulting in 145 collision solids. ODE iterations are 200, friction coefficients 1.2/1.2 and contact kp/kd 100000/10. The model does not represent plastic deformation/crushing. Arm links use ideal gravity compensation. These values are not factory-rated performance.

Gazebo contact sensors buffer multiple physics steps per message. Control selects the newest step, sums the target reaction vectors on a complete pad, then projects onto the measured closing axis. Gross absolute point-normal loads are separate diagnostics; forces are never summed across time or counted again through total_wrench. The 5 N threshold applies to observed feedback, not a guarantee of detecting every inter-sample peak or establishing real cup strength.

Historic stage 4 values 34.44/25.49 N aggregated steps/point loads and must not be interpreted as instantaneous net grip force. Both stage 4 reports now explain this while retaining the original records. SDK effort/torque is a different quantity from N and needs validated conversion/calibration. [Pinned SDK feedback definition](https://github.com/agilexrobotics/piper_sdk/blob/c9e8a28174e71eeaac448593cb65f8ab258a92fe/piper_sdk/piper_msgs/msg_v2/feedback/arm_feedback_gripper.py)

## 4. Retained failures and corrections

| Observed failure | Correction |
| --- | --- |
| Service existed before MoveIt interfaces were usable | Actual readiness gate and periodic ready notification |
| Locked image expired before preopening | Fresh-packet handshake, unchanged freshness bound |
| Temporal/contact-edge load aggregation | Newest-step net axis force, separate gross diagnostic |
| Repeated trajectories lost preload | Previous-command trajectory continuation |
| Release path was collision-rejected near the forearm | Legal outer A/B placement regions; collision checks retained |
| Hot deletion of compound cup corrupted Gazebo heap | Complete owned-stack reset on R; no automatic moving retry |
| Summary serialization made console feedback temporarily stale | Wait for fresh settled joint feedback before reset |
| Synthetic overload pulse expired before timer consumption | Latch one explicitly synthetic test sample |
| GUI load exceeded jaw TF validity | 100 Hz clock, 50 Hz TF and contact-time lookup; bound retained |

The first 15 paused-development trials, later pilots, r1–r7 and GUI failures are preserved separately from final acceptance. Prior successful trials are not added to the final denominator.

## 5. Final acceptance

The complete frozen final r8 suite passed: **75 mm 5/5**, **55 mm 2/2**, **85 mm 2/2**, plus all five negatives (missed bilateral capture, lost feedback during lifting, synthetic 6 N overload, mid-lift stop and visual rejection of a 105 mm oversized cup). Every group retained unchanged frozen source hashes. Earlier r6/r7 results and failures remain separate and are not added to this denominator.

| Metric | Final nine positives |
| --- | --- |
| Maximum 3D placement error | 0.916 mm |
| Minimum measured holding span | 3.16 simulation s |
| Minimum peak physical lift | 144.79 mm |
| Maximum homing joint error | 0.0000977 rad |
| Maximum final cup-axis tilt | 0.0011495 rad |
| Range of every bilateral holding-force sample | 2.659–3.221 N |

GUI validation passed a complete S sequence, full R recreation/readiness, B selection, X cancellation during release lowering and Q cleanup. The independent GUI success had approximately 0.731 mm placement error and at most21 ms jaw-axis TF age; mid-lift cancellation is separately covered by the frozen suite. Core checks:91 aggregate, zero errors/failures/skips. The publication workspace built seven packages from empty build/install and passed91 core checks. Publication motion, archive restoration and remote checks have separate receipts.

An earlier expanded scan covered187 aggregate checks with74 vendor copyright/style failures;13 relevant Python/CMake files match stage4 Git blobs. Core checks subsequently increased to91. Upstream lint is not reported as passing; full failure logs/comparison are retained.

Evidence: `simulation/validation/cup_grasp/acceptance_r8_final/results.json`, `final_acceptance.json` and each saved `session.json`. Criteria: actual lift≥50 mm, holding≥3 simulation s, every stationary-hold force sample bilateral/in-band/fresh/healthy, placement<30 mm, home<0.02 rad, final tilt<0.12 rad, physical release and no nonzero Servo jog.

## 6. Reproduction

With the existing local environment:

```bash
cd /home/young1x/robot_projects/piper_robot/simulation
bash scripts/run_cup_grasp_sim.sh --seed 20261015
```

First setup:

```bash
cd /home/young1x/robot_projects/piper_robot/simulation
bash scripts/build_simulation.sh
bash scripts/setup_cup_vision_env.sh
bash scripts/run_cup_grasp_sim.sh --seed 20261015
```

Wait for five startup steps and ready. In the launching terminal press `1`, wait for zone confirmation, then `S`. After completion press `R`, wait for readiness, select `2`, wait for confirmation, then `S`. `X` stops and `Q` quits; no Enter is required. Gazebo/RViz show the arm/cup; the large floating “Cup Detection and Grip Force” panel shows segmentation, measured opening and pad forces and can be moved.

GitHub users clone/pull, enter `brain-robot-arm/simulation_cup_grasp` and run the same scripts. Full prerequisites, checks, diameter examples and fault commands: [English guide](cup_grasp/README.en.md), [中文指南](cup_grasp/README.zh-CN.md). Earlier read-only replay and ball/cylinder entries remain available and use separate acceptance statistics.

```bash
python3 scripts/verify_cup_grasp_suite.py --case all
```

## 7. Data preservation and restoration

Each session stores exact locked RGB-D/mask/calibration and model hash, visual estimates, object/joint/force/opening traces, state events, generated configuration, logs and source snapshots/hashes. Sessions live in `simulation/log/visual_sim/cup-TIMESTAMP/`; build/test/aggregate evidence is in `simulation/validation/cup_grasp/`.

The new published workspace includes split archives and checksums under `validation/cup_grasp/archives/`. Restore to a nonexistent directory:

```bash
python3 scripts/restore_cup_grasp_archives.py --destination recovered_cup_grasp
```

Historical world/SDF absolute paths are evidence and are not launched directly on another machine; the entry regenerates local paths. Recorded RGB-D/mask/calibration is self-contained. Previous complete training archives remain in `simulation_cup/`.

![Measured force, opening and physical cup height](cup_grasp/cup_force_trace.png)

![Live segmentation and measured grip force](cup_grasp/cup_force_panel.png)

![RViz cup grasp view](cup_grasp/cup_grasp_rviz.png)

## 8. Limits and next stage

This validates simulated visual sizing with force-feedback grasping. It does not validate real hardware, transparent/handled/water-filled cups, multiple targets, moving-object tracking, material-strength estimation, unknown-scene collision reconstruction or brain-computer decoding. Fixed calibration/tabletop, a single upright opaque empty cup, assumed mass/friction, simplified pads and ideal gravity compensation are current conditions.

Next: identify physical gripper/firmware/feedback, collect real images and dimensions, calibrate RGB-D/arm/TCP, evaluate offline replay, establish whether torque/current can be converted to grip force, then perform supervised low-speed single-cup testing. Physical motion requires explicit authorization and on-site supervision; this stage has not connected or controlled hardware.


### Independent publication and legacy smoke checks

Seven packages built from empty build/install in approximately1 min38 s; the final readiness-heartbeat rebuild took approximately1 min47 s. All91 core checks passed and212 source/config/model files match the local workspace. The pinned local private vision environment was reused; this is not a fresh operating-system installation test.
- ball: 1/1 passed, placement error 0.607 mm, counted separately.
- cylinder: 1/1 passed, placement error 16.004 mm, counted separately.
- published-cup: 1/1 passed, placement error 0.840 mm, counted separately.


### Complete archive verification

All18177 stage files are preserved in two parts, each at most45 MiB; combined archive55239926 bytes. Restoration to a new directory verified every file SHA-256. Earlier training/model archives remain preserved. Receipt: `validation/cup_grasp/archive_restore_verification.log`.
