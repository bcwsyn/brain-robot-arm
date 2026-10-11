# 机械臂使能与夹爪目标解耦（2026-10-11 20:25）

起点 `39783f9`。没有实体使能请求、轨迹、夹爪命令、回零或失能。修复加载了新反馈驱动，但未证明整个抓取链完成。本轮是普通可逆源码最小修改，不扩大已有实体预算。

## 实际代码证据与修复

实际console入口映射 `piper_single_ctrl = piper.piper_ctrl_single_node:main`，不是目录内旧 `piper_ctrl_single_node_new.py`。规范和部署原源码SHA相同 `f2631dfe941abaaa1ad2839f20ef22666c138b23d66275a7fd476c65d2cf8edc`，本轮修改前这两个指定规范路径均无用户既有改动。其他vendor/reference/测试样式文件改动保留，不纳提交。

使能话题入口旧代码直接调用 GripperCtrl(0,1000,0x02,0)、(0,1000,0x01,0)。使能服务旧代码取夹爪缓存，超过80000就回退0，仍发上述夹爪命令；当前历史缓存0.1019m对应101900，会进入这个分支。这是代码中可复现的意外闭爪通道，不证明历史每一次异常都由它引起。

只删除**正向机械臂使能**中的夹爪目标写入，保留六轴EnablePiper/关节模式、服务应答、失败门和既有失能分支。机械臂使能后保留 _gripper_clear_pending=True；已有显式夹爪命令第一帧在它请求的目标上用0x03，随后0x01，仍set_zero=0，未加开口/抓取门或取消开闭功能。六轴无gripper名字的命令仍只发六轴。未改相机/末段方向/实体YAML/adapter/executor/默认入口。

本机实际SDK `/home/johnwick/.local/lib/python3.10/site-packages/piper_sdk/interface/piper_interface_v2.py` 只读源码显示EnablePiper取GetArmEnableStatus、EnableArm(7)、返回all(enable_list)，不含GripperCtrl；没有实例化新SDK或CAN发送。不能把本轮假SDK验证当真实开闭/硬件标定通过。

## 针对性验证

从 `git show 39783f9:<driver路径>` 与新源码分别编译**单函数**，用假SDK、假clock、不导入/启动ROS节点。缓存101900且gripper_exist=true时旧话题/服务均记录 [[0,1000,2,0],[0,1000,1,0]]，新两入口记录[]，两者均保留arm_enabled=true。不是仅字符串/AST存在性测试。

既有test_command_validation扩展行为回归：2个正向入口×4个缓存×2个gripper存在配置，全不写夹爪、六轴使能和pending标记保留；使能失败不放开门/不注入夹爪；六轴保持无夹爪，显式50mm帧仍50000/1000/0x03→0x01、set_zero0。首先测试私有名被unittest类名重整导致AttributeError，已更正getattr，非生产失败。第一次合并测试覆盖PYTHONPATH而漏ROS，74通过/2跳过，不当全通过；随后保留原ROS路径，最终**77通过/无跳过**（驱动8项+原四组69项）。

复现：source /opt/ros/humble/setup.bash，设 `PYTHONPATH=/mnt/hgfs/ub/brain_robot_arm/vendor/piper_ros/src/piper:"$PYTHONPATH"`、PYTHONNOUSERSITE=1/PYTHONDONTWRITEBYTECODE=1，pytest -q -p no:cacheprovider 指定 test_command_validation.py 与 test_static_rgbd.py/test_startup_script.py/test_jaw_scene_review.py/test_calibration_sampling.py。未跑含用户改动的全vendor测试目录。

新规范/部署驱动SHA `c0153c88e0e5ac5ff9d8d1b299e4c911c62e14b8f0834e25d5c0d67f6de299cb`；回归SHA `0c014510970b5ade4bfe8505b9a9009f2966f85e17b0cd091f957dd54cec6d91`。回退本轮提交、同步此driver文件并在保持位置/不失能条件下按正常受控生命周期加载即可；不得用文件回退声称内存中老/新节点也已改变。

## 实际加载与静止结果

只对先前本轮标记 `BRAIN_ROBOT_LOG_DIR=/home/johnwick/brain_robot_logs/real_static_20261011.IrUxSo/stack` 的组47039，完整核成员47039/47043后发送TERM。随后轮询的/proc/47039/environ在终止期间PermissionError，使该诊断脚本中断；TERM已经发送，不能说“完全没动作”，也不能据此又诊断共享目录写权限。

后验wrapper已退出，但SDK child47043仍存活。再次核同标记、UID、PGID47039及start_ticks2367737，精确KILL **PID47043**；核没有其他实际SDK实例后才起替代，未重现先前双驱动重叠。驱动main最终清理没有DisableArm调用，未发失能服务/帧，CAN未down/up/reset。

source原ROS/piper_ros/piper_ws/现UDP配置，普通/usr/bin/Python保留用户can依赖，PYTHONDONTWRITEBYTECODE=1。新目录 `/home/johnwick/brain_robot_logs/arm_enable_fix_20261011.2wUnGP`，同一驱动：

```bash
ros2 run piper piper_single_ctrl --ros-args --log-level WARN \
  -p can_port:=can0 -p auto_enable:=false -p gripper_exist:=true \
  -r joint_states_single:=/joint_states -r joint_ctrl_single:=/joint_commands
```

Wrapper50855/SDK50857，PGID50855，后验唯一；实际Python导入模块路径为 /home/johnwick/piper_ros/src/piper/piper/piper_ctrl_single_node.py，SHA c0153c88…；不是未加载的备用文件。没有服务使能、夹爪/轨迹操作，auto_enable=false。只读订阅新feedback3秒获595样本，首1791721090115437472ns、末1791721093085893224ns，六轴范围0，q仍 [-.262724084,1.888278112,-1.280686148,.0095942,.836928232,0]。未读新硬件六使能位；“未发Disable”不等于新使能测量。

当前旧47043已被替代，下一代理不得沿用上两条的存活PID。原一键0e976b0a…/executor源码107ce501…/YAML75612194…未变，控制栈/相机没有启动，只有反馈50857及非控制daemon47019，无自动续跑。

## 可在旧预算内的下一候选，不是执行结果

用新静止15组最后q与归档实际URDF、现.1358m tip，对 **J4+1°→回原中心→J5+1°** 三段，各101点FK：tip弧长2.940502/2.940502/3.958407mm，最大距段起点2.940465/2.940465/3.958357mm；三段9.839412mm，加前已用3.958357mm=13.797769mm，4段内。由此更正“完整八段1度27.6mm超预算”不等于所有多轴小段必然超预算。

尚未做此三段的实时MoveIt碰撞/轨迹、实际桌面间隙或执行；未把FK曲线转发给adapter，未重跑旧8段隔离规划。不以三段模型检查声称实际可采/可抓；小角是否能给真实自然纹理足够激励仍需实测、独立验证，不能凑同姿态15帧或恢复旧候选。下一动作先用原高级MoveIt→adapter核这个有限候选，逐段可靠时间配对/看图、不闭爪；扩大±6°仍需新范围。当前相机→实际夹持区对应和抓取未完成。
