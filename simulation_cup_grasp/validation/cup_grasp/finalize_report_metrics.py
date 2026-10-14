"""Finalize report metrics only after the complete frozen suite passes."""
from pathlib import Path
import json,hashlib

ws=Path(__file__).resolve().parents[2]
root=ws.parent
v=ws/'validation/cup_grasp'
data=json.loads((v/'acceptance_r8_final/results.json').read_text())
assert data['passed'] and data['complete'],'Frozen final suite is not complete/passing'
metrics=[r for c in data['cases'] for r in c.get('metrics',[])]
assert len(metrics)==9 and len(data['cases'])==8
stats=dict(maximum_placement_error_m=max(r['placement_error_m'] for r in metrics),
 minimum_hold_span_sim_s=min(r['hold_span_sim_s'] for r in metrics),
 minimum_peak_lift_m=min(r['peak_lift_m'] for r in metrics),
 maximum_home_error_rad=max(r['home_error_rad'] for r in metrics),
 maximum_final_tilt_rad=max(r['final_tilt_rad'] for r in metrics),
 holding_force_range_n=[min(b[0] for r in metrics for b in r['hold_force_range_n']),
                       max(b[1] for r in metrics for b in r['hold_force_range_n'])])
report=dict(status='final r8 fixed simulation suite passed',all_passed=True,
 positive_count=9,negative_count=5,revision='stage5-force-bridge-r8-final',
 cases=data['cases'],metrics=stats,
 model_sha256=hashlib.sha256((ws/'models/cup_yolov8n_seg_v2.pt').read_bytes()).hexdigest(),
 gui=json.loads((v/'gui_validation.json').read_text()),
 core_tests='91 tests, 0 errors, 0 failures, 0 skipped')
(v/'final_acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
cn='''最终冻结版本r8完整执行：75 mm **5/5**，55 mm **2/2**，85 mm **2/2**；5种负测均通过（偏位没有双侧夹持就不抬升、抬升中反馈丢失、合成6 N过载、中途停止、105 mm超开口视觉拒绝）。所有组源码哈希未变。前序r6/r7对照通过与失败单独保留，本表只统计最终r8。

| 指标 | 最终9次取放 |
| --- | --- |
| 最大三维放置误差 | %.3f mm |
| 最短实测保持跨度 | %.2f仿真秒 |
| 最小峰值实际抬升 | %.2f mm |
| 最大回零关节误差 | %.7f rad |
| 最大最终杯轴倾斜 | %.7f rad |
| 保持阶段全部双侧力样本范围 | %.3f–%.3f N |

最终GUI：S完整取放通过，R重建重新就绪，B区选择、X在放置下降中停止、Q清理均验证；GUI成功轮次独立统计，放置误差约0.731 mm，保持时轴TF最大延迟21 ms。抬升中停止由固定负测另验。核心91项汇总检查通过；独立发布目录从空build/install构建七包成功，核心91项通过。发布物理试验和归档恢复/远端核验见相应回执。

曾扩展检查全工作区：当时187项汇总、74失败，均来自未改上游版权/格式；13个相关Python/CMake文件与第四步Git blob一致。新增用例后核心变为91项，此处没有把全工作区lint标成通过。保留完整失败输出和对比证据。

原始固定结果：`simulation/validation/cup_grasp/acceptance_r8_final/results.json`、`final_acceptance.json`、各会话`session.json`。判据为实际抬升≥50 mm、保持≥3仿真秒、每个保持力样本双侧2.5–3.5 N且新鲜健康、放置误差<30 mm、回零<0.02 rad、倾斜<0.12 rad、物理释放及无非零Servo指令。

''' % (stats['maximum_placement_error_m']*1000,stats['minimum_hold_span_sim_s'],stats['minimum_peak_lift_m']*1000,stats['maximum_home_error_rad'],stats['maximum_final_tilt_rad'],*stats['holding_force_range_n'])
en='''The complete frozen final r8 suite passed: **75 mm 5/5**, **55 mm 2/2**, **85 mm 2/2**, plus all five negatives (missed bilateral capture, lost feedback during lifting, synthetic 6 N overload, mid-lift stop and visual rejection of a 105 mm oversized cup). Every group retained unchanged frozen source hashes. Earlier r6/r7 results and failures remain separate and are not added to this denominator.

| Metric | Final nine positives |
| --- | --- |
| Maximum 3D placement error | %.3f mm |
| Minimum measured holding span | %.2f simulation s |
| Minimum peak physical lift | %.2f mm |
| Maximum homing joint error | %.7f rad |
| Maximum final cup-axis tilt | %.7f rad |
| Range of every bilateral holding-force sample | %.3f–%.3f N |

GUI validation passed a complete S sequence, full R recreation/readiness, B selection, X cancellation during release lowering and Q cleanup. The independent GUI success had approximately 0.731 mm placement error and at most21 ms jaw-axis TF age; mid-lift cancellation is separately covered by the frozen suite. Core checks:91 aggregate, zero errors/failures/skips. The publication workspace built seven packages from empty build/install and passed91 core checks. Publication motion, archive restoration and remote checks have separate receipts.

An earlier expanded scan covered187 aggregate checks with74 vendor copyright/style failures;13 relevant Python/CMake files match stage4 Git blobs. Core checks subsequently increased to91. Upstream lint is not reported as passing; full failure logs/comparison are retained.

Evidence: `simulation/validation/cup_grasp/acceptance_r8_final/results.json`, `final_acceptance.json` and each saved `session.json`. Criteria: actual lift≥50 mm, holding≥3 simulation s, every stationary-hold force sample bilateral/in-band/fresh/healthy, placement<30 mm, home<0.02 rad, final tilt<0.12 rad, physical release and no nonzero Servo jog.

''' % (stats['maximum_placement_error_m']*1000,stats['minimum_hold_span_sim_s'],stats['minimum_peak_lift_m']*1000,stats['maximum_home_error_rad'],stats['maximum_final_tilt_rad'],*stats['holding_force_range_n'])
for name,text in [('第五步_水杯视觉估径与力反馈抓取开发与验收.md',cn),('stage5_cup_grasp_report.en.md',en)]:
 p=root/'docs'/name;s=p.read_text();a=s.index('## 5. ');b=s.index('## 6. ',a)
 title='## 5. 最终验收数据\n\n' if name.startswith('第五步') else '## 5. Final acceptance\n\n'
 s=s[:a]+title+text+s[b:]
 s=s.replace('最终版本验收正在整理，本文件完成时会填入最终固定批次和发布核验数据。','最终固定批次和窗口验收已完成；发布核验和归档回执随发布记录补齐。')
 s=s.replace('Final frozen results and publication verification are being collected; the results section will be finalized afterward.','Final frozen simulation and GUI acceptance are complete; publication/archive verification has separate receipts.')
 p.write_text(s)
print(stats)
