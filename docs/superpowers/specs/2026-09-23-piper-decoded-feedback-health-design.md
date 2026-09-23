# PiPER decoded-feedback health design

## Context

The transient-CAN grace logic exposed that `C_PiperInterface_V2.isOk()` is not
a suitable health source on this VMware + USB-CAN deployment.  During a
25-second capture made while visual PREPARE was active, a separate raw
SocketCAN consumer received 744 to 776 frames in every 0.25-second interval;
there were no zero-frame intervals.  At the same time the PiPER ROS driver
reported `isOk() == false`, first recovering after 1.52 seconds and later
exiting after the two-second safety grace.

The SDK's `isOk()` is driven by its internal parser-frame FPS queue rather
than by the kernel SocketCAN receive stream.  It can become false if that
internal monitor is not incremented even while the bus remains active.

## Goal and success criteria

Use fresh, successfully decoded PiPER joint feedback as the driver's health
criterion, without weakening the fail-safe response to a real loss of usable
arm feedback.

* Continuous decoded joint feedback keeps the driver active even if the SDK
  FPS monitor reports false.
* A stale decoded joint-feedback timestamp immediately suppresses new pose and
  joint commands.
* If that timestamp remains stale for 2.0 seconds, the driver shuts down as
  before and the existing adapter disarms.
* Raw CAN packet counts alone must not authorize motion, because unrelated
  devices could generate packets on the same bus.
* No automatic reconnection, re-enable, command replay, firmware operation,
  or new configuration parameter is introduced.

## Design

Only `vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py` changes.

The existing `_can_feedback_available()` helper will replace its
`piper.isOk()` check with the timestamp from
`piper.GetArmJointMsgs().time_stamp`.  The timestamp is set by the SDK only
after it has decoded PiPER joint feedback, so it validates the exact data that
the ROS driver converts into `/joint_states`.

The helper considers feedback current while its age is at most 0.5 seconds.
This permits normal scheduler jitter but is far below the existing two-second
failure window.  A zero timestamp is treated as unavailable.  The existing
two-second monotonic grace timer, recovery logging, suppressed ROS feedback,
and guarded pose/joint output remain unchanged.

The deliberate separation is:

1. **0.5 s freshness threshold**: detect that decoded arm state has stopped
   advancing.
2. **2.0 s stop threshold**: give an intermittent schedule delay time to
   recover, then retain the existing safe exit.

## Alternatives considered

1. Keep SDK `isOk()`: disproved by a continuous raw-CAN capture while it
   reports failure.
2. Use raw SocketCAN packet arrival: unsuitable as a motion authorization
   signal, since it does not prove those packets are valid PiPER joint state.
3. Use decoded joint-feedback timestamp with the existing grace timer:
   directly tests fresh arm state and preserves safe failure behavior;
   selected.

## Verification

1. Run syntax and focused source checks for timestamp freshness and the two
   thresholds.
2. Rebuild only the `piper` package in the VM.
3. Run one-key startup and press `1`; verify the driver stays alive through
   PREPARE and the arm reaches the observation pose.
4. Confirm `/joint_states` timestamps advance while the arm is moving.
5. For a real loss of decoded feedback, verify command suppression and the
   existing two-second shutdown/disarm behavior.

