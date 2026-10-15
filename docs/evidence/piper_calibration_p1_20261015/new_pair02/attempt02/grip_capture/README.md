# new_pair02 attempt02：新位置夹持侧B（2026-10-15 11:30 +08:00）

操作者明确确认：“已被两指实际夹紧，选择一个新的位置，待记录后代理张开夹爪、回观测记录第一组”。本包只读采集在回复期间完成；实际接触依据是用户后续确认，不是37.4mm开口/照片自行证明。原export sample_id的contact_pending保留生成时状态，不改原字节；当前此README记录确认后状态。原sample只有8张近距图，不是观测侧A，正式点对仍0/6。

## 数据与原值

- `portable/manifest.json`：27资产、1,129,460 bytes（不含manifest），5夹持候选RGB-D+3预览RGB-D、完整同戳depth Info/实际q、SDK、工厂K/D/R/T/内部TF、原配置、实际模型FK和全部SHA。`observation_capture=grip_candidate_rgbd`是导出器通用分析目录字段，不代表这里已经取得A。
- SDK原6秒，60/59fresh、5.820880175s、原静止条件全部通过rc0，六q波动0/速度0/六enabled=true/开口37.4mm。q_mdeg=[10550,106332,-58733,-504,32456,-8654]，q_driver_rad=[.1840342,1.854855408,-1.024538452,-.008791776,.566162464,-.150960376]。effort原-84非牛顿，不据它证明接触力。
- 5夹持图rc0/7.659285s，3预览rc0/6.737022s；q与SDK一致，异戳Info照旧拒绝（2/3次），未改采集门。已看首预览和第5夹持原RGB，方块在两指之间；近距原深度目标无有效表面保留，不能当观测质量失败或拟合中心。
- 原factory helper当前新读成功，CC1365304DG、内部光学TF保存；无需重测7cm/10.5cm，未改安装TF。工具原点基座位置[.333526642173882,.061643311552050,.141870156619624]m，完整T在depth_review各帧，工具内方块中心c_G仍未知，不填0。

## 边界和下一步

本包runtime为`/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015/new_pair02_retake_preview.4PMunD`。本轮目前只读/无CAN控制、使能、运动、开闭、Reset或Disable；正常链路复用，未改生产代码/TF/门/模型/限位。先Git保存此B，随后执行已授权仅本组原adapter张爪、核原图方块未明显移动、原controller stop_after_observe=true原轨迹回既定观测，采新A60帧≥20好帧。若方块移动/出画需如实记录，不能混旧attempt01位置或冒称点对完成。
