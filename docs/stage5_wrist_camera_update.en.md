# Stage 5 supplement: single wrist-mounted Gemini 2

Date: 2026-10-14. Development scope: `simulation/`. New independent GitHub workspace: `simulation_cup_wrist/`. The previous [fixed-camera stage 5 report](stage5_cup_grasp_report.en.md) and release remain available.

## Implementation

All cup visual inputs now come from the moving wrist RGB-D camera: RGB, registered depth, intrinsics, segmentation, unknown diameter estimation and image-time world targets. The cup world no longer creates an external camera or publishes its static calibration. The YOLO weights remain unchanged. The real-robot workspace and the cup collision-cylinder simplification are outside this update.

The [user photograph](wrist_camera/mount_reference.png) supplies approximate axial distances. The nominal optical/front plane is flange `z=30.8 mm`, and the model tip reference is `z=135.8 mm`, giving 105 mm axial spacing. This moves the prior `z=75 mm` reference rearward by 44.2 mm. Lateral `x=-55 mm, y=0`, orientation and actual lens optical centres remain assumptions pending physical calibration.

The [official Gemini 2 datasheet](https://www.orbbec.com/wp-content/uploads/2023/04/ORBBEC_Datasheet_Gemini-2-3.pdf) supplies a 90×25×30 mm body, 97 g mass and 0.15–10 m depth range. The ideal registered 640×480 RGB-D view uses approximately 63° RGB horizontal FOV at 5 Hz. It does not reproduce native IR FOV, active stereo matching, distortion or vendor D2C. Gazebo and MoveIt share `gemini2_wrist_camera.xacro`, including camera collision geometry; optical `+Z` points towards the fingers.

Startup plans a slow, collision-checked observation configuration `[-0.27, 0, 0, 0, 0.44, 0] rad` before starting the cup executor. This fixed workspace pose does not use Gazebo cup coordinates. Reset re-enters observation; completed grasping still returns to zero.

The 105 mm front-to-tip spacing is shorter than the 150 mm depth minimum. A consistent RGB-D/mask/image-time-TF/diameter/target packet is locked while observing farther away. Close-range execution uses that packet and continuous simulated force feedback, rather than claiming ongoing close-range depth estimation.

## Findings and corrections

An XML comment containing colon-space broke Gazebo's ROS/YAML parameter parser and prevented controller startup. The comment was corrected, and model verification checks parser compatibility.

The actual wrist view produced a cup detection around 0.956 confidence and a finger-edge false positive around 0.427. Each segmentation mask now independently passes depth, upright-height and unknown-diameter/uncertainty gates. The finger mask lacks valid depth and is rejected. Exactly one geometrically valid cup is required; two valid instances remain ambiguous. Four regression cases use the saved actual frame to check detection ordering, fingers alone and multiple valid instances.

## Acceptance

The frozen-code two-trial 75 mm batch passed both A/B placements, seed `20261015`, session `cup-20261014-220858-542297`. Each planned reset reconstructs the simulation; failures are retained without automatic motion retries.

| Metric | A | B |
| --- | --- | --- |
| Estimated diameter | 74.87 mm | 74.85 mm |
| Estimated height | 200.09 mm | 200.08 mm |
| Preopening | 82.87 mm | 82.85 mm |
| Actual peak lift | 144.80 mm | 144.82 mm |
| Hold duration | 3.25 sim s | 3.20 sim s |
| Placement error | 1.217 mm | 0.686 mm |
| Left hold force | 2.710–3.181 N | 2.683–3.166 N |
| Right hold force | 2.818–3.141 N | 2.734–3.151 N |
| Maximum home error | 0.000099 rad | 0.000095 rad |

Both trials verify physical retention, lift, hold, settled release and return. Initial vision diagnostics identify `wrist_camera_optical_frame`; two 2-D detections leave one depth-valid cup. Object truth remains an independent acceptance input rather than a visual target source.

**96 aggregate core checks pass, with zero failures/errors/skips.** This includes the previous core checks and four new regression cases plus their CTest target. Model verification checks matching Gazebo/MoveIt mounts, spacing, optical orientation, collision dimensions, depth minimum and parser compatibility.

GUI and independent-release validation receipts are in `validation/wrist_camera_mount_20261014/final_validation.json`. The former fixed-camera 9/9 positives and 5/5 negatives are historical results. Full 55/85 mm and fault-suite acceptance has not been repeated for the wrist configuration.

The independent release built all seven packages from empty build/install directories in approximately 2 min 1 s and passed all 96 core checks. It reused the installed private vision environment; this is not a fresh operating-system dependency installation test. Its separate GUI trial passed 1/1, with 1.345 mm placement error and a 3.15 sim-second hold. `R` returned to observation/recognition and `Q` exited normally. This trial doubles as release runtime verification and is not counted again in the two-trial batch. Live graph checks confirm one publisher each for wrist RGB/depth and no external-camera topics.

## Reproduction and retained data

Follow the [English guide](wrist_camera/README.en.md) or [Chinese guide](wrist_camera/README.zh-CN.md). In `brain-robot-arm/simulation_cup_wrist`, build the workspace, configure its private vision environment, verify the model, then run:

```bash
bash scripts/run_cup_grasp_sim.sh --seed 20261015
```

Wait for the observation/vision ready state, then use terminal `S` to grasp, `R` to reset and `Q` to exit. Both the camera mounting and its moving image can be inspected visually.

All development failures, pilot/frozen/GUI and release sessions are retained with verification logs, model checks, reference photo and regression data. The session archive has a checksum/file manifest and publication receipt. Previous training and stage 5 archives stay in their original release folders.

The archive verifies 1,659 files individually and occupies 5,814,304 bytes, SHA-256 `391a905c215e4dbd1bfcc22666a7cf756dc5d26124c2583a713b8b08c7c6d856`. All 217 runtime source/config/model files match the independent release byte-for-byte. Archived absolute paths remain historical evidence; the launcher regenerates runtime paths on another machine.

Physical intrinsics/hand-eye calibration, real-image generalization, all-size/fault revalidation, material deformation and hardware feedback remain future work. No physical USB/CAN connection or real-arm command was made.


## Publication receipt

Published [simulation_cup_wrist/](https://github.com/bcwsyn/brain-robot-arm/tree/cup-wrist-gemini2-v1-20261014/simulation_cup_wrist), code commit `fc7107c310324443129c2ea4d8c1721df932932a`, tag `cup-wrist-gemini2-v1-20261014`. The Git trees of all four previous workspace folders remain identical to their pre-publication state. All 217 runtime files match local development; the remote camera macro, console and English guide were downloaded again and verified byte-for-byte. Receipts are in `validation/wrist_camera_mount_20261014/`.
