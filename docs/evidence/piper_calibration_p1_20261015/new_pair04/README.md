# 第三位置 new_pair04：夹持B已保存，观测A未采

**最新2026-10-15：按用户新授权已重新使能并实际返回观测，SEARCH前STOPPED；随后CAN接收停流，正式A仍0帧/完整1/6。** 新起点q_mdeg[-10826,-44,-77,-1295,18787,-1837]在原任务限位内，enable_srv true+新SDK确认六true/q不变；原arm首命令没有重演J3裁剪，缺陷本身未修改。原17点63.631s轨迹实际85.809s后1792045099.282919033 OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH。末有效ROS q[-.142744252,.941539900,-1.267969472,-.073823008,1.220591568,.081986800]/64.5mm；之后RX9146121/TX42472固定、新8秒SDK80/0fresh，不能把默认q0/false当实体状态。原adapter25秒反馈超时自动disarm，后手动disarm CLI失败，不虚报；全部源已限时退出，无Disable/Reset/开闭/SEARCH。只读桥误传150>原上限120，启动前失败另记，与独立SDK和计数停流证据分开；严格q相等诊断失败及小幅反馈变化也保留，不改原容差。23使能前后预览资产/63原文件压缩/43172消息bag留SHA，预览不是A，B原件及物体同点不默认成立。下一宿主仅USB-CAN断开/重连，保持当前位置；恢复后只读核q并补A，不重走观测/使能。五生产SHA不变，未推送GitHub，见P1/new_pair04/attempt01/reenable_observe。

**最新2026-10-15：第三组已获张爪/原回观测许可，但在张爪前发现原arm隐式J3裁剪，已停止；A0帧，完整仍1/6。** 预SDK匹配B84d8552/58fresh/静止rc0；原stop_after_observe=true回读。1792044192.519 arm后首条命令将实际J3−1.689608396直接改为下界−1.4rad，跳.289608396rad，bag和原_limit_visual_target AST离线复现一致；此时controller仍IDLE，没有张爪/start/观测规划。代理未在arm前识别越界起点，这是控制接管问题，不归咎操作者。原stop/disarm成功；之后新SDK58fresh/静止rc0显示六false、64.5mm/q明显变化，失能根因尚未证实，画面有人手也不据此推断原因或原位。driver3.49s缺流自行恢复，末CAN ERROR-ACTIVE但warning5/passive6971不忽略，无重载。全部源退出，无本代理Disable/Reset/enable false/开闭指令，不自动重新使能或arm。23资产/60原文件压缩/23214消息bag保留，B原件不覆盖，物体同点关系待核对；五生产SHA未变。下一核对支撑/物体原位，并提仅修arm越界接管不发隐式跳变的方案，需批准后改生产；不扩大限位、不重复实机错误。见P1/new_pair04/attempt01/release_observe/README.md；未推送GitHub。

**最新2026-10-15 13:59 +08:00：第三位置new_pair04 attempt01夹持B已纯只读采成，A未采，完整仍1/6。** 用户“已完成第三组抓取”对应本组手摆真夹紧/静止确认，不称自主抓取成功。SDK60/59fresh/q波动0，索引53 J1速度−2mrad/s导致原全窗rc2保持；原连续[1:53]52fresh/5.118834s按原静止规则通过。q_mdeg[-13303,128046,-96859,-9004,49061,29678]、六true/36.2mm；5原RGB-D/同帧Info/实际q/FK/本轮工厂新读/19资产SHA齐全，图已看，c_G及相机几何中心null。只读桥60s/2829发布，本轮源已退出，CAN TX18922始终不变/无恢复或控制命令，五生产SHA不变。相对第一组工具原点211.82mm/z轴12.60°只作真实多样性、不宣称可辨识。第二组仍暂缓，不能混用旧位置B。下一本组原位张爪/原回观测待明确许可，SEARCH前停采A，不进入搜索/ALIGN或抓取。见P1/new_pair04/attempt01/grip_capture/README.md，未推送GitHub。

角色fit，attempt01；这是第三次位置编号，不是第三个已完成标定点对。当前合格完整仍1/6。
第二组new_pair03缺合格A，按用户要求先暂缓，保留全部原数据；不能记成第二组合格。

## 本组清单（1—2已完成，3—5待本组动作许可及A采集）

1. 操作者将同一名义29mm方块放到第三位置，实际夹紧并保持静止，通知完成。不要拿第三位置数据配第二组B。
2. 代理用原只读采集链记录B：新鲜静止SDK≥3秒/30样本、原图、实际q/开口/使能、实际FK及SHA。接触以操作者确认为准，不由照片/开口代替。
3. 按本组动作许可原位张爪，确认未见方块移动，沿既有轨迹返回既定观测。
4. 原stop_after_observe=true设置并回读；SEARCH之前停止，不搜索/ALIGN、不靠近/闭爪，静止采A60帧，至少20帧满足原质量标准。
5. 保存同帧Info、实际q/FK、工厂参数来源、原16位深度/0值/所有拒绝帧和哈希；不填中心、不改门。质量合格并配对完整后才递增计数。

B已保存在[attempt01/grip_capture](attempt01/grip_capture/README.md)，观测A尚未采；没有把当前接触确认扩成已释放且物体原位的确认。
实际runtime为`/home/johnwick/brain_robot_logs/piper_calibration_p1_20261015/new_pair04_attempt01.mYeDDO/`；全部本轮源已退出，原工具拒绝覆盖历史。
夹持B本次严格只读，没有生产driver/adapter/controller/使能/持位。回观测仍须本组动作许可并走原controller→adapter，不新增基础运动程序。
