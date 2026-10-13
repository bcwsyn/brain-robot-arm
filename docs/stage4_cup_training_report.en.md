# Stage 4: cup training, RGB-D sizing and adaptive-gripper foundations

Date: 2026-10-14. Development scope: local `simulation/`; publication directory: `simulation_cup/`. [Reproduction guide](cup_simulation/README.en.md) · [Chinese report](第四步_水杯训练与自适应夹持基础验证.md).

**Training and component validation are complete for this increment. Integrated force-controlled cup pick-and-place is not yet implemented or accepted.** Perception/offline-policy results are not counted as physical cup-grasp successes.

## 1. Confirmed specimen and hardware variant

The empty, opaque, handleless plastic cup has a 75 mm outer body diameter over 160 mm, then a 63 mm outer mouth diameter over 40 mm, approximately stepped; total height 200 mm. Mass 80 g and wall thickness 2 mm are simulation assumptions, not measurements. The user confirmed a 100 mm total gripper opening and selected simulation force feedback while the real interface is unknown.

The [official SDK parameters](https://github.com/agilexrobotics/piper_sdk/blob/c9e8a28174e71eeaac448593cb65f8ab258a92fe/asserts/V2/INTERFACE_V2.MD) distinguish 70 mm small and 100 mm large grippers. Upstream ROS Humble still uses 35 mm one-sided travel. Default Gazebo/MoveIt limits now match the selected large variant: joint7 [0, +0.050] m and joint8 [−0.050, 0] m; SRDF open and executor bounds agree. Generated URDF limits were checked.

Only stroke was verified/corrected. Existing meshes, simplified pads, position PID and ideal arm gravity compensation are not calibrated factory dynamics. Historical Stage 3 trials keep their original versions/results. SDK effort is torque in 0.001 N·m according to its [feedback definition](https://github.com/agilexrobotics/piper_sdk/blob/c9e8a28174e71eeaac448593cb65f8ab258a92fe/piper_sdk/piper_msgs/msg_v2/feedback/arm_feedback_gripper.py); it is not measured fingertip normal force in N.

## 2. Implemented components

| Component | Implemented | Pending |
| --- | --- | --- |
| Hollow stepped cup | Bottom/body/shoulder/mouth, 48-segment convex shell, distributed inertia | Plastic deformation and material calibration |
| Learned segmentation | Two YOLOv8n-seg training revisions and frozen recommended model | Real-camera and broader scene evaluation |
| RGB-D sizing | Learned mask, calibrated camera transform, unknown local circle fit | Tilted/noncircular objects and heavy occlusion |
| Opening policy | Diameter + 2×uncertainty + 6 mm; rejects insufficient stroke | Actual execution in the cup task |
| ROS perception | Image-time TF, target/width/validity/debug outputs | Motion-executor connection |
| Force extraction | Sum point-wrench projections onto normals per target pad | Real torque-to-force conversion |
| Force policy | Bounded closing/relief, bilateral band, stale/invalid/overforce handling | Gazebo controller ownership and integrated task acceptance |

The estimator never receives specimen diameter or Gazebo object position. Near-facing outer-wall selection prevents visible inner walls from shrinking the estimate. Sparse, narrow-arc or inconsistent clouds are rejected. The current upright/tabletop rule selects roughly 55% of observed height for a body grasp; it is not general grasp planning.

Opening examples with the current 1 mm uncertainty floor: 75 mm diameter suggests 83 mm; 63 mm suggests 71 mm. The floor is a conservative uncalibrated parameter, not a certified confidence interval. Oversized, stale or overly uncertain estimates are rejected rather than clamped into a grasp.

Offline force settings are configurable: 1.2–2.5 N per pad, 5 N hard threshold, maximum 4 mm/s total closing rate. They are not manufacturer/material limits. Policy state is commanded opening; resetting to blocked measured jaw position would erase PID preload. Bilateral force alone cannot prove retention or safe release.

## 3. Data and training revisions

Twelve cup geometries, ten camera views each, with raw RGB/depth, calibration, poses, geometry and logs. Geometry splits precede color/brightness augmentation. Development sets: 264 training images, 26 validation, 26 development test; a further 26-image final set uses new geometries/backgrounds after v2 is frozen. Positive-image hashes do not overlap across development splits. One constant blank negative repeated in the development sets and is explicitly audited; the fresh final set has zero image-hash or geometry overlap.

The user's exact specimen has five diagnostic views excluded from training. They were used to debug labels, so they are not called an untouched final test set.

Initial fixture annotations missed a dark connecting neck, producing body-only masks and approximately 39 mm height underestimation despite high synthetic metrics. V1 data, labels, weights and predictions were preserved. Corrected chroma-based fixture annotation includes the dark neck before recoloring; v2 then learns the whole cup. Runtime perception uses learned masks, not fixture color rules.

CPU training: input 320, batch 8, AdamW, seed 20261014. V1: 20 epochs from official COCO weights. V2: 12 epochs from v1 best. All arguments, CSV/plots, best/last, periodic checkpoints and data revisions are archived. COCO cup ID is 41; the custom single-class cup ID is 0, resolved by name in tools.

## 4. Results and limits

Frozen v2 on 26 fresh synthetic images: 20 cup instances, six negatives. Box/mask precision approximately 0.9973, recall 1.000, mask mAP50 0.995, mask mAP50–95 0.9269. This small synthetic evaluation does not establish real-camera accuracy.

Recommended model SHA-256: `8f7afc15dd047edabc3fc0459e539e11220b19adbcc28c2da955aa07043cbeef`.

The original COCO model detected no cup in the five specimen views. V2 detected one in every view, with mask IoU 0.9607–0.9765, maximum body-diameter error approximately 0.137 mm and maximum observed-height error approximately 0.542 mm. These geometric errors use ideal noise-free simulated depth and calibrated transforms. They are not hardware precision. Initial failures are retained.

ROS v2 replay passed five positive views, blank-image rejection and stale-image rejection: seven checks, no arm motion. Algorithm tests passed 69 cases across nine CTest targets; colcon reports 78 total, zero failures/errors/skips.

The first clean-publication replay lacked enough results for two views and exposed duplicate context shutdown. The failed run is retained. Reliable image QoS, actual endpoint discovery, a slower fixture rate, frame-associated results, bounded numerical-library threads and guarded shutdown were added together; validation does not establish a single exclusive root cause.

The stronger frame association also exposed shared Python message headers: setting an output frame modified the input image header by reference. Output headers now use deep copies. That failed attempt and its source snapshot are retained; the final replay checks actual image-frame identity.

The corrected 100 mm model passed legacy physical regression: one ball trial, one cylinder trial, plus one cylinder trial with a read-only normal-force recorder. Each completed release/home. They are separate from historical 20+20 results and are not cup trials. Baseline cylinder pad-force peaks were approximately 34.44 N / 25.49 N; the recorder did not regulate force, and these do not validate the new low-force policy.

All 334 imported real-workspace files retain original hashes. No real-workspace build, system-package installation or hardware command occurred.

The publication directory built all seven packages from zero in approximately 1 min 41 s and created a fresh private Python environment. Model sizing, the 78-test aggregate and the corrected seven-case ROS replay passed there; an additional ball/cylinder physical trial passed for each legacy specimen. Archive restoration compared 7,076 original dataset/training files byte-for-byte with no mismatch. Additional publication sessions are archived separately.

## 5. Saved material and next increment

`validation/cup_vision/` holds results, failures, checksums and multipart archives. `models/` provides recommended and original weights plus provenance/license references. The guide covers clean build, private dependencies, offline evaluation, ROS replay, fresh Gazebo capture, archive restoration and retraining.

Next: connect synchronized diameter/validity to the executor; introduce one exclusive Gazebo jaw-force command owner; validate stable bilateral force while lifting/transporting; retain actual-object/drop/release/stop checks; test multiple diameters and failures. Then broaden visual evaluation and separately establish real feedback, hand–eye/TCP calibration, torque conversion and cup strength. No further hardware information is needed to continue simulation work.

The publication keeps previous repository code in place and adds `simulation_cup/`. It does not replace the previous workspace or rewrite its history.
