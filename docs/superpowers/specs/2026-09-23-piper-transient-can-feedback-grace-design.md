# PiPER transient CAN feedback grace design

## Context

The physical arm, USB-CAN adapter, and CAN bus have been independently
verified: the arm reports feedback at about 200 Hz after recovery, a direct V2
SDK command can move J2, and the one-key stack publishes a valid observation
target.  During the visual PREPARE phase, however, the current ROS driver exits
as soon as `piper.isOk()` is false for one publishing iteration.  This removes
`/joint_states`, causing the safety adapter to disarm after its existing joint
state timeout.

The V2 SDK determines `isOk()` from a small rolling CAN-feedback monitor.  On
this VMware + USB-CAN system, measured `/joint_states` gaps have reached about
0.33 seconds even though the normal average rate is near 200 Hz.  Treating one
false result as a permanent hardware loss is therefore too aggressive.

## Goal and success criteria

Allow a transient loss of decoded CAN feedback to recover without terminating
the PiPER ROS driver, while preserving a bounded fail-safe response to a real
loss.

* A first `isOk() == false` sends no further position commands and publishes no
  stale arm feedback.
* If valid feedback returns within 2.0 seconds, the driver resumes publishing
  fresh feedback without a restart.
* If it remains unavailable for 2.0 seconds, the driver follows its existing
  failure path and shuts down; the existing adapter will disarm when its joint
  state timeout expires.
* The change must not auto-reconnect CAN, auto-enable the arm, resend a motion
  target, alter firmware settings, or change joint/gripper control semantics.

## Design

Only `vendor/piper_ros/src/piper/piper/piper_ctrl_single_node.py` changes.

The node records the monotonic time at which `piper.isOk()` first becomes
false.  During the following two-second grace interval it logs one warning,
suppresses feedback publication, and waits for a fresh SDK feedback result.  A
successful result clears the timestamp and logs recovery.  A continuously
false result beyond the interval logs the existing loss/error messages and
calls the current shutdown path.

The direct joint and pose command callbacks will additionally require both the
existing enable flag and a current `piper.isOk()` result before they emit CAN
control frames.  Consequently, no command is sent during the grace interval.
This is deliberately not a reconnect strategy: a sustained loss remains a
safe stop, and a recovered link does not replay any discarded command.

The fixed 2.0-second value matches the already configured joint-state timeout
used by `piper_jog_adapter`, keeping the driver and adapter safety boundaries
aligned without adding a new parameter surface.

## Alternatives considered

1. Keep immediate exit: simplest but contradicted by measured transient gaps;
   it causes avoidable driver loss.
2. Auto-reopen CAN and re-enable the arm: could mask a real cable/bus fault and
   unexpectedly restore motion; rejected for physical safety.
3. Two-second feedback grace with command suppression: tolerates scheduling
   jitter while retaining a bounded fail-safe stop; selected.

## Verification

1. Run a syntax check and a focused source-level check that the grace constant,
   recovery branch, and command-output guard are present.
2. Rebuild only the `piper` ROS package in the VM.
3. Start the one-key stack and press `1`; verify the driver stays alive,
   `/joint_states` continues after any short gap, and the observation trajectory
   starts.
4. Verify that a sustained real CAN interruption still removes fresh joint
   feedback and causes the adapter to disarm rather than continuing movement.

