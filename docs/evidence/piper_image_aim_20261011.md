# 2026-10-11 原末段与有限图像瞄准证据

起点 `3b10e99`。唯一生产入口仍 `/home/johnwick/start_brain_robot_cube_real.sh`，实际 executor、TF、TCP、cube_task_real.yaml 未修改。本文件记录真实运动与尚未解决的残差，不是完整一键抓取验收。

## 原轨迹诊断（只规划）

在域78、原模型和 `allow_trajectory_execution=false` 下，用原 `review_surface_grasp_plan.launch.py`、实际同 SHA `target_directed_grasp.hpp`、既有 `review_target_directed_geometry` 生成目标，`review_surface_grasp_plan.py --target-directed --snapshot directed_static_snapshot.json --output directed_plan_response.json` 保存完整响应。

快照由前轮真实点/关节与未改原TF派生，明确 historical_not_live。假设模型开口70mm，不当真实开口。预抓取18路点/17轨迹点，下降11路点/9轨迹点，fraction/code均1。J5预抓取54.625→42.975°，下降末44.801°。这些路径**没有执行**；当前算法由目标射线生成朝向，不包含可见两指中线误差，模型内可达不能消除实体投影偏差。模型world为空不证明桌面净空。

## 新有限瞄准工具与验证

`test/review_camera_jaw_alignment.py` 只订阅原真实反馈/同帧原RGB投影和关联深度，调用原FK、MoveIt/Pilz LIN和参数服务；不创建关节/夹爪publisher或使能client。屏幕参考(150.5,155.5)来自当前320×240原图可见两指自由端区域，只用于瞄准，不是CAD接触点。

按原工厂内参求当前/期望图像射线差，逆D2C旋转到DEP，再用精确图像时刻base←DEP旋转到base，**没有拟合或修改安装平移/旋转**。默认纯图像面平移≤15mm；可选单次前进≤10mm仍受总15mm约束。原LIN vel/acc=.005，原限位校核及全响应保存，真实运动仍由原adapter执行。一个平移段保持当前朝向，不把整个抓取锁为固定朝向。

纯几何11项pytest通过（图像误差收缩、镜像、前进深度、非有限输入、范围），语法校验通过。它是针孔投影的本项目有限平移应用，不是部署完整ViSP控制器。官方方法参考：[ViSP官方眼在手IBVS例](https://github.com/lagadic/visp/blob/master/example/servo-universal-robots/servoUniversalRobotsIBVS.cpp)、[OpenCV投影文档](https://docs.opencv.org/4.5.4/d9/d0c/group__calib3d.html)；官方事实为图像特征/深度可构造相机运动关系，本文实际平移、限幅、原适配器路径为项目实现，不推断供应商保证。

## 一次真实15mm段

原两相机、已部署detector、原 `cube_visual_search.launch.py` 在IDLE有限运行。只读planner参数 `--goal-pixel 150.5 155.5 --maximum-m .015 --output image_aim_plan.json`。36点/3.444444419秒；模型tip弧长15.000002mm，单相邻最大.001503456rad。真实起点199.964Hz/年龄1.106ms；原enable_srv(true)、adapter enable_motion/arm正常（驱动正向使能已不写夹爪），原 `/brain_robot_grasp/arm_trajectory` 只发布一次，adapter日志接受1791727459.496931855。

原图中心(119.844,160.609)→(142.194,157.833)，距屏幕参考误差31.079→8.628px。原时间配对collector后5帧4.422秒，最大跨度92.068ms，已查看0005原RGB、完整方块；detector无新TARGET_LOST。没有闭爪/张爪目标、Disable、ResetPiper或固件动作。

实际末q rad `[-.22136436,1.882870472,-1.271650156,0,.949494364,0]`。J5≈54.402°；规划J6 .044868213rad/2.571°而真实仍0，J4规划.005392547rad但真实0。**不是完整六轴到位**，下一必须用真实末q；adapter逐tick从反馈限幅可能相关但没有本段同步joint_commands，原因不确定，不据此改原反馈防超前。

CLI曾印 `camera_loss` 停止文字，但没有实现专用视觉中断订阅；真实停止是原反馈/限位门与结束disarm，结果JSON已纠正，不能用“没新LOST”替代闭环实现。栈13452手动INT/精确自有组清理exit130，adapter disarm=true，只有原SDK50857/PGID50855保持。实际入口SHA0e976b0a…、executor源码107ce501…、YAML75612194…不变。单次新任务瞄准不重置旧4段采样授权。

## 原始产物与SHA-256

均在 `/home/johnwick/brain_robot_logs/large_j5_view_20261011.7cb6Gu/`（未把大日志/图像加入Git）：

- directed_static_snapshot.json：228a0afac9498e4deebbbd0ea5d1b8155793bbf5a22a117b299bbc152a452147
- directed_plan_response.json：effa26886f8f31097042b6ffb08a5557afaee5e56bb4b4a74558d75b58aea6b8
- image_aim_plan.json：58ae239b129769795db7dd829b5d11b93ce0c153313e1923f97046fce8618393
- image_aim_result.json：22e356ef6113d6356b597e69b6f237c1037b52822df4d8179f9112cd1cf8d7ba
- image_aim_after/observer.jsonl：a7d80f0d776ced493d006d4006d14b512820cb9cc76501423d8d12f5f82588aa
- image_aim_after/evidence/0005_rgb.png：d11e653bc3c4164b7c924f4b81098069af72c96fdfc7f0bc1ed18e40bcf11975

命令/日志还有 image_aim_publish.txt、image_aim_fresh.json、image_aim_plan_client.txt、aim_{astra,color,detector,visual}.log、directed_plan_client.txt/model.log。下一单次最多10mm前进，采同轮目标Depth-Z/原图/命令与反馈，实证靠近方向；不得拿本轮二维改善宣布方块已在两指里或成功抓取。
