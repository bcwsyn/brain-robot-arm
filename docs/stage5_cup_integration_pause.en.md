# Stage 5 cup integration: paused development checkpoint

Status: IN PROGRESS, NOT ACCEPTED. The user requested a pause because the computer battery is low. This is a recovery record, not a successful stage acceptance report.

## Saved implementation

The frozen stage 4 YOLOv8n-seg v2 model and training datasets were not changed. A new simulation launcher/console and `cup_task.launch.py` connect a fixed RGB-D camera, learned segmentation, unknown local diameter estimation, MoveIt motion, and a dedicated gripper contact-force node. The executor locks fresh matching point/width timestamps and computes preopening as diameter + 2 sigma + 6 mm, capped at 100 mm. Only Gazebo motion is used; the real-robot workspace is untouched.

Force control now selects the newest physics step from each Gazebo contact message and projects the net cup reaction onto each jaw closing axis. Gross absolute point-normal load remains a diagnostic. Fourteen related unit tests passed (`simulation/validation/cup_grasp/contact_axis_tests.log`). Current development thresholds are 2.5–3.5 N per pad with a 5 N hard limit; these are uncalibrated simulation settings. The hollow stepped cup remains 75/63 mm in outer diameter, 160/40 mm in height, with assumed 80 g mass and 2 mm wall thickness. A single thin bottom collision disk and 200 ODE solver iterations are experimental changes, not validated fixes.

The latest C++ build passed (`ready_gate_build.log`). Full integration regression, GUI acceptance and formal cup pick-and-place validation have not been completed.

## Last failure

Fifteen development trials are retained. None completed the entire cup capture, hold, transfer, placement and homing sequence. An earlier trial lifted approximately 70 mm but failed force-health checks and is not an accepted success.

Latest session: `simulation/log/visual_sim/cup-20261014-161056-497915/`.
Console log: `simulation/validation/cup_grasp/fifteenth_trial.console.log`.
Last sequence: `OPENING_GRIPPER -> PREPARED -> FAULT_CUP_PREOPEN_FAILED`; the session then exited and cleaned up its simulation processes. This failure was not investigated before the pause.

The latest experimental bridge sends capture/hold trajectories with an explicit previous commanded position and next target, to investigate loss of position preload when repeated trajectories interpolate from blocked actual positions. Open/preopen now sends one 600 ms trajectory. This change is not validated and currently fails preopening.

Session JSON, events, node logs, later source snapshots and raw contact packets are retained. `force_contact_trace_10.jsonl` is a diagnostic recording spanning later debugging, not formal trial 10 acceptance evidence.

## Resume order

1. Inspect the latest task, event, force status and controller logs. Diagnose preopening, trajectory rejection/reference, timestamp validity and state transitions before further motion.
2. Verify sustained command preload; complete lift-time contact/force monitoring, HOLD low-force/lost-feedback handling, sustained overload relief and clearing stale readiness on reset. Fix or remove the incompatible legacy drop-negative path. These changes remain unfinished.
3. Archive the actual locked RGB-D frame, calibration and segmentation, and add live opening/force visualization.
4. Update and freeze `stage5_test_plan.json`: its older force band/definition does not match the current implementation. Run the planned multi-diameter positives, meaningful negatives, legacy regressions and GUI controls only after the prototype works.
5. After acceptance, write Chinese/English stage reports and reproducible instructions, archive all data and publish to the existing GitHub repository without removing previous versions. Stage 5 development is currently local only.

The following command reproduces the current development attempt; it is expected to fail and is not an accepted demonstration. Read the existing logs first.

```bash
cd /home/young1x/robot_projects/piper_robot/simulation
bash scripts/run_cup_grasp_sim.sh --headless --seed 20261014 --batch-trials 1
```

Use the existing Humble/Gazebo environment, simulation install and `.venv-yolo`. Build only the simulation workspace when code changes require it. Never connect or command real hardware. The launcher uses localhost ROS domain 85 and Gazebo port 11485.

All sources, build/install outputs and trials remain on disk. An additional `validation/cup_grasp/pause_*/current_sources_and_latest_evidence.tar.gz` archive and SHA-256 manifest preserve the current source and latest evidence. Restore only deliberately; no automatic overwrite is required. Development, testing and publication are paused until the user asks to continue.
