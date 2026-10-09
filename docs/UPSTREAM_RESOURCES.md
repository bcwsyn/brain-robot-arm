# Upstream resources and compatibility ledger

Last reviewed: 2026-10-09. This is an evaluation ledger, not an authorization to replace the active real-robot chain. Pin immutable commits and run receive-only/offline compatibility tests before integrating upstream code.

## Official AgileX sources

| Resource | Current reference | License / environment | Reuse assessment |
|---|---|---|---|
| [agx_arm_ros](https://github.com/agilexrobotics/agx_arm_ros), branch `ros2` | Official ROS 2 driver; repository README says Piper/Nero family, Humble/Jazzy install paths, pyAgxArm dependency, MoveIt package, and `auto_enable` defaults true. Branch head SHA was not reliably retrievable in this review; pin it before any checkout or code comparison. | MIT (repository page) | Compare launch, feedback, MoveIt and grasp examples only in an isolated workspace. Not a drop-in replacement: the active chain depends on the existing `piper_jog_adapter`, custom V2 offset feedback parsing, safety gates and real profile. Do not invoke its direct control examples on the robot. |
| [pyAgxArm](https://github.com/agilexrobotics/pyAgxArm), branch `master`, changelog v1.0.0 | Official new Python SDK; README documents Linux SocketCAN and `can0`, firmware-aware arm models, and Ubuntu 18.04/20.04/22.04/24.04. Current page identifies LGPL-3.0-only; review obligations before redistribution. Exact branch SHA was not retrieved; pin before isolated test. | LGPL-3.0-only; Python >=3.6 per README | Candidate for a future isolated receive-only comparison, not migration now. Local runtime imports `piper_sdk` 0.6.2 and `pyAgxArm` is not installed. Firmware-profile support for the actual S-V1.9-1 controller must be verified before even an SDK-only migration test. |
| [piper_sdk](https://github.com/agilexrobotics/piper_sdk) | Legacy official SDK. Local runtime package metadata: `piper_sdk==0.6.2`; active driver imports `C_PiperInterface_V2`. | MIT; installed metadata claims Ubuntu 18.04/20.04/22.04 and Python 3.6/3.8/3.10 | Currently active dependency, not a candidate for blind replacement. Installed SDK source has a `ReadCan` loop that breaks on CAN exceptions; `CanMonitor` observes FPS but does not restart the read thread. The application driver independently watchdogs fresh high-speed and aggregate joint feedback and suppresses commands when absent. This proves a plausible software failure mode, not the cause of the observed guest USB/CAN RX stall. |
| [agx_arm_moveit](https://github.com/agilexrobotics/agx_arm_ros/tree/ros2/src/agx_arm_moveit) | Official parameterized MoveIt 2 configuration for arm/effector combinations. | Under parent repository license | Reference planning group and model structure only. Preserve current custom URDF, measured state construction, collision checks, software limits and adapter gate. |

### Official CAN compatibility caveat

The current pyAgxArm [CAN module manual](https://github.com/agilexrobotics/pyAgxArm/blob/master/docs/can_user.md) explicitly says its helper scripts/support cover only the CAN module supplied with the arm and do not support other CAN modules; it separately documents Linux SocketCAN and 1 Mbps setup. The actual guest currently enumerates USB ID `1d50:606f` (“Geschwister Schneider CAN adapter”) and binds `gs_usb`. This identifies the guest USB device/driver but does **not** establish that it is AgileX’s supplied CAN module. Compatibility remains unverified; do not infer support solely from SocketCAN/`gs_usb` compatibility.

## Upstream reports relevant to the observed symptom (reports, not verified root causes)

- [piper_sdk issue #112](https://github.com/agilexrobotics/piper_sdk/issues/112): reporter describes Ubuntu 22.04 + candleLight/`gs_usb` where TX is visible but no arm RX, while the same hardware reportedly worked on Windows. It is an open user report, not a confirmed vendor diagnosis.
- [piper_sdk issue #118](https://github.com/agilexrobotics/piper_sdk/issues/118): reporter describes intermittent Ubuntu CAN communication restored by physical USB reconnect. It does not establish that the current incident has the same cause.
- [piper_sdk issue #109](https://github.com/agilexrobotics/piper_sdk/issues/109): reporter alleges the SDK read thread terminates on CAN exceptions and lacks recovery. Local 0.6.2 source inspection confirms its `ReadCan` loop catches CAN/general exceptions and `break`s; its FPS monitor updates health but does not restart that worker. Local app-level feedback watchdog is present. This remains a plausible software weakness, separate from the currently observed `can0 DOWN` state and VM USB receive path.

## Other project leads

- [Orbbec ros2_astra_camera](https://github.com/orbbec/ros2_astra_camera): reference only for official Astra launch/stream options. Keep the already validated OpenNI depth + separate kernel V4L2 RGB setup; do not enable Astra UVC in the combined USB path without a new compatibility test.
- [piper-ros2-dls](https://github.com/iit-DLSLab/piper-ros2-dls): secondary project lead; inspect only after pinning commits and comparing firmware, driver, camera and ROS interfaces. It is not authoritative for this hardware.

## Required compatibility workflow before any upstream code is adopted

1. Resolve and record immutable commit SHAs (including submodules), license, supported OS/ROS/Python, PiPER firmware profile and CAN hardware.
2. Use an independent workspace; preserve the dirty canonical/runtime trees.
3. Compare CAN receive/error propagation, feedback message IDs/units, gripper contract, URDF/TCP, MoveIt groups/limits, and launch control publishers against the actual active chain.
4. Run offline tests, then a receive-only compatibility test with no enable, reset, mode change or motion frames.
5. Integrate only the smallest proven change through the existing adapter and one-click launch; keep all current feedback, collision, limits and safe-stop gates.
