"""Generate a hollow stepped cup; dimensions are simulation truth, not perception inputs."""
from dataclasses import dataclass
import math
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class CupSpec:
    body_diameter_m: float = .075
    body_height_m: float = .160
    mouth_diameter_m: float = .063
    mouth_height_m: float = .040
    wall_m: float = .002
    mass_kg: float = .080
    segments: int = 48

    def __post_init__(self):
        values = (self.body_diameter_m, self.body_height_m, self.mouth_diameter_m,
                  self.mouth_height_m, self.wall_m, self.mass_kg)
        if not all(math.isfinite(x) and x > 0 for x in values):
            raise ValueError('cup dimensions and mass must be finite and positive')
        if not (self.mouth_diameter_m <= self.body_diameter_m and
                2*self.wall_m < self.mouth_diameter_m and
                2*self.wall_m < self.body_height_m and
                self.wall_m < self.mouth_height_m):
            raise ValueError('invalid hollow stepped cup geometry')
        if not isinstance(self.segments, int) or not 24 <= self.segments <= 128:
            raise ValueError('segments must be an integer in [24, 128]')

    @property
    def height_m(self):
        return self.body_height_m+self.mouth_height_m

    def sections(self):
        """Non-overlapping annular solids: bottom, body, shoulder, mouth."""
        rb, rn, t = self.body_diameter_m/2, self.mouth_diameter_m/2, self.wall_m
        hb, h = self.body_height_m, self.height_m
        return [(0., rb, 0., t), (rb-t, rb, t, hb-t),
                (rn-t, rb, hb-t, hb), (rn-t, rn, hb, h)]

    def inertial(self):
        parts = self.sections()
        volumes = [math.pi*(ro*ro-ri*ri)*(z1-z0) for ri, ro, z0, z1 in parts]
        masses = [self.mass_kg*v/sum(volumes) for v in volumes]
        center = sum(m*(p[2]+p[3])/2 for m, p in zip(masses, parts))/self.mass_kg
        ixy = iz = 0.
        for m, (ri, ro, z0, z1) in zip(masses, parts):
            iz += m*(ri*ri+ro*ro)/2
            ixy += m*(3*(ri*ri+ro*ro)+(z1-z0)**2)/12 + m*((z0+z1)/2-center)**2
        return center, ixy, iz


def write_model(directory, spec=CupSpec(), *, name='stepped_cup'):
    """Write closed convex collision wedges and a hollow visual mesh in ASCII STL.

    The 48-sided shell approximates circular surfaces; it does not simulate
    plastic deformation. The model frame is at half the total height.
    """
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if not name.replace('_', '').isalnum():
        raise ValueError('model name must be alphanumeric with underscores')
    triangles = []
    collision_names = []
    for section, (ri, ro, z0, z1) in enumerate(spec.sections()):
        for segment in range(spec.segments):
            a, b = 2*math.pi*segment/spec.segments, 2*math.pi*(segment+1)/spec.segments
            # A centre wedge at the bottom has degenerate inner faces; skip
            # zero-area triangles when writing STL.
            vertices = [(r*math.cos(theta), r*math.sin(theta), z-spec.height_m/2)
                        for z in (z0, z1) for r, theta in ((ri, a), (ro, a), (ro, b), (ri, b))]
            faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                     (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
            mesh = [tuple(vertices[j] for j in tri)
                    for q in faces for tri in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))]
            filename = f'section_{section:02d}_{segment:03d}.stl'
            _write_stl(directory/filename, mesh)
            triangles.extend(mesh)
            collision_names.append(filename)
    _write_stl(directory/'cup_visual.stl', triangles)
    root = ET.Element('sdf', version='1.7')
    model = ET.SubElement(root, 'model', name=name)
    ET.SubElement(model, 'static').text = 'false'
    link = ET.SubElement(model, 'link', name='cup_link')
    ET.SubElement(link, 'gravity').text = 'true'
    inertial = ET.SubElement(link, 'inertial')
    center, ixy, iz = spec.inertial()
    ET.SubElement(inertial, 'pose').text = f'0 0 {center-spec.height_m/2:.12g} 0 0 0'
    ET.SubElement(inertial, 'mass').text = str(spec.mass_kg)
    tensor = ET.SubElement(inertial, 'inertia')
    for field, value in [('ixx', ixy), ('iyy', ixy), ('izz', iz), ('ixy', 0), ('ixz', 0), ('iyz', 0)]:
        ET.SubElement(tensor, field).text = str(value)
    for index, filename in enumerate(collision_names):
        collision = ET.SubElement(link, 'collision', name=f'cup_shell_{index}')
        _mesh(collision, directory/filename)
        surface = ET.SubElement(collision, 'surface')
        friction = ET.SubElement(ET.SubElement(surface, 'friction'), 'ode')
        ET.SubElement(friction, 'mu').text = '1.2'
        ET.SubElement(friction, 'mu2').text = '1.2'
        contact = ET.SubElement(ET.SubElement(surface, 'contact'), 'ode')
        for key, value in [('kp', 100000), ('kd', 10), ('max_vel', .05), ('min_depth', .0001)]:
            ET.SubElement(contact, key).text = str(value)
    visual = ET.SubElement(link, 'visual', name='cup_visual')
    _mesh(visual, directory/'cup_visual.stl')
    material = ET.SubElement(visual, 'material')
    ET.SubElement(material, 'ambient').text = '.75 .11 .08 1'
    ET.SubElement(material, 'diffuse').text = '.90 .18 .12 1'
    ET.SubElement(material, 'specular').text = '.12 .12 .12 1'
    ET.indent(root)
    path = directory/'model.sdf'
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    return path


def _mesh(parent, path):
    mesh = ET.SubElement(ET.SubElement(parent, 'geometry'), 'mesh')
    ET.SubElement(mesh, 'uri').text = path.as_uri()


def _write_stl(path, triangles):
    lines = ['solid cup']
    for a, b, c in triangles:
        u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
        normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        norm = math.sqrt(sum(x*x for x in normal))
        if norm < 1e-14:
            continue
        lines.append('facet normal '+' '.join(f'{x/norm:.10g}' for x in normal))
        lines.append('outer loop')
        lines.extend('vertex '+' '.join(f'{x:.10g}' for x in p) for p in (a, b, c))
        lines.extend(['endloop', 'endfacet'])
    lines.append('endsolid cup')
    path.write_text('\n'.join(lines)+'\n')
