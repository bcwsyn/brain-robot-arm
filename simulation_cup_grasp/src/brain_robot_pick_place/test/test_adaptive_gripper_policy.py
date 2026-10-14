"""Offline policy checks with varying widths and delayed contact response."""
import importlib.util
from pathlib import Path
import sys

import pytest


spec = importlib.util.spec_from_file_location('adaptive_gripper_policy',
    Path(__file__).parents[1] / 'scripts/adaptive_gripper_policy.py')
policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policy
spec.loader.exec_module(policy)


def test_distinct_measured_widths_change_opening_and_preserve_margin():
    plans = [policy.opening_from_measurement(w, .001, .1) for w in [.055, .063, .075, .088]]
    assert len({p.opening_m for p in plans}) == 4
    for width, plan in zip([.055, .063, .075, .088], plans):
        assert width+.006 <= plan.opening_m <= .100
        assert plan.left_joint_m-plan.right_joint_m == pytest.approx(plan.opening_m)


def test_invalid_or_unobservable_width_never_becomes_a_clamped_grasp():
    for width, sigma, age in [(.101, .001, .1), (.096, .002, .1),
                               (.075, .01, .1), (.075, .001, 1),
                               (float('nan'), .001, .1)]:
        with pytest.raises(ValueError):
            policy.opening_from_measurement(width, sigma, age)


@pytest.mark.parametrize('diameter', [.055, .063, .075, .088])
def test_delayed_contacts_converge_without_fixed_final_width(diameter):
    controller = policy.ContactForcePolicy()
    commanded = actual = policy.opening_from_measurement(diameter, .001, .1).opening_m
    stable = 0
    for _ in range(1000):
        left = 600 * max(0, diameter-actual)/2
        right = 800 * max(0, diameter-actual)/2
        decision = controller.step(actual, left, right, .02, .02)
        assert not decision.fault
        assert max(left, right) < controller.hard_force_limit_n
        commanded = decision.next_opening_m
        actual += .5*(commanded-actual)
        stable = stable+1 if decision.force_in_band else 0
        if stable >= 15:
            break
    assert stable >= 15
    assert controller.minimum_force_n <= left <= controller.maximum_force_n
    assert controller.minimum_force_n <= right <= controller.maximum_force_n
    assert actual < diameter


def test_one_sided_contact_does_not_qualify_holding():
    decision = policy.ContactForcePolicy().step(.075, 1.8, 0, .02, .02)
    assert not decision.force_in_band


def test_blocked_pid_jaws_retain_pressure_using_the_commanded_opening():
    controller = policy.ContactForcePolicy()
    diameter = .075
    commanded = policy.opening_from_measurement(diameter, .001, .1).opening_m
    left = right = 0.
    stable = 0
    for _ in range(600):
        measured = max(diameter, commanded)  # rigid shell prevents further motion
        left += .5*(600*(measured-commanded)/2-left)
        right += .5*(800*(measured-commanded)/2-right)
        decision = controller.step(commanded, left, right, .02, .02)
        assert not decision.fault
        commanded = decision.next_opening_m
        stable = stable+1 if decision.force_in_band else 0
        if stable >= 20:
            break
    assert stable >= 20
    assert commanded < measured
    assert controller.minimum_force_n <= min(left, right)


def test_stale_invalid_and_overforce_feedback_interrupt_closing():
    c = policy.ContactForcePolicy()
    for left, right, age in [(1, 1, .3), (float('nan'), 1, .01)]:
        d = c.step(.075, left, right, age, .02)
        assert d.fault and d.next_opening_m == .075
    d = c.step(.075, 6, 2, .01, .02)
    assert d.fault and d.next_opening_m > .075
    assert c.step(.075, 0, 0, .01, .02, cancelled=True).fault
