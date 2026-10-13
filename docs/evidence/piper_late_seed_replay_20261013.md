# 2026-10-13 近距晚种子离线回放（未实施20cm新策略）

基线96fd749，当前actual仍1cf6423/binarya20a541…、原入口87039b…；无控制/采集进程。本轮不启动ROS/相机/机械臂、不发运动、不改应用/TF/闭爪。上一目标轮有代码/部署/讨论收尾进展，本轮按用户20cm提案只核对历史后续多帧，不能把自动goal continuation当作应用修改同意。

## 新实验与结果

复用attitude_exact/frames.jsonl、attitude_onekey/visual_stack.log、归档URDF/FK review_jaw_scene.poses与原review_near_depth_policy。新只读review_late_rgbd_seed.py按原日志seed..FAULT区间排除cleanup缓存；选择同RGB stamp的raw_point/qualified_box，以及与图像相差≤20ms的latest反馈。没有确切插值图像时刻TF，FK与原rounded surface均为近似。

在20–22cm彩色光轴距离内选择首组三帧，span0.400秒、六轴max range≤.002rad；实际depth Z三帧均.211m，末color Z .211479601m。stamp=[1791898921379776058,1791898921580930372,1791898921780085405]。这里只是历史低运动候选，不是控制器实际停稳/新种子锁定确认；其近似base中值[.430644483,-.120030204,.034155379]未写入控制。

冻结该候选后比较后续92个同帧观测（8921.780085..8943.380045，21.59996秒）：原远距种子的model colorZ与实测差中位数51.733mm、最大64.029mm；晚种子为7.127mm、最大16.854mm。后续J2/J3/J5变化范围.224/.384/.412rad，非全是原地重复同一帧。第一次概略更新称“约21.6cm”，实际选中的三帧为约21.1cm，本文/最终结论以精确数据为准。

两者本次原纯策略回放的尺度/关联均92/92通过；**不能声称晚种子避免了本来会发生的尺度拒绝**。本次证实的是多帧距离一致性改善，不是原控制分支/实体落点/闭爪验收，也不是已标定安装TF。回放freshness/identity/path allowance模拟，原范围与模型未变；相机rotation_calibrated仍false，17mm残余也未消失。

已实际查看历史候选末RGB1791898921780085405_rgb.png：完整紫块靠下、两指可见未包围，不作当前画面或闭爪证据。该候选三帧没有40ms内保存的原生depth附件，末精确stamp的debug图片也不存在（view_image明确失败），因此不能冒充已经查看同帧三图/证明新的可靠重测。raw_point是原检测器同stamp发布的结果，底层native-depth配对仍未独立验收；未来20cm实测必须停稳保存完整同帧证据。

## 复现与状态

命令：PYTHONNOUSERSITE=1 /usr/bin/python3 test/review_late_rgbd_seed.py --capture /home/johnwick/brain_robot_logs/view_guard_20261013/attitude_exact --log /home/johnwick/brain_robot_logs/view_guard_20261013/attitude_onekey/visual_stack.log --urdf /home/johnwick/brain_robot_logs/ego_motion_review_20261013/model/move_group.urdf --policy-bin /tmp/piper_visual_feedback.NhxMgk/build/brain_robot_pick_place/review_near_depth_policy。

replay0/py_compile0，最终输出view_guard_20261013/late_seed_replay_final.json SHAb2203018cb53c26cd19bfbc60683e3d4baa2fbaf5d5bbbc16243825eb2d7ccc6，源SHA15776dbc8117663e177c037ca3ce64503144cb508ec082ca793c8e0f60e38358。第一版硬编码边界改为从log读取FAULT时间后最终重算，相同92帧结果；不把临时版本当最终源。原policy二进制未改。root90%/8.1GB仅固定clean_disk_space.sh0，清后90%无扩删，日志late_seed_disk_cleanup.txt。

下一仍需用户明确确认20cm停稳重测/冻结末段策略，随后只在原拥有组件实施并原入口实测；新策略/最终门尚未授权修改，不继续无意义等待或盲跑。总目标未完成，最后实体使能仅引用上一新SDK1297/六true，不冒充本轮SDK读取；Git仅本轮只读工具/证据/记录、本地，用户原改动和远程历史审查阻断保持。
