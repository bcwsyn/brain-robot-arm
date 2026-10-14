# Source provenance / 源码来源

The seven packages are independent simulation copies adapted from `bcwsyn/brain-robot-arm` commit `6ebd0c53ca830ac4071b8e64fcc1954dbf5a8cf1`. The historical repository tree remains available under `brain_robot_arm/`. Subsequent simulation development implements explicit ownership, randomized scenes, contact-based physical retention, release and return home. It is recorded by the bilingual stage report and versioned evidence.

七个包来自上述固定版本，按独立仿真工作区适配。后续改动包括控制权交接、随机场景、物理接触保持、释放与回零。历史目录保留；导入时与后续验收版本的哈希不互相改写。

Package license declarations are retained. Upstream Piper source and assets originate from the vendored Piper ROS tree; its MIT license is retained in [LICENSE.piper_ros](LICENSE.piper_ros) and the original [vendor license](../brain_robot_arm/vendor/piper_ros/LICENSE). Individual package declarations are also preserved, including their original Apache/BSD declarations and historical placeholder fields. This document does not assign a new blanket license to third-party content.

保留包内原有许可证声明及 Piper 上游许可证。部分生成配置包的历史元数据仍有占位许可证字段，本文件不替第三方资源重新指定统一许可证。Pre-change/accepted source snapshots and raw trial records are under `validation/physics_grasp/`; they document distinct source versions rather than a reusable precompiled environment.
