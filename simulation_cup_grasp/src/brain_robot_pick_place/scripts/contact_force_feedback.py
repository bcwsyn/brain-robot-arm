"""Extract Gazebo target contact normal force in N, never motor torque.

Read-only helper. Gazebo bumper wrenches and normals are expressed in the same
configured frame. A wrench is projected once at each matching contact point;
total_wrench is deliberately not added again.
"""
import math
import re


def _latest_contacts(message, target_model, require_step_time):
    if not target_model or '::' in target_model:
        raise ValueError('target model must be an exact model name')
    prefix = target_model+'::'
    contacts = [c for c in message.states if c.collision1_name.startswith(prefix)
                or c.collision2_name.startswith(prefix)]
    # Gazebo ContactSensor batches contacts from several physics steps before
    # a sensor update. ROS conversion preserves each step in ContactState.info.
    # Sum simultaneous contact points, never forces across different times.
    timestamps = []
    for contact in contacts:
        match = re.search(r'time:\s*\[(\d+)\.(\d+)\]', getattr(contact, 'info', ''))
        timestamps.append((int(match[1]), int(match[2])) if match else None)
    if contacts and (require_step_time or any(t is not None for t in timestamps)):
        if any(t is None for t in timestamps):
            raise ValueError('missing physics-step time in batched contact feedback')
        latest = max(timestamps)
        contacts = [c for c, t in zip(contacts, timestamps) if t == latest]
    return contacts


def target_normal_force(message, target_model, *, require_step_time=False):
    """Gross point-normal load, useful for diagnostics rather than jaw-axis control."""
    contacts = _latest_contacts(message, target_model, require_step_time)
    force_n, count = 0., 0
    for contact in contacts:
        if len(contact.wrenches) != len(contact.contact_normals):
            raise ValueError('contact normals and point wrenches do not match')
        for wrench, normal in zip(contact.wrenches, contact.contact_normals):
            vector = (wrench.force.x, wrench.force.y, wrench.force.z)
            n = (normal.x, normal.y, normal.z)
            if not all(math.isfinite(x) for x in vector+n):
                raise ValueError('nonfinite contact feedback')
            length = math.sqrt(sum(x*x for x in n))
            if length < 1e-8:
                raise ValueError('zero-length contact normal')
            force_n += abs(sum(f*x for f, x in zip(vector, n))/length)
            count += 1
    return force_n, count


def target_axis_force(message, target_model, axis_world, *, require_step_time=True):
    """Net target reaction projected on the measured jaw closing axis, in N.

    Opposing loads from edge/facet contacts cancel before projection, as they
    do in a whole-pad force sensor. Tangential loads remain separate.
    """
    axis = tuple(axis_world)
    if len(axis) != 3 or not all(math.isfinite(x) for x in axis):
        raise ValueError('invalid world jaw axis')
    length = math.sqrt(sum(x*x for x in axis))
    if length < 1e-8:
        raise ValueError('zero world jaw axis')
    vector, count = [0., 0., 0.], 0
    for contact in _latest_contacts(message, target_model, require_step_time):
        if len(contact.wrenches) != len(contact.contact_normals):
            raise ValueError('contact arrays do not match')
        sign = 1 if contact.collision1_name.startswith(target_model+'::') else -1
        for wrench in contact.wrenches:
            force = (wrench.force.x, wrench.force.y, wrench.force.z)
            if not all(math.isfinite(x) for x in force):
                raise ValueError('nonfinite contact wrench')
            vector = [v + sign*f for v, f in zip(vector, force)]
            count += 1
    return abs(sum(v*a for v, a in zip(vector, axis))/length), count
