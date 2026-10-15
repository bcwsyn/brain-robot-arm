# 第二组new_pair03 attempt02：等待新的手动摆位和实际夹紧

本目录目前只是采集计划，不是已采成的数据。P1完整进度仍1/6，第一组new_pair02 attempt02（d80c80c）不变。

操作者选择第二个位置，用同一个名义29mm方块，实际夹紧并保持方块平稳贴桌、不提起；夹爪朝向相对第一组有倾斜变化。摆好后通知代理，只读采新的B：至少3秒/30个新鲜静止SDK样本、5—10帧原图、真实关节/开口/使能、原始时间及实际模型FK。不要拿旧7650461或grounded_recheck的角度作为新位置。

新的运行根目录已空白创建：
`/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015/new_pair03_attempt02.v22Alq/`

未提前创建采集输出JSON/PNG或子目录，避免原采集工具拒绝覆盖。后续可用尚不存在的`grip_rgbd/`、`grip_sdk.json`和`observe_capture/`；没有伪造样本/中心/接触确认。目前不启动ROS/SDK、使能、运动或开闭夹爪，也不沿用户已叫停前的动作许可自动续跑。

**夹持侧B只复用receive-only SDK桥与原相机/只读采集器，不启动生产driver、adapter、controller，也不调用使能/arm服务。** 先完成静止B并提交，再进入另行确认的释放/返回阶段；不为拍B提前接入关节持位输出。

B完成并保存检查点后，才根据本次摆位确认原位释放/原回观测许可；不夹着方块返回。沿原controller→adapter轨迹返回固定观测、SEARCH前停止，再只读采60帧/至少20好帧A。两边必须同一个未移位方块，新A只配本次新B；生产算法/门/TF/TCP/模型/入口保持冻结。

旧记录均在原路径保留，登记为不参与本次拟合：`../grip_capture/`、`../release_observe/`及`../closed_attempts/`。不删除原图、深度0值或失败窗，不因新attempt覆盖旧哈希；new_pair03仍是预定fit组，new_pair07仍是留出组。
