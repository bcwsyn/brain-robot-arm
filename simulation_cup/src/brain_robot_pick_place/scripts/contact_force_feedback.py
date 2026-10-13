"""Extract Gazebo target contact normal force in N, never motor torque.

Read-only helper. Gazebo bumper wrenches and normals are expressed in the same
configured frame. A wrench is projected once at each matching contact point;
total_wrench is deliberately not added again.
"""
import math


def target_normal_force(message, target_model):
    if not target_model or '::' in target_model:
        raise ValueError('target model must be an exact model name')
    prefix = target_model+'::'
    force_n, count = 0., 0
    for contact in message.states:
        if not (contact.collision1_name.startswith(prefix) or contact.collision2_name.startswith(prefix)):
            continue
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
