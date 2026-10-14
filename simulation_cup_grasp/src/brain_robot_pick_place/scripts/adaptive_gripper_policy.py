"""Measured-width opening and bounded contact-force policy, independent of ROS.

This policy requires contact forces in newtons. SDK motor torque is a different
quantity and must not be passed here without a validated conversion. Calling
the policy alone does not establish object retention or real force calibration.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class OpeningPlan:
    opening_m: float
    left_joint_m: float
    right_joint_m: float
    width_upper_bound_m: float


def opening_from_measurement(width_m, sigma_m, age_s, *, stroke_m=.100,
                             clearance_m=.006, maximum_sigma_m=.004):
    """Use a conservative image/depth width bound; never clamp an oversized target."""
    values = (width_m, sigma_m, age_s, stroke_m, clearance_m, maximum_sigma_m)
    if not all(math.isfinite(x) for x in values):
        raise ValueError('nonfinite width estimate or opening configuration')
    if not 0 < width_m <= stroke_m or not 0 <= sigma_m <= maximum_sigma_m:
        raise ValueError('width estimate is outside the stroke or too uncertain')
    if not 0 <= age_s <= .5 or clearance_m < 0 or stroke_m <= 0:
        raise ValueError('stale estimate or invalid opening configuration')
    upper = width_m + 2 * sigma_m
    opening = upper + clearance_m
    if opening > stroke_m:
        raise ValueError('uncertainty and clearance exceed available stroke')
    return OpeningPlan(opening, opening/2, -opening/2, upper)


@dataclass(frozen=True)
class ForceDecision:
    next_opening_m: float
    state: str
    force_in_band: bool = False
    fault: bool = False


@dataclass(frozen=True)
class ContactForcePolicy:
    """Adjust total opening from two measured pad normal forces.

    All force thresholds are configurable simulation control settings, not cup
    strength estimates or manufacturer torque limits. The integration layer
    must enforce task timeout, stable holding, cancellation and object retention.
    """
    stroke_m: float = .100
    minimum_force_n: float = 1.2
    maximum_force_n: float = 2.5
    hard_force_limit_n: float = 5.0
    closing_speed_m_s: float = .004
    response_m_per_n_s: float = .002

    def __post_init__(self):
        values = (self.stroke_m, self.minimum_force_n, self.maximum_force_n,
                  self.hard_force_limit_n, self.closing_speed_m_s, self.response_m_per_n_s)
        if not all(math.isfinite(x) and x > 0 for x in values) or not (
                self.minimum_force_n < self.maximum_force_n < self.hard_force_limit_n):
            raise ValueError('invalid contact force policy')

    def step(self, opening_m, left_force_n, right_force_n, feedback_age_s, dt_s,
             *, cancelled=False):
        # opening_m is the current commanded total opening. With a rigid cup,
        # measured jaw position stops at contact; resetting the command to that
        # position on every tick would erase the PID preload and lose force.
        if cancelled:
            return ForceDecision(opening_m, 'STOP_CANCELLED', fault=True)
        values = (opening_m, left_force_n, right_force_n, feedback_age_s, dt_s)
        if not all(math.isfinite(x) for x in values) or not (
                0 <= opening_m <= self.stroke_m and left_force_n >= 0 and
                right_force_n >= 0 and feedback_age_s >= 0 and 0 < dt_s <= .1):
            return ForceDecision(opening_m, 'STOP_INVALID_FEEDBACK', fault=True)
        if feedback_age_s > .2:
            return ForceDecision(opening_m, 'STOP_STALE_FORCE_FEEDBACK', fault=True)
        peak, low = max(left_force_n, right_force_n), min(left_force_n, right_force_n)
        maximum_step = self.closing_speed_m_s * dt_s
        if peak > self.hard_force_limit_n:
            return ForceDecision(min(self.stroke_m, opening_m+maximum_step),
                                 'BACKOFF_OVERFORCE', fault=True)
        if peak > self.maximum_force_n:
            change = min(maximum_step, self.response_m_per_n_s *
                         (peak-self.maximum_force_n) * dt_s)
            return ForceDecision(min(self.stroke_m, opening_m+change), 'RELIEVE_FORCE')
        if low >= self.minimum_force_n:
            return ForceDecision(opening_m, 'BILATERAL_FORCE_IN_BAND', force_in_band=True)
        if opening_m <= .001:
            return ForceDecision(opening_m, 'STOP_NO_CAPTURE_AT_MINIMUM_OPENING', fault=True)
        target = (self.minimum_force_n+self.maximum_force_n)/2
        change = min(maximum_step, self.response_m_per_n_s * (target-low) * dt_s)
        return ForceDecision(max(0, opening_m-change), 'CLOSE_UNTIL_CONTACT_FORCE')
