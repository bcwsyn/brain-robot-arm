#!/usr/bin/env python3
"""Generate a portable MJCF from the CURRENT simulation URDF, not legacy MJCF."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import numpy as np

WS = Path(__file__).resolve().parents[1]


def vec(value):
    return np.array([float(v) for v in value.split()])


def rotation(rpy):
    r, p, y = vec(rpy)
    sr, cr, sp, cp, sy, cy = math.sin(r), math.cos(r), math.sin(p), math.cos(p), math.sin(y), math.cos(y)
    return np.array([[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr],
                     [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr], [-sp, cp*sr, cp*cr]])


def pose(source):
    origin = source.find('origin')
    return dict(pos=origin.get('xyz', '0 0 0'), euler=origin.get('rpy', '0 0 0')) if origin is not None else {}


def generate(urdf_bytes, destination):
    urdf = ET.fromstring(urdf_bytes)
    for name, expected in [('joint7', [0., .05]), ('joint8', [-.05, 0.])]:
        limit = urdf.find(f"joint[@name='{name}']/limit")
        if limit is None or not np.allclose([float(limit.get('lower')), float(limit.get('upper'))], expected, atol=1e-12):
            raise ValueError('This training release requires the confirmed 100 mm gripper variant')
    root = ET.Element('mujoco', model='piper_cup_rl_current_urdf')
    ET.SubElement(root, 'compiler', angle='radian', eulerseq='XYZ', balanceinertia='false')
    ET.SubElement(root, 'option', timestep='.002', integrator='implicitfast',
                  gravity='0 0 -9.81', iterations='80', cone='elliptic')
    ET.SubElement(root, 'size', nconmax='400', njmax='2500')
    defaults = ET.SubElement(root, 'default')
    ET.SubElement(defaults, 'geom', friction='1.2 .01 .001', solref='.008 1', solimp='.95 .99 .001')
    ET.SubElement(defaults, 'joint', damping='1', armature='.01')
    assets = ET.SubElement(root, 'asset')
    world = ET.SubElement(root, 'worldbody')
    ET.SubElement(world, 'light', pos='.3 -.4 1', dir='0 0 -1', diffuse='.8 .8 .8')
    ET.SubElement(world, 'geom', name='table', type='plane', size='1 1 .01', rgba='.65 .65 .65 1')
    ET.SubElement(world, 'site', name='goal', type='cylinder', size='.04 .0005', pos='.43 .12 .001', rgba='0 .8 .2 .4')
    children = {}
    for joint in urdf.findall('joint'):
        children.setdefault(joint.find('parent').get('link'), []).append(joint)
    links = {l.get('name'): l for l in urdf.findall('link')}
    meshes, fingerprints = {}, {}

    def mesh_name(filename):
        path = Path(filename.removeprefix('file://'))
        if not path.is_absolute():
            raise ValueError('Expected resolved absolute URDF mesh URI')
        if path not in meshes:
            name = 'mesh_'+str(len(meshes))
            ET.SubElement(assets, 'mesh', name=name, file=os.path.relpath(path, destination.parent))
            meshes[path] = name
            fingerprints[str(path.relative_to(WS))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return meshes[path]

    def add_link(parent, name, joint=None):
        attributes = dict(name=name)
        if joint is not None:
            attributes.update(pose(joint))
        body = ET.SubElement(parent, 'body', **attributes)
        link = links[name]
        inertia = link.find('inertial')
        if inertia is not None:
            mass = float(inertia.find('mass').get('value'))
            if mass > 0:
                i = inertia.find('inertia')
                tensor = np.array([
                    [float(i.get('ixx')), float(i.get('ixy')), float(i.get('ixz'))],
                    [float(i.get('ixy')), float(i.get('iyy')), float(i.get('iyz'))],
                    [float(i.get('ixz')), float(i.get('iyz')), float(i.get('izz'))]])
                transform = pose(inertia)
                r = rotation(transform.get('euler', '0 0 0'))
                tensor = r@tensor@r.T
                values = [tensor[0, 0], tensor[1, 1], tensor[2, 2], tensor[0, 1], tensor[0, 2], tensor[1, 2]]
                ET.SubElement(body, 'inertial', pos=transform.get('pos', '0 0 0'),
                              mass=str(mass), fullinertia=' '.join(map(str, values)))
                body.set('gravcomp', '1')
        if joint is not None and joint.get('type') != 'fixed':
            limit = joint.find('limit')
            ET.SubElement(body, 'joint', name=joint.get('name'), type='slide' if joint.get('type') == 'prismatic' else 'hinge',
                          axis=joint.find('axis').get('xyz'), range=limit.get('lower')+' '+limit.get('upper'),
                          damping='2' if joint.get('type') == 'prismatic' else '1')
        for kind in ('visual', 'collision'):
            for n, item in enumerate(link.findall(kind)):
                geometry = item.find('geometry')[0]
                props = dict(name=f'{name}_{kind}_{n}', **pose(item))
                if kind == 'visual':
                    props.update(contype='0', conaffinity='0', group='1')
                    color = item.find('material/color')
                    props['rgba'] = color.get('rgba') if color is not None else '.25 .25 .25 1'
                else:
                    props.update(group='3', rgba='.6 .6 .6 .15')
                if geometry.tag == 'mesh':
                    props.update(type='mesh', mesh=mesh_name(geometry.get('filename')))
                elif geometry.tag == 'box':
                    props.update(type='box', size=' '.join(str(v/2) for v in vec(geometry.get('size'))))
                elif geometry.tag == 'cylinder':
                    props.update(type='cylinder', size=f"{geometry.get('radius')} {float(geometry.get('length'))/2}")
                elif geometry.tag == 'sphere':
                    props.update(type='sphere', size=geometry.get('radius'))
                else:
                    raise ValueError('Unsupported URDF geometry '+geometry.tag)
                ET.SubElement(body, 'geom', **props)
        if name == 'gripper_base':
            ET.SubElement(body, 'site', name='tcp', pos='0 0 .130', size='.003', rgba='0 0 1 1')
        if name == 'wrist_camera_optical_frame':
            vfov = math.degrees(2*math.atan(.75*math.tan(math.radians(63)/2)))
            ET.SubElement(body, 'camera', name='wrist_rgb', pos='0 0 0', quat='0 1 0 0', fovy=str(vfov))
        for child in children.get(name, []):
            add_link(body, child.find('child').get('link'), child)
        return body

    for joint in children.get('world', []):
        add_link(world, joint.find('child').get('link'), joint)
    # Keep Gazebo's ideal robot gravity compensation and independent cup gravity.
    cup = ET.SubElement(world, 'body', name='cup', pos='.4 -.1 .1')
    ET.SubElement(cup, 'freejoint', name='cup_free')
    ET.SubElement(cup, 'inertial', pos='0 0 0', mass='.080', diaginertia='.00028333 .00028333 .00005625')
    # Hollow stepped shell: radial boxes preserve the cavity, plus a solid bottom.
    for section, radius, height, centre in [('body', .0375, .158, -.019), ('mouth', .0315, .040, .080)]:
        for n in range(32):
            theta = n*2*math.pi/32
            radial = radius-.001
            ET.SubElement(cup, 'geom', name=f'cup_{section}_{n}', type='box',
                pos=f'{radial*math.cos(theta)} {radial*math.sin(theta)} {centre}',
                euler=f'0 0 {theta}', size=f'.001 {radius*math.tan(math.pi/32)} {height/2}',
                rgba='.85 .14 .08 1')
    ET.SubElement(cup, 'geom', name='cup_bottom', type='cylinder', size='.0375 .001', pos='0 0 -.099', rgba='.85 .14 .08 1')
    # Approximate annular shoulder, kept hollow instead of filling the cup.
    for n in range(32):
        theta = n*2*math.pi/32
        ET.SubElement(cup, 'geom', name=f'cup_shoulder_{n}', type='box',
            pos=f'{.0335*math.cos(theta)} {.0335*math.sin(theta)} .059',
            euler=f'0 0 {theta}', size=f'.003 { .0365*math.tan(math.pi/32)} .001', rgba='.85 .14 .08 1')
    equality = ET.SubElement(root, 'equality')
    contact = ET.SubElement(root, 'contact')
    excluded = set()
    for joint in urdf.findall('joint'):
        a, b = joint.find('parent').get('link'), joint.find('child').get('link')
        if a != 'world':
            excluded.add(tuple(sorted((a, b))))
    srdf = ET.parse(WS/'src/piper_with_gripper_moveit/config/piper.srdf')
    for pair in srdf.findall('disable_collisions'):
        a, b = pair.get('link1'), pair.get('link2')
        if a in links and b in links and 'world' not in (a, b):
            excluded.add(tuple(sorted((a, b))))
    for a, b in sorted(excluded):
        ET.SubElement(contact, 'exclude', body1=a, body2=b)
    ET.SubElement(equality, 'joint', name='symmetric_jaws', joint1='joint8', joint2='joint7', polycoef='0 -1 0 0 0')
    actuators = ET.SubElement(root, 'actuator')
    for n, (kp, kv) in enumerate(zip([3000, 3000, 2000, 200, 200, 100, 300, 300], [80, 80, 60, 12, 10, 8, 2, 2]), 1):
        joint = urdf.find(f"joint[@name='joint{n}']")
        limit = joint.find('limit')
        effort = float(limit.get('effort'))
        ET.SubElement(actuators, 'position', name=f'joint{n}', joint=f'joint{n}', kp=str(kp), kv=str(kv),
                      ctrlrange=limit.get('lower')+' '+limit.get('upper'), forcerange=f'{-effort} {effort}')
    ET.indent(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(destination, encoding='utf-8', xml_declaration=True)
    (destination.parent/'source_robot.urdf').write_bytes(urdf_bytes)
    (destination.parent/'model_provenance.json').write_text(json.dumps(dict(
        source='current simulation Gazebo URDF expanded with physics_grasp=true',
        urdf_sha256=hashlib.sha256(urdf_bytes).hexdigest(), meshes=fingerprints,
        total_gripper_stroke_m=.1, ideal_robot_gravity_compensation=True,
        cup_mass_kg=.08, cup_mass_is_assumed=True, cup_wall_m=.002,
        contact_engine='MuJoCo; dynamics are NOT Gazebo-equivalent or factory-calibrated',
        legacy_mujoco_model_used=False), indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--urdf', type=Path, help='Optional expanded CURRENT URDF')
    parser.add_argument('--output', type=Path, default=WS/'rl/assets/piper_cup.xml')
    args = parser.parse_args()
    expanded = args.urdf.read_bytes() if args.urdf else subprocess.check_output([
        'xacro', str(WS/'src/brain_robot_pick_place/urdf/piper_with_wrist_camera_gazebo.xacro'), 'physics_grasp:=true'])
    generate(expanded, args.output)
    print('Generated current-model MJCF:', args.output)


if __name__ == '__main__':
    main()
