# Publication validation / 发布核验

Date / 日期：2026-10-14。

This increment adds `simulation_cup/`. The previous 777 tracked repository files were audited: all previous code/documents remain unchanged, while the complete old root README text is preserved and a new entry is appended. No force push or history rewrite is used.

本版新增 `simulation_cup/`。旧仓库 777 个跟踪文件已逐一核验：原代码、原文档全部保留；根 README 保留完整旧内容并追加新版入口。旧版本不删除，不强制推送或改写历史。

| Check / 检查 | Result / 结果 |
| --- | --- |
| Source-only independent build / 无生成输出的独立构建 | Seven packages, approximately 1 min 41 s / 七包通过，约 1 分 41 秒 |
| Private Python setup / 独立 Python 环境 | Setup script passed in a fresh venv / 新环境安装脚本通过，无系统包安装 |
| Algorithm checks / 算法检查 | 69 cases, 9 CTest targets; colcon 78 total, zero failures / 69 用例、9 目标，汇总 78，零失败 |
| Learned-mask RGB-D sizing / 学习掩膜估径 | Five specimen views passed / 五视角通过 |
| ROS replay / ROS 回放 | Final seven checks passed with frame association; two failed attempts preserved / 最终七项通过，保留两次失败及修复证据 |
| Legacy Gazebo motion / 原物理流程 | Fresh-directory ball 1/1 and cylinder 1/1 / 新目录球与圆柱各 1/1 |
| Archived data restoration / 原始数据恢复 | 7,076 dataset/training files identical / 7,076 个数据与训练文件一致 |
| Real workspace / 实机工作区 | 334 imported files retain hashes; no hardware commands / 334 文件未变，未操作硬件 |

Detailed evidence is under `simulation_cup/validation/cup_vision/`. `publication_validation.json`, `published_physics_regression.json`, `github_preservation_check.json`, archive manifests and native failure logs explain the scope. Multipart training archives preserve both model/annotation revisions, including the incorrect first annotation attempt. Generated build/install, private environments and unrelated project files are excluded from publication.

详细证据位于上述目录。第一轮错误标签、失败预测及回放失败均有保存。上传包含源码、推荐/初始化权重、完整数据与训练归档和双语文档；排除 build/install、私有 Python 环境及无关项目文件。

**Accepted here: synthetic training, read-only perception, offline adaptive policies and legacy motion regression. Integrated force-controlled cup pick-and-place and real-camera accuracy remain pending.**

**本轮核验完成的是合成训练、只读视觉、离线自适应策略及原运动流程回归；完整水杯力控取放和真实相机精度仍待验证。**
