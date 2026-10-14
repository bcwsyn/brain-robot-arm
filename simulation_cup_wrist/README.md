# Piper cup simulation with one wrist-mounted Gemini 2

2026-10-14 倾角修正：光轴朝夹爪中心偏转19.81°，与法兰平面70.19°，观察位joint5=0.15 rad。Tilt update:19.81° towards the gripper centre,70.19° to the flange plane; observation joint5=0.15 rad. [中文报告](../docs/第五步补充_腕部相机倾角修正与验证.md) / [English report](../docs/stage5_wrist_camera_tilt_update.en.md). 原未倾斜版本保留在标签 `cup-wrist-gemini2-v1-20261014`。

本工作区使用一台腕部相机完成水杯RGB-D、YOLO掩膜、外径估计和视觉抓取。相机法兰前约30 mm、距指尖轴向105 mm；75 mm A/B固定批次2/2和96项核心检查通过。固定外部相机版本保留在相邻 `simulation_cup_grasp/`。

This independent release uses one moving Gemini 2 wrist camera for every visual input and simulated force-feedback cup pick-and-place. The nominal front plane is 105 mm behind the finger-tip reference. The 75 mm two-trial A/B batch and 96 core checks pass; all-size/fault revalidation remains pending.

[中文详细复现](../docs/wrist_camera/README.zh-CN.md) · [English reproduction](../docs/wrist_camera/README.en.md) · [中文补充报告](../docs/第五步补充_单腕部Gemini2相机安装与视觉接入.md) · [English report](../docs/stage5_wrist_camera_update.en.md).

```bash
bash scripts/build_simulation.sh
bash scripts/setup_cup_vision_env.sh
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONNOUSERSITE=1
/usr/bin/python3 -s scripts/verify_wrist_camera_model.py
bash scripts/run_cup_grasp_sim.sh --seed 20261015
```

等待自动规划至观察位和 `[就绪]` 后，在启动终端按 S取放、R复位、Q退出。Wait for the collision-checked observation move and ready state, then use terminal S/R/Q. All motion occurs in Gazebo.

Near-range depth is unavailable below 150 mm; a consistent observation packet is locked before approach. Side offsets/optical centres are mounting assumptions, not hand-eye calibration. Historical training and full fixed-camera archives remain in `simulation_cup/` and `simulation_cup_grasp/`; use those workspaces for their archived offline replay or historical acceptance.
