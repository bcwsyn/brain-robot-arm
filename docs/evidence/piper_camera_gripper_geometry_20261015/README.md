# PiPER 相机—夹爪侧视结构证据

日期：2026-10-15（Asia/Shanghai）
证据文件：`camera_gripper_side_view.png`
来源：用户在本次对话提供的真实安装侧视照片（原始临时文件名：`codex-clipboard-17ebf98d-f923-4377-a79f-c79ebd449ed5.png`）。

## 原始文件完整性

```text
size_bytes: 1130772
sha256: 231AF92715DD5724FBB7AC2D36D614F2F8491F384AA17E2239D3029D93AAC199
```

仓库内 PNG 为原始文件的直接副本，未裁剪、缩放或重新编码。

机器可读的结构观察、模型输入、推导公式和两个候选分支见同目录的 `geometry_inference.json`。

## 图中可直接使用的结构信息

- 红色竖线表示夹爪的向下中心方向。
- 红色斜线表示用户标出的相机光轴，光轴朝向夹爪前下方，而不是与夹爪中心线平行。
- 侧视投影给出的光轴倾角约为 20°；这是照片中的二维几何先验，不是已经部署的 ROS TF 数值。
- 相机为侧面支架安装，镜头光心与 `gripper_base` 原点、两指接触中心不是同一点。
- 相机支架和外壳位于夹爪附近，可能进入近距离深度图和自体过滤模型，需要在后续模型核对中考虑。

## 与仓库模型的对应关系

- 夹爪名义模型：`brain_robot_arm/vendor/piper_ros/src/piper_description/urdf/piper_description.xacro`
- 真实相机参数：`brain_robot_arm/piper_ws/src/brain_robot_ball_pick/config/cube_task_real.yaml`
- 几何计算：`brain_robot_arm/piper_ws/src/brain_robot_pick_place/test/review_camera_mount.py`
- 现有真实配置仍标记 `rotation_calibrated: false` 和 `horizontal_offset_measured: false`。

现有真实配置使用指尖相对光学坐标的测量先验 `[0, 0.070, 0.105] m`，并使用名义指尖偏移 `0.1358 m`。将照片的约 20° 物理倾角作为附加绕工具 Y 轴的初始候选时，按当前几何函数可得到两个符号分支：

```text
additional_pitch = +19.8°  -> effective_pitch ≈ -70.2°,
                         translation ≈ [-101.4, 0, 60.7] mm
additional_pitch = -19.8°  -> effective_pitch ≈ -109.8°,
                         translation ≈ [-30.3, 0, 13.3] mm
```

这两个结果是离线候选，不是最终标定值，也没有写入生产配置。分支符号需结合 `gripper_base` 的实际 TF 轴向和镜头光学 +Z 方向确定；最终仍由六组真实夹持配对数据验证。

## 当前限制

照片提供了真实的安装方向和结构约束，但没有独立的绝对尺度、镜头光心标记、完整三维姿态或夹爪接触中心测量。因此本证据用于初始化和核对模型，不单独证明手眼外参已经标定，也不授权修改生产 TF 或执行真机运动。
