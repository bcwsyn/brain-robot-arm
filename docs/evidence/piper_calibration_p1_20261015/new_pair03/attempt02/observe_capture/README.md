# 第二组 attempt02：已回观测，A原始120帧，合格0帧

本组尚未完整，P1仍 **1/6**。B检查点为 `63da2d9`，只与这次原位置A配对，不混旧attempt。生产算法、门、TF/TCP、模型、限位、一键脚本均未修改。

## 已执行和实际反馈

用户授权本组原位张爪、原轨迹回观测且SEARCH前停止；此前实际开口37.1→99.4mm，张爪前后原图经背景补偿方块中心差约0.70px，仅说明未见显著移动，不证明三维零位移。首个返回请求因反馈停流被拒，未发轨迹；原证据和完整ROS bag见[释放记录](../release_observe/README.md)。

用户确认VMware USB-CAN重连后，新ifindex11原为DOWN，仅按已批准1Mbps/.75/queue1000/UP激活，RX恢复。不再张爪、不重采B、不重载模块、不复位硬件。
原controller/adapter发布13点44.5s轨迹，1792041364.726550970明确：
`OBSERVE_POSE_REACHED_STOPPED_BEFORE_SEARCH`。
实际q_mdeg=[-7989,54577,-72577,-4358,69694,5233]，不是用目标值代替实际反馈；99.4mm。详细服务、轨迹时间和停止结果见[执行记录](return_execution.json)。没有进入SEARCH或抓取，没有发送Disable/Reset。

## A采集与质量

返回后第一采集因只读桥尚未发现而0帧，随后预览因有界相机退出而0帧；[原报告](startup_failures/)保留。只重开只读图源/桥，不重走实体轨迹。预览3帧；随后原P0工具两批各60帧，44.61s/43.65s，采集本身rc0，质量总rc2并按原上限停止。

120正式帧中 **0个合格顶面**。目标彩色完整可见，但实际深度支持仅25—93点/帧，覆盖3.73%—10.00%，中位6.48%。所有帧均拒绝“Insufficient measured face coverage; edge/background samples do not define cube center”。不能用边缘/背景稀疏中位数当方块面或几何中心，不能靠放宽800内点门、填深度或多采同一画面制造成功。
[原完整质量报告](p0_report.json)、[逐帧深度复核](portable/depth_review.json)、[已查看的衍生叠图](witness_review/annulus_witness_0001.png)、[结论](assessment.json)。

SDK100/99fresh、实际六q波动0；全窗因速度脉冲原rc2保留。原连续samples[29:100]为71fresh/7.028s，经原summarize静止检查通过，不覆盖全窗失败旗标。每图实际q/时间/FK、原16位深度（含0）、原RGB、同帧内参、同机新读完整D→C工厂参数均保存。C系中心和夹持侧未知中心仍null，不进入P2拟合。

## 数据与停点

[portable/manifest.json](portable/manifest.json)列259资产、18,957,143B及逐项SHA；含3预览+120正式完整图对。
manifest SHA-256：`495061ae532f9bafe9f536eb86935689011f534a32648e4c202975d6e25b517c`。
原始return_visual_stack_trace.txt含供应商日志行尾空格；observe_service_trace.txt有原始尾部空行，均保留字节。Git仅这两个原日志临时关闭对应blank-at-eol/blank-at-eof检查，其他文件正常检查，不修改全局配置。

收尾并非全部子进程干净退出：虽然launch包装器rc0，在到观测并主动SIGINT之后，move_group析构报段错误（-11），depth_cube_probe重复shutdown报rc1，adapter退出时rosout context无效。原栈和错误均保留于return_visual_stack_trace.txt；这些发生在到位后退出阶段，不伪称轨迹失败或当前采集质量根因，也不在生产冻结期间顺手修补。

本轮源均退出。最后新鲜SDK六true/99.4mm；退出后没有新读，不把末次状态当实时承诺。CAN末RX1479900/TX8569、ERROR-ACTIVE/error0；只读采集TX8569不变。当前阻断是观测侧目标深度质量，不是CAN仍断、IK或微量阈值超限。根55%/34GB可用，共享73%/136GB可用，无数据删除。

下一先保留方块/本组B，针对“完整RGB但目标深度稀疏”拟定一个有限对照。涉及新观测姿态、场景/材料或相机参数时先具体说明并获批；不自动移动方块，不再重走张爪/返回，不重复已耗尽两批的同条件采集。数据本地归档不等于GitHub已推送。
