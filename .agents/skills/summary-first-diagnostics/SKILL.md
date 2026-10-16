---
name: summary-first-diagnostics
description: Reduce wall-clock time and redundant work in real-device diagnostics and high-volume ROS/CAN, log, JSON or Git inspection. Reuse valid evidence, plan discriminating bounded experiments, and aggregate before reading raw output. Preserve required instructions, freshness and full requested reviews.
---

# Summary-first diagnostics

Prioritize time to a verified task outcome over token savings. Reduce redundant experiments and data returned to the model, not evidence quality or required observation periods. This skill does not authorize motion, recovery, configuration changes or deletion.

## Spend real-device time on progress

- **Reuse with validity conditions.** Before repeating a test, consult its result and relevant source/deployed hashes, configuration and device/setup identity. Reuse only while its assumptions hold; state what changed or invalidated it. A successful parser/build/trajectory test can avoid unrelated retesting, but never substitutes for fresh joint/enable/target feedback. Reboot, reconnect, mount/scene changes or stale data can invalidate different parts independently.
- **Make each attempt discriminate.** Briefly state the question, expected observable result, success condition, bounded window and failure branches before running. Prefer an existing proven path and the smallest authorized experiment that separates plausible causes. Do not repeat an identical failed attempt without new evidence or a changed condition; inspect its failure first. These notes belong in the existing work record, not another planning framework.
- **Stay on the evidenced blocker.** Once a cause or failing owner is localized, use focused offline replay/tests before another real attempt. Build/test only affected components and dependencies where justified; do not restart CAN/TF/limits surveys, full builds or passed motion experiments without a reason. Offline success does not prove physical success.
- **Reduce orchestration overhead.** Batch independent read-only inspections and complete coherent fixes within the approved scope. Reuse valid existing approvals rather than asking again; still obtain required approval before new code changes, motions or scope expansion. Keep one physical control owner; do not overlap competing probes or CPU-heavy analysis with timing-sensitive capture/control just to claim parallelism.
- **Measure, then optimize.** Use existing logs or lightweight monotonic start/end timing for preparation, build/deploy, observation/wait, motion and analysis; mark unmeasured time unknown. Report total wall time, the dominant stage and what advanced or which hypothesis was eliminated. Overlapping stages are not additive. Do not rerun an experiment merely to fill missing timings or claim speedups without a comparable baseline. Shorten avoidable overhead, not required checks; this is not a new robot gate or mandatory instrumentation project.

## Workflow

1. State the question and select the least expensive evidence that answers it. Reuse existing summaries and verified project tools before writing another collector. Check source ownership before opening devices; do not start duplicate camera sources or competing probes.
2. Aggregate and filter **inside the terminal before tool output**. Return counts, ranges, freshness, failure categories and a few relevant excerpts, not entire message streams or large JSON payloads. Tool-output truncation is not aggregation and can hide errors. Avoid unbounded `ros2 topic echo`, `candump` or image-array dumps.
3. Choose a finite observation window appropriate to the task. Preserve already required durations; reducing model input does not shorten a required 60-second check. Bound retries, wall time, buffers and diagnostic output; clean up only owned probes. Use a forced-exit grace where appropriate, e.g. `timeout -k 2s 5s ...`; preserve the real exit code and timeout reason, not a false “no data” result.
4. Return a compact summary, normally about 20 lines or fewer: question, source/interface identity, actual window, measurements, conclusion, limitations, exit/timeout/cleanup status and raw-artifact path when retained. Expand when correctness requires it; this is not a new acceptance threshold.
5. If the summary is inconclusive, inspect the specific failing time range, fields or representative images. Escalate from counters to semantic statistics to targeted raw evidence, not automatically to a full dump or another identical run. Prefer one bounded probe over many concurrent CLI subscribers.

## Match evidence to the claim

- **CAN presence:** compare `ip -j -s link show dev can0` snapshots; aggregate RX/TX/error deltas locally. Record boot/interface identity (including ifindex) and elapsed time. A re-created interface, counter decrease/reset, missing snapshot or failed command makes that window inconclusive, not a negative packet count or proof of no traffic. Counters cannot exclude every reconnect/reset; disclose identity gaps.
- **CAN continuity:** use time-bin counter deltas for coarse no-growth intervals. Do not call them exact inter-frame gaps. If exact gaps or individual feedback IDs matter, use a bounded receive-only parser and return its statistics. Total RX growth alone does not prove all six joint/enable/gripper streams are fresh or that movement succeeded.
- **ROS/camera:** distinguish discovered publishers from delivered messages; summarize received count, source-stamp progression, ages and relevant field validity. `ros2 topic hz` measures that subscriber's receive rate, affected by resources and QoS; do not diagnose the publisher or change DDS/QoS from this measurement alone. Choose representative images only when scene/geometry matters.
- **Logs/JSON/Git:** use `rg`, structured field extraction and scoped diff/status summaries first; then read relevant context, not whole unrelated histories or inventories. Preserve complete required instruction reads, requested code reviews and necessary diffs. A summary cannot substitute for evidence the task explicitly requires.

## Preserve meaning and scope

Keep raw calibration/evidence bytes, timestamps, original failures and existing retention rules. Save required raw artifacts without printing them into the conversation; do not start unlimited logging or delete data to save tokens. An expired probe, permission failure, stale/default value and verified zero traffic are different outcomes.

Do not add robot execution gates, weaken existing checks or treat receiving/decoding/planning/execution as equivalent. For PiPER, `ros2-piper-debug` determines diagnostic meaning and runtime paths; `surgical-change` governs code edits. Their authorization and repository rules still apply. Savings depend on actual tool output and reuse; do not promise a token or latency reduction without measurement.

## Sources

- [OpenAI: skills and progressive disclosure](https://learn.chatgpt.com/docs/build-skills)
- [Linux kernel: interface statistics, JSON and counter semantics](https://docs.kernel.org/networking/statistics.html)
- [ROS 2 Humble official tutorial source: topic discovery and subscriber rate caveat](https://github.com/ros2/ros2_documentation/blob/humble/source/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Topics/Understanding-ROS2-Topics.rst)
