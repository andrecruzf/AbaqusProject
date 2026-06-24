# -*- coding: utf-8 -*-
"""
modules/parts.py
Creates all parts of the Nakazima model.

Coordinate convention (after assembly rotation):
  Z = forming direction — punch moves +Z
  Blank lies in the XY plane: z=0 (bottom face / ZMIN) to z=t (top / ZMAX)

All rigid body parts are sketched with Y as the local revolution axis.
Assembly.py rotates each tool instance +90° around the global X-axis so
that the revolution axis aligns with global Z.

  Local  →  Global (after +90° Rx)
   Y    →   +Z   (forming direction)
   Z    →   -Y
   X    →    X   (unchanged)
"""
from abaqus import mdb
import abaqusConstants as ac
from abaqusConstants import (THREE_D, ANALYTIC_RIGID_SURFACE, STANDALONE,
                             CLOCKWISE, SIDE1, REVERSE)
import math, os


# ─────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────

def _inp_path(cfg):
    """Full path to the geometry .inp file for the selected specimen width."""
    return os.path.join(cfg.INP_DIR, 'W%d.inp' % cfg.SPECIMEN_WIDTH)


def _cae_path(cfg):
    """Full path to the geometry .cae file for the selected specimen width."""
    return os.path.join(cfg.INP_DIR, 'W%d.cae' % cfg.SPECIMEN_WIDTH)


def _add_dome_zone_set(cfg, part):
    """
    Create DOME_ZONE: all elements (all through-thickness layers) whose
    centroid falls within R_DOME of the punch axis.  Used by
    *TERMINATE ANALYSIS to stop the simulation on first dome-zone failure.
    """
    import math as _math
    try:
        r_dome = cfg.R_DOME
        node_coords = {n.label: n.coordinates for n in part.nodes}
        labels = []
        for elem in part.elements:
            xs = [node_coords[nl][0] for nl in elem.connectivity if nl in node_coords]
            ys = [node_coords[nl][1] for nl in elem.connectivity if nl in node_coords]
            if not xs:
                continue
            r = _math.sqrt((sum(xs)/len(xs))**2 + (sum(ys)/len(ys))**2)
            if r <= r_dome:
                labels.append(elem.label)
        if not labels:
            print('  WARNING _add_dome_zone_set: no elements within R_DOME=%.1f mm.' % r_dome)
            return
        elems = part.elements.sequenceFromLabels(labels)
        part.Set(name='DOME_ZONE', elements=elems)
        print('  DOME_ZONE set : %d elements within R_DOME=%.1f mm' % (len(labels), r_dome))
    except Exception as e:
        print('  WARNING _add_dome_zone_set: %s' % e)


def _add_elout_set(cfg, part):
    """
    Create the ELOUT element set: the element on the top face (z ≈ BLANK_THICKNESS)
    whose centroid is closest to the punch apex (r = 0).
    """
    import math as _math
    try:
        t = cfg.BLANK_THICKNESS
        node_coords = {n.label: n.coordinates for n in part.nodes}
        best_label = None
        best_r2 = float('inf')
        for elem in part.elements:
            zs = [node_coords[nl][2] for nl in elem.connectivity if nl in node_coords]
            if not zs or (sum(zs) / len(zs)) < t * 0.5:
                continue
            xs = [node_coords[nl][0] for nl in elem.connectivity if nl in node_coords]
            ys = [node_coords[nl][1] for nl in elem.connectivity if nl in node_coords]
            r2 = (sum(xs) / len(xs)) ** 2 + (sum(ys) / len(ys)) ** 2
            if r2 < best_r2:
                best_r2 = r2
                best_label = elem.label
        if best_label is None:
            print('  WARNING _add_elout_set: no top-face element found — ELOUT skipped.')
            return
        elems = part.elements.sequenceFromLabels([best_label])
        part.Set(name='ELOUT', elements=elems)
        print('  ELOUT set  : element %d  (apex r=%.3f mm)' % (best_label, _math.sqrt(best_r2)))
    except Exception as e:
        print('  WARNING _add_elout_set: %s' % e)


# ─────────────────────────────────────────────────────────────
# Rigid tools
# ─────────────────────────────────────────────────────────────

def create_punch(cfg):
    """
    Hemispherical punch — analytic rigid surface.

    Profile (local Y = revolution axis, X = radial):
      • Tip at (r=0, y=0)  →  global z=0  (blank bottom face after rotation)
      • Quarter-sphere arc to (r=R, y=-R)
      • Cylindrical body below

    The punch moves in +Z (global) after the assembly rotation.
    """
    R   = cfg.PUNCH_RADIUS
    ctr = -R          # sphere centre y-coordinate in local sketch

    m = mdb.models[cfg.MODEL_NAME]
    s = m.ConstrainedSketch(name='__profile__', sheetSize=400.0)
    g = s.geometry
    s.setPrimaryObject(option=STANDALONE)
    s.ConstructionLine(point1=(0.0, -200.0), point2=(0.0, 200.0))
    s.FixedConstraint(entity=g[2])

    # Quarter-sphere: tip at (0, 0) → equator at (R, ctr)
    s.ArcByCenterEnds(
        center=(0.0, ctr),
        point1=(0.0, 0.0),
        point2=(R, ctr),
        direction=CLOCKWISE)

    # Cylindrical body
    s.Line(point1=(R, ctr),
           point2=(R, ctr - cfg.PUNCH_HEIGHT))
    s.Line(point1=(R, ctr - cfg.PUNCH_HEIGHT),
           point2=(0.0, ctr - cfg.PUNCH_HEIGHT))

    p = m.Part(name='Punch', dimensionality=THREE_D,
               type=ANALYTIC_RIGID_SURFACE)
    p = m.parts['Punch']
    p.AnalyticRigidSurfRevolve(sketch=s)
    s.unsetPrimaryObject()
    del m.sketches['__profile__']
    print('  Punch  : tip at local y=0  (→ global z=0 after rotation)  OK')


def create_pip_punch1(cfg):
    """
    PiP Punch1 — annular outer punch, analytic rigid surface.

    Profile is an open path derived from PUNCH1.inp (PinP_CR210H reference).
    Local Y = revolution axis (→ global Z after +90° rotation).
    Blank contact face is at y=0.  Punch body extends to y < 0.

    Path (r, y):
      (Ri, 0)   → inner bore edge at blank face
      (Ri, -H)  → inner bore wall (going away from blank)
      arc → (Ri+ef, -(H+ef))  inner top fillet, center (Ri+ef, -H)
      (Rfo, -(H+ef))  → flat inner flange
      arc → (Ro, -(fcz))  large outer fillet, center (Rfo, -fcz)
      (Ro, 0)   → outer wall back to blank face

    Reference: PUNCH1.inp START/LINE/CIRCL data (y-axis flipped to match
    our convention where punch body is at y < 0).
    """
    Ri   = cfg.PIP_PUNCH1_INNER_RADIUS     # 20.0
    ef   = cfg.PIP_PUNCH1_EDGE_FILLET      # 2.0
    Rfo  = cfg.PIP_PUNCH1_FLANGE_OUTER_R   # 28.75
    fr   = cfg.PIP_PUNCH1_FILLET_RADIUS    # 15.0
    fcz  = cfg.PIP_PUNCH1_FILLET_CENTER_Z  # 30.0 → -30.0 in our coords
    Ro   = cfg.PIP_PUNCH1_OUTER_RADIUS     # 43.75
    H    = cfg.PIP_PUNCH1_HEIGHT           # 43.0

    # Derived coordinates (match PUNCH1.inp flipped to y < 0)
    # Inner bore wall bottom: y = -H
    # Inner fillet center: (Ri+ef, -H); arc end: (Ri+ef, -(H+ef))
    # Flat flange: y = -(H+ef) = -45
    # Large fillet center: (Rfo, -fcz) = (28.75, -30); arc end: (Ro, -fcz) = (43.75, -30)
    y_bore_bottom  = -H              # -43
    y_flange       = -(H + ef)       # -45
    y_fillet_ctr   = -fcz            # -30

    m = mdb.models[cfg.MODEL_NAME]
    s = m.ConstrainedSketch(name='__profile__', sheetSize=400.0)
    g = s.geometry
    s.setPrimaryObject(option=STANDALONE)
    s.ConstructionLine(point1=(0.0, -200.0), point2=(0.0, 200.0))
    s.FixedConstraint(entity=g[2])

    # 1. Inner bore wall: (Ri, 0) → (Ri, -H)
    s.Line(point1=(Ri, -ef), point2=(Ri, y_bore_bottom))

    # 2. Inner top fillet (convex): (Ri, -H) → (Ri+ef, -(H+ef))
    #    Center: (Ri+ef, -H), radius=ef
    s.ArcByCenterEnds(
        center=(Ri + ef, -ef),
        point1=(Ri, -ef),
        point2=(Ri + ef,0),
        direction=CLOCKWISE)

    # 3. Flat inner flange: (Ri+ef, -(H+ef)) → (Rfo, -(H+ef))
    s.Line(point1=(Ri + ef, 0), point2=(Ro-fr, 0))

    # 4. Large outer fillet (convex): (Rfo, -(H+ef)) → (Ro, -fcz)
    #    Center: (Rfo, -fcz), radius=fr
    s.ArcByCenterEnds(
        center=(Ro-fr, -fr),
        point1=(Ro-fr, 0),
        point2=(Ro, -fr),
        direction=CLOCKWISE)

    # 5. Outer wall: (Ro, -fcz) → (Ro, 0)
    s.Line(point1=(Ro, -fr), point2=(Ro, y_bore_bottom))

    p = m.Part(name='Punch1', dimensionality=THREE_D,
               type=ANALYTIC_RIGID_SURFACE)
    p = m.parts['Punch1']
    p.AnalyticRigidSurfRevolve(sketch=s)
    s.unsetPrimaryObject()
    del m.sketches['__profile__']
    print('  Punch1 (PiP annular): Ri=%.1f Ro=%.1f H=%.1f  OK' % (Ri, Ro, H))


def create_pip_punch2(cfg):
    """
    PiP Punch2 — inner hemispherical punch, analytic rigid surface.

    Profile from PUNCH2.inp:
      START (r=0, y=15) → CIRCL (r=15, y=0), center (0, 0)
    This is a quarter-circle arc — the hemisphere tip at y=0 (blank face),
    body extending to y < 0 in our convention.

    Our sketch (Y = revolution axis, blank face at y=0, body at y < 0):
      (0, 0) → arc (R, -R), center (0, -R) → (R, -R-H) → (0, -R-H)
    """
    R = cfg.PIP_PUNCH2_RADIUS    # 15.0
    H = cfg.PIP_PUNCH2_HEIGHT    # 40.0
    ctr = -R

    m = mdb.models[cfg.MODEL_NAME]
    s = m.ConstrainedSketch(name='__profile__', sheetSize=400.0)
    g = s.geometry
    s.setPrimaryObject(option=STANDALONE)
    s.ConstructionLine(point1=(0.0, -200.0), point2=(0.0, 200.0))
    s.FixedConstraint(entity=g[2])

    # Quarter-sphere hemisphere
    s.ArcByCenterEnds(
        center=(0.0, ctr),
        point1=(0.0, 0.0),
        point2=(R, ctr),
        direction=CLOCKWISE)
    # Cylindrical body below hemisphere
    s.Line(point1=(R, ctr), point2=(R, ctr - H))
    s.Line(point1=(R, ctr - H), point2=(0.0, ctr - H))

    p = m.Part(name='Punch2', dimensionality=THREE_D,
               type=ANALYTIC_RIGID_SURFACE)
    p = m.parts['Punch2']
    p.AnalyticRigidSurfRevolve(sketch=s)
    s.unsetPrimaryObject()
    del m.sketches['__profile__']
    print('  Punch2 (PiP hemisphere): R=%.1f mm  OK' % R)


def create_pip_die(cfg):
    """
    PiP Die — flat contact ring with fillet, analytic rigid surface.

    Profile from DIE surface in PinP_CR210H reference:
      START (75, 0) → LINE (70, 0) → CIRCL (55, 15) center (70, 15) → LINE (55, 25)

    y=0 in reference = blank TOP face contact level.
    In our convention, die contact face at local y=t (blank thickness).
    Die body extends to y > t (above blank, global z > t after rotation).

    Our sketch:
      (Ro, t) → (Rfi, t) → arc (Rw, t+f) center (Rfi, t+f) → (Rw, t+H)
    where Ro=75, Rfi=70, Rw=55, f=15, H=25, t=BLANK_THICKNESS.
    """
    t   = cfg.BLANK_THICKNESS
    Ro  = cfg.DIE_OUTER_RADIUS           # 73 mm (standard outer radius)
    Rfi = cfg.PIP_DIE_FLAT_INNER_R       # 70.0 — inner edge of flat ring
    Rw  = cfg.PIP_DIE_INNER_WALL_R       # 55.0 — inner wall radius
    f   = cfg.PIP_DIE_FILLET             # 15.0
    H   = cfg.PIP_DIE_HEIGHT             # 25.0

    m = mdb.models[cfg.MODEL_NAME]
    s = m.ConstrainedSketch(name='__profile__', sheetSize=400.0)
    g = s.geometry
    s.setPrimaryObject(option=STANDALONE)
    s.ConstructionLine(point1=(0.0, -200.0), point2=(0.0, 200.0))
    s.FixedConstraint(entity=g[2])

    # Outer edge to flat ring inner edge: both at y=t
    s.Line(point1=(Ro, t), point2=(Rfi, t))
    # Fillet arc from flat ring inner edge → inner wall
    # Reference: CIRCL(55, 15) center(70, 15) — concave fillet
    # Our coords: CIRCL(Rw, t+f) center(Rfi, t+f)
    s.ArcByCenterEnds(
        center=(Rfi, t + f),
        point1=(Rfi, t),
        point2=(Rw, t + f),
        direction=CLOCKWISE)
    # Inner wall going up
    s.Line(point1=(Rw, t + f), point2=(Rw, t + H))

    p = m.Part(name='Die', dimensionality=THREE_D,
               type=ANALYTIC_RIGID_SURFACE)
    p = m.parts['Die']
    p.AnalyticRigidSurfRevolve(sketch=s)
    s.unsetPrimaryObject()
    del m.sketches['__profile__']
    print('  Die (PiP): Ro=%.1f, Rfi=%.1f, Rw=%.1f, f=%.1f  OK' % (Ro, Rfi, Rw, f))


def create_pip_matrix(cfg):
    """
    PiP Blank holder (Matrix) — analytic rigid surface.

    Profile from BLANKHOLDER surface in PinP_CR210H reference:
      START (62.5, 0) → LINE (62.5, 20) → LINE (64.5, 22) → LINE (75, 22)

    Reference y=0 is the BOTTOM of the BH body; the blank contact face is
    at y=22 (the chamfer top + outer flat ring).

    In our convention (local y=0 = blank BOTTOM face = global z=0 after rotation,
    BH body at y < 0):
      y_our = y_ref - (H + ch)  =  y_ref - 22

    Reference profile → Our profile:
      (62.5,  0) → (62.5, -22)   inner bore bottom
      (62.5, 20) → (62.5,  -2)   inner bore top
      (64.5, 22) → (64.5,   0)   chamfer end / contact face start
      (75,   22) → (75,     0)   outer contact face

    Traversal order (outer-to-inner): (75,0) → (64.5,0) → (62.5,-2) → (62.5,-22)
    """
    Ri  = cfg.PIP_BH_INNER_RADIUS    # 62.5
    H   = cfg.PIP_BH_HEIGHT          # 20.0
    ch  = cfg.PIP_BH_CHAMFER         # 2.0
    Ro  = 75.0                       # outer radius (from reference, matches BH flat ring)

    m = mdb.models[cfg.MODEL_NAME]
    s = m.ConstrainedSketch(name='__profile__', sheetSize=400.0)
    g = s.geometry
    s.setPrimaryObject(option=STANDALONE)
    s.ConstructionLine(point1=(0.0, -200.0), point2=(0.0, 200.0))
    s.FixedConstraint(entity=g[2])

    # Outer flat contact ring at y=0 (blank face)
    s.Line(point1=(Ro, 0.0), point2=(Ri + ch, 0.0))
    # Chamfer: 45° bevel going down-inward from contact face
    s.Line(point1=(Ri + ch, 0.0), point2=(Ri, -ch))
    # Inner bore wall going down
    s.Line(point1=(Ri, -ch), point2=(Ri, -(H + ch)))

    p = m.Part(name='Matrix', dimensionality=THREE_D,
               type=ANALYTIC_RIGID_SURFACE)
    p = m.parts['Matrix']
    p.AnalyticRigidSurfRevolve(sketch=s)
    s.unsetPrimaryObject()
    del m.sketches['__profile__']
    print('  Matrix (PiP BH): Ri=%.1f, Ro=%.1f, H=%.1f, chamfer=%.1f  OK'
          % (Ri, Ro, H, ch))


def create_flat_punch(cfg):
    """
    Flat Marciniak punch — analytic rigid surface (ISO 12004-2 §6.3.4).

    Profile (local Y = revolution axis, X = radial):
      • Flat face at y=0 from r=0 to r=R
      • PUNCH_EDGE_FILLET arc at the outer edge (convex, connects flat to cylinder)
      • Cylindrical body below

    The punch moves in +Z (global) after the assembly rotation.
    """
    R = cfg.PUNCH_RADIUS
    f = cfg.PUNCH_EDGE_FILLET
    h = cfg.PUNCH_HEIGHT

    m = mdb.models[cfg.MODEL_NAME]
    s = m.ConstrainedSketch(name='__profile__', sheetSize=400.0)
    g = s.geometry
    s.setPrimaryObject(option=STANDALONE)
    s.ConstructionLine(point1=(0.0, -200.0), point2=(0.0, 200.0))
    s.FixedConstraint(entity=g[2])

    # Flat face at y=0
    s.Line(point1=(0.0, 0.0), point2=(R, 0.0))
    # Cylindrical wall
    s.Line(point1=(R, 0.0), point2=(R, -h))
    # Edge fillet at outer corner (flat face meets cylindrical wall)
    s.FilletByRadius(
        radius=f,
        curve1=g[3], nearPoint1=(R - f, 0.0),
        curve2=g[4], nearPoint2=(R, -f))
    # Bottom close back to axis
    s.Line(point1=(R, -h), point2=(0.0, -h))

    p = m.Part(name='Punch', dimensionality=THREE_D,
               type=ANALYTIC_RIGID_SURFACE)
    p = m.parts['Punch']
    p.AnalyticRigidSurfRevolve(sketch=s)
    s.unsetPrimaryObject()
    del m.sketches['__profile__']
    print('  Punch (Marciniak flat): R=%.1f mm, edge fillet=%.1f mm  OK' % (R, f))


def create_die(cfg):
    """
    Die (draw ring) — analytic rigid surface.

    Profile (local Y = revolution axis, X = radial):
      • Flat contact ring at y=BLANK_THICKNESS  →  global z=t  (blank top / ZMAX)
        from r=DIE_INNER_RADIUS to r=DIE_OUTER_RADIUS
      • 8 mm fillet at inner edge (from flat to vertical wall)
      • Vertical wall rising above the blank

    After assembly rotation the die sits above the blank and contacts ZMAX.
    """
    t  = cfg.BLANK_THICKNESS
    Ri = cfg.DIE_INNER_RADIUS
    Ro = cfg.DIE_OUTER_RADIUS
    f  = cfg.DIE_FILLET
    h  = cfg.DIE_HEIGHT

    m = mdb.models[cfg.MODEL_NAME]
    s = m.ConstrainedSketch(name='__profile__', sheetSize=400.0)
    g = s.geometry
    s.setPrimaryObject(option=STANDALONE)
    s.ConstructionLine(point1=(0.0, -200.0), point2=(0.0, 200.0))
    s.FixedConstraint(entity=g[2])

    # Flat contact ring at y=t
    s.Line(point1=(Ri, t), point2=(Ro, t))
    # Vertical inner wall rising from y=t upward
    s.Line(point1=(Ri, t), point2=(Ri, t + h))
    # 8 mm fillet at the die throat (concave corner)
    s.FilletByRadius(
        radius=f,
        curve1=g[3], nearPoint1=(Ri + f, t),
        curve2=g[4], nearPoint2=(Ri, t + f))

    p = m.Part(name='Die', dimensionality=THREE_D,
               type=ANALYTIC_RIGID_SURFACE)
    p = m.parts['Die']
    p.AnalyticRigidSurfRevolve(sketch=s)
    s.unsetPrimaryObject()
    del m.sketches['__profile__']
    print('  Die    : contact face at local y=%.2f mm  (→ global z=t after rotation)  OK' % t)


def create_matrix(cfg):
    """
    Blank holder (Matrix) — analytic rigid surface.

    Profile (local Y = revolution axis, X = radial):
      • Flat contact ring at y=0  →  global z=0  (blank bottom / ZMIN)
        from r=BH_INNER_RADIUS to r=DIE_OUTER_RADIUS
      • BH_FILLET radius fillet at the inner contact edge (prevents the
        blank rim from catching on a sharp corner during forming)
      • Vertical inner wall extending below the blank

    After assembly rotation the blank holder sits below the blank and contacts ZMIN.
    """
    Ri = cfg.BH_INNER_RADIUS
    Ro = cfg.DIE_OUTER_RADIUS
    h  = cfg.BH_HEIGHT
    f  = cfg.BH_FILLET

    m = mdb.models[cfg.MODEL_NAME]
    s = m.ConstrainedSketch(name='__profile__', sheetSize=400.0)
    g = s.geometry
    s.setPrimaryObject(option=STANDALONE)
    s.ConstructionLine(point1=(0.0, -200.0), point2=(0.0, 200.0))
    s.FixedConstraint(entity=g[2])

    # Flat contact ring at y=0
    s.Line(point1=(Ri, 0.0), point2=(Ro, 0.0))
    # Inner wall going below (y<0)
    s.Line(point1=(Ri, 0.0), point2=(Ri, -h))
    # Fillet at the inner contact edge (flat ring meets inner wall)
    s.FilletByRadius(
        radius=f,
        curve1=g[3], nearPoint1=(Ri + f, 0.0),
        curve2=g[4], nearPoint2=(Ri, -f))

    p = m.Part(name='Matrix', dimensionality=THREE_D,
               type=ANALYTIC_RIGID_SURFACE)
    p = m.parts['Matrix']
    p.AnalyticRigidSurfRevolve(sketch=s)
    s.unsetPrimaryObject()
    del m.sketches['__profile__']
    print('  Matrix : contact face at local y=0, inner fillet r=%.1f mm  OK' % f)


# ─────────────────────────────────────────────────────────────
# Specimen — import from .cae or .inp or build via macro
# ─────────────────────────────────────────────────────────────

def _upgrade_cae(abs_path):
    """
    Upgrade a .cae file to the current Abaqus version using upgradeMdb()
    via a noGUI subprocess.

    upgradeMdb(source, dest) requires both paths to end in .cae — otherwise
    Abaqus appends .cae automatically, producing an unexpected filename.
    Strategy: write upgraded version to a _v2023.cae temp path, then replace
    the original once we confirm the output exists.
    """
    import subprocess, tempfile
    tmp_path = abs_path.replace('.cae', '_v2023.cae')
    script = (
        "from abaqus import upgradeMdb\n"
        "upgradeMdb(r'%s', r'%s')\n" % (abs_path, tmp_path)
    )
    tmp_script = tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False)
    tmp_script.write(script)
    tmp_script.close()
    # Find abaqus executable: env var override → known install paths → PATH fallback.
    _candidates = [
        os.environ.get('ABAQUS_CMD', ''),
        '/cluster/software/commercial/abaqus/2023/x86_64/Commands/abaqus',
        '/usr/local/bin/abaqus',
        'abaqus',
    ]
    abaqus_cmd = next((c for c in _candidates if c and (os.path.isfile(c) or c == 'abaqus')), 'abaqus')
    try:
        subprocess.call([abaqus_cmd, 'cae', 'noGUI=' + tmp_script.name])
    finally:
        os.remove(tmp_script.name)

    if not os.path.exists(tmp_path):
        raise RuntimeError('upgradeMdb did not produce output: %s' % tmp_path)

    os.remove(abs_path)
    os.rename(tmp_path, abs_path)
    print('  Upgrade complete: %s' % os.path.basename(abs_path))


def _ac_const(name):
    return getattr(ac, name, None)


def _seed_float(value):
    try:
        value = float(value)
    except Exception:
        return None
    if value > 1.0e-12:
        return value
    return None


def _seed_int(value):
    try:
        value = int(round(float(value)))
    except Exception:
        return None
    if value > 0:
        return value
    return None


def _edge_point(edge):
    try:
        if edge.pointOn:
            return edge.pointOn[0]
    except Exception:
        pass
    return None


def _edge_length(edge):
    try:
        return edge.getSize(printResults=False)
    except Exception:
        try:
            return edge.getSize()
        except Exception:
            return None


def _edge_seed(part, edge, attr_name):
    attr = _ac_const(attr_name)
    if attr is None:
        return None
    try:
        return part.getEdgeSeeds(edge=edge, attribute=attr)
    except Exception:
        try:
            return part.getEdgeSeeds(edge, attr)
        except Exception:
            return None


def _part_seed(part, attr_name):
    attr = _ac_const(attr_name)
    if attr is None:
        return None
    try:
        return part.getPartSeeds(attribute=attr)
    except Exception:
        return None


def _is_thickness_edge(cfg, edge):
    p = _edge_point(edge)
    if p is None:
        return False
    t = float(cfg.BLANK_THICKNESS)
    return abs(p[2] - t * 0.5) < t * 0.4


def _edge_radius(edge):
    p = _edge_point(edge)
    if p is None:
        return None
    return math.sqrt(p[0]**2 + p[1]**2)


def _part_outer_radius(part):
    vals = []
    try:
        vals.extend(math.sqrt(n.coordinates[0]**2 + n.coordinates[1]**2)
                    for n in part.nodes)
    except Exception:
        pass
    if not vals:
        try:
            vals.extend(math.sqrt(v.pointOn[0][0]**2 + v.pointOn[0][1]**2)
                        for v in part.vertices)
        except Exception:
            pass
    if not vals:
        try:
            vals.extend(_edge_radius(e) for e in part.edges
                        if _edge_radius(e) is not None)
        except Exception:
            pass
    return max(vals) if vals else 1.0


def _imported_seed_scale_at_radius(cfg, radius, outer_radius, target_scale):
    mode = getattr(cfg, 'MESH_IMPORTED_SCALE_MODE', 'radial_growth').lower()
    if mode == 'uniform':
        return target_scale
    if mode in ('banded', 'banded_growth', 'two_band'):
        band_r = max(0.0, float(getattr(cfg, 'MESH_IMPORTED_BAND_RADIUS', 50.0)))
        if radius is None:
            return target_scale
        return 1.0 if radius <= band_r else target_scale
    if mode not in ('radial', 'radial_growth', 'growth'):
        raise ValueError("Invalid MESH_IMPORTED_SCALE_MODE: '%s'" % mode)

    fixed_r = max(0.0, float(getattr(cfg, 'MESH_IMPORTED_FIXED_RADIUS', 20.0)))
    power = max(0.1, float(getattr(cfg, 'MESH_IMPORTED_GROWTH_POWER', 1.0)))
    if radius is None or outer_radius <= fixed_r + 1.0e-9:
        return target_scale
    if radius <= fixed_r:
        return 1.0
    xi = (radius - fixed_r) / (outer_radius - fixed_r)
    xi = max(0.0, min(1.0, xi))
    return 1.0 + (target_scale - 1.0) * (xi ** power)


def _seed_value_text(value):
    if value is None:
        return ''
    try:
        return '%.10g' % float(value)
    except Exception:
        return str(value)


def _dump_mesh_seeds(cfg, part, tag):
    if not getattr(cfg, 'MESH_DUMP_IMPORTED_SEEDS', False):
        return
    try:
        if not os.path.isdir(cfg.OUTPUT_DIR):
            os.makedirs(cfg.OUTPUT_DIR)
        path = os.path.join(cfg.OUTPUT_DIR, cfg.JOB_NAME + '_' + tag + '.csv')
        attrs = (
            'EDGE_SEEDING_METHOD', 'SIZE', 'NUMBER', 'BIAS_METHOD',
            'BIAS_RATIO', 'BIAS_MIN_SIZE', 'BIAS_MAX_SIZE',
            'DEVIATION_FACTOR', 'MIN_SIZE_FACTOR', 'CONSTRAINT',
        )
        with open(path, 'w') as fh:
            fh.write('edge_index,x,y,z,r,length,is_thickness,%s\n' %
                     ','.join(attrs))
            for edge in part.edges:
                p = _edge_point(edge)
                if p is None:
                    x = y = z = r = ''
                else:
                    x, y, z = p
                    r = math.sqrt(x**2 + y**2)
                length = _edge_length(edge)
                vals = [_seed_value_text(_edge_seed(part, edge, a)) for a in attrs]
                fh.write('%s,%s,%s,%s,%s,%s,%s,%s\n' % (
                    edge.index,
                    _seed_value_text(x), _seed_value_text(y),
                    _seed_value_text(z), _seed_value_text(r),
                    _seed_value_text(length),
                    1 if _is_thickness_edge(cfg, edge) else 0,
                    ','.join(vals)))
        print('  Mesh seed dump: %s' % path)
    except Exception as exc:
        print('  WARNING _dump_mesh_seeds: %s' % exc)


def _apply_outer_reseed(cfg, part):
    """
    Keep imported seeds inside MESH_IMPORTED_FIXED_RADIUS (center stays
    exactly as in the .cae, typically 0.1 mm).  Outside that radius,
    delete all imported seeds and apply seedEdgeBySize(h(r)) uniformly to
    every in-plane edge — both radial and circumferential edges get the same
    target size at their radius, so the mesher produces near-square elements.

    Growth law:
      h(r) = h_center                                for r <= r_fixed
      h(r) = h_center + (h_outer-h_center) * xi^p   for r >  r_fixed
      where xi = (r - r_fixed) / (R_outer - r_fixed)
    """
    r_fixed     = float(getattr(cfg, 'MESH_IMPORTED_FIXED_RADIUS', 20.0))
    h_center    = float(getattr(cfg, 'MESH_CENTER_SIZE', 0.1))
    h_outer     = h_center * float(getattr(cfg, 'MESH_REFINEMENT_FACTOR', 3.0))
    power       = max(0.1, float(getattr(cfg, 'MESH_IMPORTED_GROWTH_POWER', 1.0)))
    n_t         = int(getattr(cfg, 'N_THICKNESS_SEEDS', 10))
    thickness_seed = float(cfg.BLANK_THICKNESS) / float(n_t)
    outer_radius = _part_outer_radius(part)

    _dump_mesh_seeds(cfg, part, 'outer_reseed_before')

    thick_seeded = 0
    center_kept  = 0
    outer_reseeded = 0

    for edge in part.edges:
        if _is_thickness_edge(cfg, edge):
            try:
                part.seedEdgeBySize([edge], thickness_seed, deviationFactor=0.1)
                thick_seeded += 1
            except Exception:
                pass
            continue

        radius = _edge_radius(edge)
        if radius is None or radius <= r_fixed:
            center_kept += 1
            continue

        if outer_radius > r_fixed + 1.0e-9:
            xi = (radius - r_fixed) / (outer_radius - r_fixed)
            xi = max(0.0, min(1.0, xi))
        else:
            xi = 1.0
        h = h_center + (h_outer - h_center) * (xi ** power)
        try:
            part.seedEdgeBySize([edge], h, deviationFactor=0.1)
            outer_reseeded += 1
        except Exception:
            pass

    print('  Outer reseed: center kept=%d (r<=%.1f mm, h=%.3f mm), '
          'outer reseeded=%d (h_rim=%.3f mm), thickness=%d, power=%.2f'
          % (center_kept, r_fixed, h_center, outer_reseeded, h_outer,
             thick_seeded, power))
    _dump_mesh_seeds(cfg, part, 'outer_reseed_after')


def _apply_seed_bands(cfg, part):
    """
    Explicit per-band seed control via MESH_SEED_BANDS.

    MESH_SEED_BANDS is a list of (r_max_mm, size_mm) pairs in ascending r
    order.  For each in-plane edge the band whose r_max first exceeds the
    edge midpoint radius is selected:
      - size is None  → keep the imported .cae seed untouched
      - size is a number → seedEdgeBySize(size) on that edge (both radial
        and circumferential get the same target → square elements)
    Thickness edges always get N_THICKNESS_SEEDS regardless.

    Example config:
      MESH_SEED_BANDS = [
          (20,  None),   # punch apex — keep .cae fine seeds
          (35,  0.3),    # transition zone
          (50,  0.5),    # dome shoulder
          (1e9, 0.8),    # flange / clamped
      ]
    """
    bands = list(cfg.MESH_SEED_BANDS)   # [(r_max, size), ...]
    bands.sort(key=lambda b: b[0])

    n_t = int(getattr(cfg, 'N_THICKNESS_SEEDS', 10))
    thickness_seed = float(cfg.BLANK_THICKNESS) / float(n_t)
    outer_radius = _part_outer_radius(part)

    _dump_mesh_seeds(cfg, part, 'bands_before')

    counts = {}  # size_label -> count
    thick_seeded = 0

    for edge in part.edges:
        if _is_thickness_edge(cfg, edge):
            try:
                part.seedEdgeBySize([edge], thickness_seed, deviationFactor=0.1)
                thick_seeded += 1
            except Exception:
                pass
            continue

        radius = _edge_radius(edge)
        r = radius if radius is not None else outer_radius

        target = None
        for r_max, size in bands:
            if r <= r_max + 1.0e-6:
                target = size
                break
        else:
            # beyond last band — use last band's size
            target = bands[-1][1] if bands else None

        if target is None:
            counts['kept'] = counts.get('kept', 0) + 1
            continue

        try:
            part.seedEdgeBySize([edge], float(target), deviationFactor=0.1)
            key = '%.3g' % target
            counts[key] = counts.get(key, 0) + 1
        except Exception:
            pass

    band_summary = ', '.join('r<=%.0f:h=%s(%d)'
                              % (r_max,
                                 ('kept' if size is None else '%.3g' % size),
                                 counts.get('kept' if size is None
                                            else '%.3g' % size, 0))
                              for r_max, size in bands)
    print('  Seed bands: %s  thickness=%d' % (band_summary, thick_seeded))
    _dump_mesh_seeds(cfg, part, 'bands_after')


# ─────────────────────────────────────────────────────────────
# Mesh zone partitioning and seeding (original stable approach)
# ─────────────────────────────────────────────────────────────

def _apply_mesh_zones(cfg, part):
    """
    Add radial ring partitions and apply per-zone seeding from MESH_ZONES.

    MESH_IMPORTED_FIXED_RADIUS defines a protected center region:
      r <= r_keep : imported .cae seeds and partitions are left completely
                    untouched — the engin-seeded square center mesh is preserved.
      r >  r_keep : new ring partitions are added at each MESH_ZONES boundary
                    that falls in this range, then edges are reseeded per zone.

    This avoids re-partitioning over existing geometry (which corrupts the mesh)
    while still letting the zone table control the outer circular rings.

    Caller must call part.generateMesh() afterwards.
    Falls back gracefully if any individual partition step fails.
    """
    m      = mdb.models[cfg.MODEL_NAME]
    zones  = cfg.MESH_ZONES
    factor = getattr(cfg, 'MESH_REFINEMENT_FACTOR', 1.0)
    t      = float(cfg.BLANK_THICKNESS)
    eps_t  = max(0.01, t * 0.01)
    r_keep = float(getattr(cfg, 'MESH_IMPORTED_FIXED_RADIUS', 0.0))

    if factor <= 0.0:
        print('  WARNING _apply_mesh_zones: factor=%.4f <= 0, skipped.' % factor)
        return

    node_list = list(part.nodes)
    if node_list:
        r_max = max(math.sqrt(n.coordinates[0]**2 + n.coordinates[1]**2)
                    for n in node_list)
    else:
        r_max = max(math.sqrt(v.pointOn[0][0]**2 + v.pointOn[0][1]**2)
                    for v in part.vertices)

    # Build a smooth radial seed law anchored at the protected imported core.
    # The first imported ring remains untouched; the transition to the first
    # outer zone is ramped instead of stepped so the mesh does not collapse
    # into a single abrupt layer at r_keep.
    seed_anchors = []
    center_size = float(getattr(cfg, 'MESH_CENTER_SIZE', 0.1))
    if r_keep > 0.0:
        seed_anchors.append((r_keep, center_size))
    for r_zone, size_r, _size_c in zones:
        if seed_anchors and abs(r_zone - seed_anchors[-1][0]) < 1.0e-9:
            seed_anchors[-1] = (r_zone, float(size_r) * factor)
        else:
            seed_anchors.append((r_zone, float(size_r) * factor))
    seed_anchors.sort(key=lambda item: item[0])
    if not seed_anchors:
        seed_anchors = [(0.0, center_size), (r_max, zones[-1][1] * factor)]

    def _smoothstep(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3.0 - 2.0 * x)

    def _interp_size(radius):
        if radius <= seed_anchors[0][0]:
            return seed_anchors[0][1]
        for idx in range(1, len(seed_anchors)):
            r0, s0 = seed_anchors[idx - 1]
            r1, s1 = seed_anchors[idx]
            if radius <= r1 + 1.0e-9:
                if r1 <= r0 + 1.0e-9:
                    return s1
                xi = _smoothstep((radius - r0) / (r1 - r0))
                if s0 > 0.0 and s1 > 0.0:
                    return math.exp(math.log(s0) + xi * (math.log(s1) - math.log(s0)))
                return s0 + (s1 - s0) * xi
        return seed_anchors[-1][1]

    # Only add partitions outside the protected center and inside the specimen.
    zone_radii = []
    if r_keep > 0.5 and r_keep < r_max - 0.5:
        zone_radii.append(r_keep)
    zone_radii.extend([z[0] for z in zones[:-1]
                       if z[0] > r_keep + 0.5 and z[0] < r_max - 0.5])

    # ── Radial face + cell partitions (outer zone only) ───────────────────────
    if zone_radii:
        z_datum_id = part.DatumAxisByTwoPoint(
            point1=(0.0, 0.0, 0.0),
            point2=(0.0, 0.0, 1.0)
        ).id
    else:
        print('  No outer zone radii to partition (r_keep=%.1f mm).' % r_keep)

    for r in zone_radii:
        qx = r * 0.99 if r > 0.1 else 0.05
        sk_name = '__zone_r%g__' % r
        try:
            face_seq = part.faces.findAt(((qx, 0.01, t),))
            if not face_seq:
                print('  WARNING zones: no face found at r=%.2f mm.' % r)
                continue
            face = face_seq[0]

            transform = part.MakeSketchTransform(
                sketchPlane=face,
                sketchPlaneSide=SIDE1,
                origin=(0.0, 0.0, t)
            )
            sk = m.ConstrainedSketch(name=sk_name, sheetSize=400.0, transform=transform)
            sk.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(r, 0.0))

            indices_before = {e.index for e in part.edges}
            part.PartitionFaceBySketch(faces=face_seq, sketch=sk)
            del m.sketches[sk_name]
            sk_name = None

            arc_edge = None
            for e in part.edges:
                if e.index in indices_before or not e.pointOn:
                    continue
                x, y, z_e = e.pointOn[0]
                if abs(math.sqrt(x**2 + y**2) - r) < 0.5 and abs(z_e - t) < eps_t:
                    arc_edge = e
                    break

            if arc_edge is None:
                print('  WARNING zones: arc edge at r=%.2f mm not found.' % r)
                continue

            part.PartitionCellByExtrudeEdge(
                cells=part.cells,
                edges=[arc_edge],
                line=part.datums[z_datum_id],
                sense=REVERSE
            )
            print('  Zone partition r=%.1f mm: OK' % r)

        except Exception as exc:
            print('  WARNING zones: partition at r=%.2f mm failed: %s' % (r, exc))
            if sk_name and sk_name in m.sketches.keys():
                del m.sketches[sk_name]

    # ── Seed edges ───────────────────────────────────────────────────────────
    # Delete seeds only on outer edges — inner seeds are preserved as imported.
    outer_edges = [e for e in part.edges
                   if not _is_thickness_edge(cfg, e)
                   and (_edge_radius(e) or 0.0) > r_keep]
    if outer_edges:
        try:
            part.deleteSeeds(outer_edges)
        except Exception:
            pass

    outer_max_size = getattr(cfg, 'MESH_OUTER_MAX_SIZE', None)
    global_size = zones[-1][1] * factor
    if outer_max_size is not None:
        global_size = min(global_size, float(outer_max_size))
    part.seedPart(size=global_size, deviationFactor=0.1, minSizeFactor=0.1)

    n_t = int(getattr(cfg, 'N_THICKNESS_SEEDS', 10))
    thickness_seed = t / float(n_t)

    zone_seeded = 0
    thick_seeded = 0
    center_kept = 0
    for edge in part.edges:
        if not edge.pointOn:
            continue
        x, y, z_ep = edge.pointOn[0]
        if abs(z_ep - t * 0.5) < t * 0.4:
            try:
                part.seedEdgeBySize([edge], thickness_seed, deviationFactor=0.1)
                thick_seeded += 1
            except Exception:
                pass
            continue
        r_e = math.sqrt(x**2 + y**2)
        if r_e <= r_keep:
            center_kept += 1
            continue
        size = _interp_size(r_e)
        if outer_max_size is not None:
            size = min(size, float(outer_max_size))
        if size < global_size - 1e-9:
            try:
                part.seedEdgeBySize([edge], size, deviationFactor=0.1)
                zone_seeded += 1
            except Exception:
                pass

    print('  Mesh zones: center kept=%d (r<=%.1f mm), zone seeded=%d, '
          'thickness=%d, global=%.3f mm, factor=%.3f, smooth anchors=%d'
          % (center_kept, r_keep, zone_seeded, thick_seeded, global_size,
             factor, len(seed_anchors)))


def _apply_topological_mesh_tuning(cfg, part):
    """
    Topological mesh tuning for Butterfly/C-Grid partitioned blanks.

    The supervisor's CAE has face-only partitions (not cell partitions), so the
    blank is a single 3D cell.  Classification is therefore done on the TOP
    SURFACE FACES (z≈t) by adjacency:

      core face  — the central square top face (probe at eps, eps, t)
      trans faces— top faces sharing an edge with the core face
      outer faces— all remaining top faces

    Each in-plane edge is seeded according to which face region it belongs to
    (an edge shared by two face regions takes the finer classification).
    Both the top (z≈t) and bottom (z≈0) partners are seeded identically.

    Config knobs (all env-overridable):
      MESH_CORE_SCALE         — multiplier on the CAE core seed size (default 1.0)
      MESH_OUTER_GROWTH_RATIO — outer_size = new_core_size × ratio   (default 4.0)
      MESH_RADIAL_BIAS_RATIO  — >1.0 enables biased spoke seeding    (default 1.0)
      MESH_CORE_PROBE_OFFSET  — XY offset for top-face probe         (default 0.5 mm)

    Falls back to 'imported' mode if the core face cannot be located.
    """
    t     = float(cfg.BLANK_THICKNESS)
    eps   = float(getattr(cfg, 'MESH_CORE_PROBE_OFFSET', 0.5))
    eps_t = max(0.01, t * 0.05)

    core_scale = float(getattr(cfg, 'MESH_CORE_SCALE', 1.0))
    mr         = float(getattr(cfg, 'MESH_REFINEMENT_FACTOR', 1.0))
    growth     = float(getattr(cfg, 'MESH_OUTER_GROWTH_RATIO', 4.0))
    bias_on    = float(getattr(cfg, 'MESH_RADIAL_BIAS_RATIO', 1.0)) > 1.0 + 1e-6
    n_t        = int(getattr(cfg, 'N_THICKNESS_SEEDS', 10))
    override_t = bool(getattr(cfg, 'MESH_OVERRIDE_THICKNESS_SEEDS', True))
    thick_seed = t / float(n_t)

    # ── 1. Locate the core top face ───────────────────────────────────────────
    core_found = part.faces.findAt(((eps, eps, t),))
    if not core_found:
        print('  WARNING topo: core top face not found at probe (%.2f,%.2f,%.2f) '
              '— falling back to imported' % (eps, eps, t))
        _apply_imported_seed_tuning(cfg, part, 'imported')
        return None
    core_face     = core_found[0]
    core_face_idx = core_face.index
    core_edge_set = set(core_face.getEdges())

    # ── 2. Find transition top faces (adjacent to core on top surface) ────────
    trans_face_indices = set()
    for eidx in core_edge_set:
        e = part.edges[eidx]
        if _is_thickness_edge(cfg, e):
            continue
        for fidx in e.getFaces():
            if fidx == core_face_idx:
                continue
            p = part.faces[fidx].pointOn[0]
            if abs(p[2] - t) < eps_t:
                trans_face_indices.add(fidx)

    trans_edge_set = set()
    for fidx in trans_face_indices:
        trans_edge_set.update(part.faces[fidx].getEdges())
    trans_edge_set -= core_edge_set

    # ── 3. All remaining top-surface in-plane edges = outer ───────────────────
    all_top_edge_set = set()
    for face in part.faces:
        p = face.pointOn[0]
        if abs(p[2] - t) < eps_t:
            all_top_edge_set.update(face.getEdges())
    outer_edge_set = all_top_edge_set - core_edge_set - trans_edge_set

    # ── 4. Also seed the mirrored bottom (z≈0) edges with the same logic ──────
    # Build a map: for every top in-plane edge, find its bottom partner by
    # matching XY midpoint coordinates.
    def _bottom_partner(top_edge):
        p = _edge_point(top_edge)
        if p is None or abs(p[2] - t) > eps_t:
            return None
        tx, ty = p[0], p[1]
        best, best_d = None, 1.0
        for e in part.edges:
            q = _edge_point(e)
            if q is None or abs(q[2]) > eps_t:
                continue
            d = math.sqrt((q[0]-tx)**2 + (q[1]-ty)**2)
            if d < best_d:
                best, best_d = e, d
        return best if best_d < 0.5 else None

    print('  Topo: core face %d | %d trans faces | %d outer top edges'
          % (core_face_idx, len(trans_face_indices), len(outer_edge_set)))

    # ── 5. Read base core seed size from CAE ─────────────────────────────────
    core_inplane = [part.edges[i] for i in core_edge_set
                    if not _is_thickness_edge(cfg, part.edges[i])]
    base_sizes = []
    for e in core_inplane:
        sz = _seed_float(_edge_seed(part, e, 'SIZE'))
        if sz:
            base_sizes.append(sz)
        else:
            num = _seed_int(_edge_seed(part, e, 'NUMBER'))
            length = _edge_length(e)
            if num and length:
                base_sizes.append(length / float(num))

    if base_sizes:
        base_core = min(base_sizes)
    else:
        base_core = float(getattr(cfg, 'MESH_CENTER_SIZE', 0.1))
        print('  WARNING topo: no core seeds found in CAE — '
              'using MESH_CENTER_SIZE=%.3f' % base_core)

    new_core = base_core * core_scale / mr
    outer_sz = new_core * growth
    circ_sz  = math.sqrt(new_core * outer_sz)

    def _seed_pair(top_e, size=None, num=None):
        """Seed a top edge (and its bottom partner) by size or number."""
        targets = [top_e]
        bp = _bottom_partner(top_e)
        if bp is not None:
            targets.append(bp)
        for e in targets:
            try:
                if num is not None:
                    part.seedEdgeByNumber([e], num)
                else:
                    part.seedEdgeBySize([e], size, deviationFactor=0.1)
            except Exception:
                pass

    # ── 6. Seed core edges — synchronized uniform grid ────────────────────────
    seeded_core = 0
    for e in core_inplane:
        length = _edge_length(e)
        if not length:
            continue
        _seed_pair(e, num=max(1, int(round(length / new_core))))
        seeded_core += 1

    # ── 7. Seed transition faces (spokes) — group by face for synchronization ─
    seeded_rad  = 0
    seeded_circ = 0

    for fidx in trans_face_indices:
        face_edges = [part.edges[i] for i in part.faces[fidx].getEdges()
                      if i in trans_edge_set
                      and not _is_thickness_edge(cfg, part.edges[i])]

        radial_e = []   # [(edge, inner_end_first)]
        circ_e   = []

        for e in face_edges:
            try:
                verts = e.getVertices()
                p0 = part.vertices[verts[0]].pointOn[0]
                p1 = part.vertices[verts[1]].pointOn[0]
                r0 = math.sqrt(p0[0]**2 + p0[1]**2)
                r1 = math.sqrt(p1[0]**2 + p1[1]**2)
                if abs(r0 - r1) > max(r0, r1, 1.0) * 0.15:
                    radial_e.append((e, r0 < r1))
                else:
                    circ_e.append(e)
            except Exception:
                circ_e.append(e)

        # Radial (spoke) edges — same count enforced across all in this face
        if radial_e:
            avg_len = (sum(_edge_length(e) or 0.0 for e, _ in radial_e)
                       / len(radial_e))
            num_rad = max(1, int(round(avg_len / ((new_core + outer_sz) * 0.5))))
            for e, inner_first in radial_e:
                try:
                    if bias_on:
                        if inner_first:
                            part.seedEdgeByBias(biasMethod=ac.SINGLE,
                                                end1Edges=[e],
                                                minSize=new_core, maxSize=outer_sz)
                        else:
                            part.seedEdgeByBias(biasMethod=ac.SINGLE,
                                                end2Edges=[e],
                                                minSize=new_core, maxSize=outer_sz)
                    else:
                        _seed_pair(e, num=num_rad)
                    seeded_rad += 1
                except Exception:
                    _seed_pair(e, size=(new_core + outer_sz) * 0.5)
                    seeded_rad += 1

        # Circumferential (ring) edges — geometric-mean size
        for e in circ_e:
            length = _edge_length(e)
            if not length:
                continue
            _seed_pair(e, num=max(1, int(round(length / circ_sz))))
            seeded_circ += 1

    # ── 8. Seed outer edges ───────────────────────────────────────────────────
    seeded_outer = 0
    for i in outer_edge_set:
        e = part.edges[i]
        if _is_thickness_edge(cfg, e):
            continue
        _seed_pair(e, size=outer_sz)
        seeded_outer += 1

    # ── 9. Thickness seeds ────────────────────────────────────────────────────
    seeded_thick = 0
    if override_t:
        for e in part.edges:
            if _is_thickness_edge(cfg, e):
                try:
                    part.seedEdgeBySize([e], thick_seed, deviationFactor=0.1)
                    seeded_thick += 1
                except Exception:
                    pass

    summary = {
        'base_core_size_mm':   base_core,
        'new_core_size_mm':    new_core,
        'outer_size_mm':       outer_sz,
        'core_scale':          core_scale,
        'mr':                  mr,
        'growth_ratio':        growth,
        'bias_on':             bias_on,
        'seeded_core':         seeded_core,
        'seeded_trans_radial': seeded_rad,
        'seeded_trans_circ':   seeded_circ,
        'seeded_outer':        seeded_outer,
        'seeded_thickness':    seeded_thick,
    }
    print('  Topo seed summary: '
          'core=%.3fmm (base=%.3f × scale=%.2f / mr=%.2f) '
          'outer=%.3fmm (growth×%.1f) bias=%s | '
          'edges: core=%d spk_r=%d spk_c=%d outer=%d thick=%d'
          % (new_core, base_core, core_scale, mr,
             outer_sz, growth, 'on' if bias_on else 'off',
             seeded_core, seeded_rad, seeded_circ, seeded_outer, seeded_thick))
    return summary


def _apply_imported_seed_tuning(cfg, part, mode):
    """
    Keep the imported CAE seed topology and optionally scale the seed values.

    mode='imported' keeps in-plane seeds untouched.  mode='imported_scaled'
    rescales edge sizes/counts by a local radial factor: by default the
    center stays at factor 1.0 and the factor ramps to MR at the outer edge.
    Through-thickness edges can still be forced to N_THICKNESS_SEEDS so all
    studies retain the same integration depth.
    """
    mode = (mode or 'imported').lower()
    if mode == 'zones':
        _apply_mesh_zones(cfg, part)
        return
    if mode == 'outer_reseed':
        _apply_outer_reseed(cfg, part)
        return
    if mode == 'bands':
        _apply_seed_bands(cfg, part)
        return
    if mode in ('topological', 'topo'):
        _apply_topological_mesh_tuning(cfg, part)
        return
    scale = float(getattr(cfg, 'MESH_IMPORTED_SEED_SCALE',
                          getattr(cfg, 'MESH_REFINEMENT_FACTOR', 1.0)))
    scale_edges = mode in ('imported_scaled', 'scaled_imported')
    scale_mode = getattr(cfg, 'MESH_IMPORTED_SCALE_MODE', 'radial_growth').lower()
    override_t = getattr(cfg, 'MESH_OVERRIDE_THICKNESS_SEEDS', True)
    n_t = int(getattr(cfg, 'N_THICKNESS_SEEDS', 10))
    thickness_seed = float(cfg.BLANK_THICKNESS) / float(n_t)
    outer_radius = _part_outer_radius(part)

    _dump_mesh_seeds(cfg, part, 'imported_seeds_before')

    records = []
    for edge in part.edges:
        radius = _edge_radius(edge)
        method = _edge_seed(part, edge, 'EDGE_SEEDING_METHOD')
        size = _seed_float(_edge_seed(part, edge, 'SIZE'))
        number = _seed_int(_edge_seed(part, edge, 'NUMBER'))
        bias_min = _seed_float(_edge_seed(part, edge, 'BIAS_MIN_SIZE'))
        bias_max = _seed_float(_edge_seed(part, edge, 'BIAS_MAX_SIZE'))
        records.append((edge, radius, method, size, number, bias_min, bias_max,
                        _is_thickness_edge(cfg, edge)))

    default_size = (_seed_float(_part_seed(part, 'SIZE')) or
                    _seed_float(_part_seed(part, 'DEFAULT_SIZE')))
    if (scale_edges and scale_mode == 'uniform' and default_size is not None
            and abs(scale - 1.0) > 1.0e-9):
        try:
            part.seedPart(size=default_size * scale,
                          deviationFactor=0.1, minSizeFactor=0.1)
            print('  Imported global seed scaled: %.4g -> %.4g'
                  % (default_size, default_size * scale))
        except Exception as exc:
            print('  WARNING imported global seed scale failed: %s' % exc)

    scaled_size = 0
    scaled_number = 0
    scaled_default = 0
    skipped_bias = 0
    thick_seeded = 0
    scale_min = None
    scale_max = None
    for edge, radius, method, size, number, bias_min, bias_max, is_thick in records:
        if override_t and is_thick:
            try:
                part.seedEdgeBySize([edge], thickness_seed, deviationFactor=0.1)
                thick_seeded += 1
            except Exception:
                pass
            continue

        if not scale_edges or abs(scale - 1.0) <= 1.0e-9:
            continue

        local_scale = _imported_seed_scale_at_radius(
            cfg, radius, outer_radius, scale)
        scale_min = local_scale if scale_min is None else min(scale_min, local_scale)
        scale_max = local_scale if scale_max is None else max(scale_max, local_scale)

        method_text = str(method).upper() if method is not None else ''
        has_bias = ('BIAS' in method_text) or (bias_min is not None and
                                               bias_max is not None)
        if has_bias:
            skipped_bias += 1
            continue

        try:
            if abs(local_scale - 1.0) <= 1.0e-9:
                fixed_r = float(getattr(cfg, 'MESH_IMPORTED_FIXED_RADIUS', 20.0))
                if (scale_mode in ('banded', 'banded_growth', 'two_band')
                        and radius is not None and radius > fixed_r
                        and size is None and number is None
                        and default_size is not None):
                    part.seedEdgeBySize([edge], default_size,
                                        deviationFactor=0.1)
                    scaled_default += 1
                continue
            if 'NUMBER' in method_text and number is not None:
                new_number = max(1, int(round(float(number) / local_scale)))
                if new_number != number:
                    part.seedEdgeByNumber([edge], new_number)
                    scaled_number += 1
            elif size is not None:
                part.seedEdgeBySize([edge], size * local_scale,
                                    deviationFactor=0.1)
                scaled_size += 1
            elif number is not None:
                new_number = max(1, int(round(float(number) / local_scale)))
                if new_number != number:
                    part.seedEdgeByNumber([edge], new_number)
                    scaled_number += 1
            elif default_size is not None:
                part.seedEdgeBySize([edge], default_size * local_scale,
                                    deviationFactor=0.1)
                scaled_default += 1
        except Exception:
            pass

    print('  Imported mesh seeds: mode=%s, scale_mode=%s, target=%.4g, '
          'local=%.4g..%.4g, fixed_r=%.2f, outer_r=%.2f, '
          'size-scaled=%d, number-scaled=%d, default-scaled=%d, '
          'thickness=%d, skipped-bias=%d'
          % (mode, scale_mode, scale,
             scale_min if scale_min is not None else 1.0,
             scale_max if scale_max is not None else 1.0,
             float(getattr(cfg, 'MESH_IMPORTED_FIXED_RADIUS', 20.0)),
             outer_radius, scaled_size, scaled_number, scaled_default,
             thick_seeded, skipped_bias))
    _dump_mesh_seeds(cfg, part, 'imported_seeds_after')


def import_specimen_cae(cfg, postprocess=True):
    """
    Import the specimen mesh from the supervisor's geometry .cae file.
    All named sets (XSYMM, YSYMM, EDGE, ZMIN, ZMAX) propagate correctly
    to inst.sets when the part is instanced.
    If the .cae was saved with an older Abaqus release it is upgraded
    in-place via upgradeMdb() before opening.

    Set postprocess=False to stop after importing and regenerating the mesh.
    """
    path = _cae_path(cfg)
    if not os.path.isfile(path):
        raise IOError(
            'Geometry .cae not found: %s\n'
            '  Check INP_DIR and SPECIMEN_WIDTH in config.py.' % path)

    _TOOL_NAMES = {'Punch', 'Matrix', 'Die'}
    temp_model_name = '__specimen_import_temp__'
    abs_path = os.path.abspath(path)

    try:
        mdb.openAuxMdb(pathName=abs_path)
    except Exception as e:
        if 'incompatible release' in str(e).lower():
            print('  .cae version mismatch — upgrading via upgradeMdb...')
            _upgrade_cae(abs_path)
            mdb.openAuxMdb(pathName=abs_path)
        elif 'corrupt' in str(e).lower():
            print('  WARNING: .cae corrupt, falling back to .inp ...')
            import_specimen(cfg)
            return
        else:
            raise

    mdb.copyAuxMdbModel(fromName='Model-1', toName=temp_model_name)
    mdb.closeAuxMdb()

    temp_model = mdb.models[temp_model_name]
    candidates = [n for n in temp_model.parts.keys() if n not in _TOOL_NAMES]
    if not candidates:
        del mdb.models[temp_model_name]
        raise RuntimeError('No specimen part found in %s' % path)

    src_name = candidates[0]
    for preferred in ('Sample_Circ', 'Blank_Var', 'Part-1'):
        if preferred in candidates:
            src_name = preferred
            break

    m = mdb.models[cfg.MODEL_NAME]
    m.Part(name='Specimen', objectToCopy=temp_model.parts[src_name])
    del mdb.models[temp_model_name]

    spec = m.parts['Specimen']
    spec.Unlock(reportWarnings=False)
    print('  Specimen imported from: %s  (source part: "%s")' % (path, src_name))
    print('  Sets available: %s' % sorted(spec.sets.keys()))

    # ── Update extrusion depth so geometry + mesh both match BLANK_THICKNESS ──
    # The .cae parts have a 'Solid extrude-1' feature (set to depth=1.0 by
    # Open.py). Updating the depth and regenerating keeps the CAE geometry
    # visually correct and produces the right mesh without manual node editing.
    feature_name = 'Solid extrude-1'
    feat_names = [f for f in spec.features.keys()]
    if feature_name in feat_names:
        seed_mode = getattr(cfg, 'MESH_SEED_MODE', 'imported_scaled').lower()
        if seed_mode not in ('zones', 'imported', 'imported_scaled', 'scaled_imported',
                              'outer_reseed', 'bands', 'topological', 'topo'):
            raise ValueError("Invalid MESH_SEED_MODE: '%s'" % seed_mode)
        print('  Mesh seed mode: %s — preserving imported CAE seeds.' % seed_mode)
        spec.features[feature_name].setValues(depth=cfg.BLANK_THICKNESS)
        spec.regenerate()
        _apply_imported_seed_tuning(cfg, spec, seed_mode)
        spec.generateMesh()
        print('  Mesh generated: %d elements  (factor=%.4g)'
              % (len(spec.elements), getattr(cfg, 'MESH_REFINEMENT_FACTOR', 1.0)))
        print('  Extrusion depth set to %.4f mm — geometry + mesh updated.'
              % cfg.BLANK_THICKNESS)
    else:
        # Fallback: truly orphan mesh — no parametric feature to reseed, so
        # element count is fixed.  Apply coordinate scaling instead:
        #   1. scale x,y by MESH_REFINEMENT_FACTOR (larger factor → physically
        #      larger elements; blank XY dimensions scale proportionally)
        #   2. scale z to BLANK_THICKNESS
        print('  Feature "%s" not found — truly orphan mesh, using coordinate '
              'scaling.' % feature_name)
        factor = getattr(cfg, 'MESH_REFINEMENT_FACTOR', 1.0)
        if abs(factor - 1.0) > 1e-6:
            nodes = spec.nodes
            new_coords = [(n.coordinates[0] * factor,
                           n.coordinates[1] * factor,
                           n.coordinates[2]) for n in nodes]
            spec.editNode(nodes=nodes, coordinates=new_coords)
            print('  In-plane scaled by x%.4f  (element count unchanged, '
                  'blank XY dims scale by same factor)' % factor)
        _scale_specimen_thickness(cfg, spec)

    if postprocess:
        _rebuild_contact_surfaces(cfg, spec)
        _verify_symmetry_sets(spec)
        _add_elout_set(cfg, spec)
        _add_dome_zone_set(cfg, spec)


def import_specimen_mesh_only(cfg):
    """Import only the specimen CAE mesh with no reseeding or remeshing."""
    path = _cae_path(cfg)
    if not os.path.isfile(path):
        raise IOError(
            'Geometry .cae not found: %s\n'
            '  Check INP_DIR and SPECIMEN_WIDTH in config.py.' % path)

    _TOOL_NAMES = {'Punch', 'Matrix', 'Die'}
    temp_model_name = '__specimen_import_temp__'
    abs_path = os.path.abspath(path)

    try:
        mdb.openAuxMdb(pathName=abs_path)
    except Exception as e:
        if 'incompatible release' in str(e).lower():
            print('  .cae version mismatch — upgrading via upgradeMdb...')
            _upgrade_cae(abs_path)
            mdb.openAuxMdb(pathName=abs_path)
        else:
            raise

    mdb.copyAuxMdbModel(fromName='Model-1', toName=temp_model_name)
    mdb.closeAuxMdb()

    temp_model = mdb.models[temp_model_name]
    candidates = [n for n in temp_model.parts.keys() if n not in _TOOL_NAMES]
    if not candidates:
        del mdb.models[temp_model_name]
        raise RuntimeError('No specimen part found in %s' % path)

    src_name = candidates[0]
    for preferred in ('Sample_Circ', 'Blank_Var', 'Part-1'):
        if preferred in candidates:
            src_name = preferred
            break

    m = mdb.models[cfg.MODEL_NAME]
    m.Part(name='Specimen', objectToCopy=temp_model.parts[src_name])
    del mdb.models[temp_model_name]

    spec = m.parts['Specimen']
    spec.Unlock(reportWarnings=False)
    print('  Specimen imported from: %s  (source part: "%s")' % (path, src_name))
    print('  Sets available: %s' % sorted(spec.sets.keys()))


def import_specimen(cfg):
    """
    Import the specimen mesh from the supervisor's geometry .inp file.
    The file provides: C3D8R nodes/elements, nsets (NALL, XSYMM, YSYMM,
    EDGE), elsets (ELALL, ELOUT), and surfaces (ZMIN, ZMAX).
    Material, section and BCs are defined by our modules.

    The geometry files have no *Part/*End Part block — they were designed
    for *INCLUDE, not PartFromInputFile.  In Abaqus 2023, PartFromInputFile
    without a *Part wrapper only imports 'generate'-style sets (ELALL) and
    drops all explicit node/element lists (EDGE, XSYMM, YSYMM, _ZMAX_S1,
    _ZMIN_S2).  Fix: write a temporary wrapper that adds *Part/*End Part
    around the original content before calling PartFromInputFile.

    After import the z-coordinates are rescaled to cfg.BLANK_THICKNESS.
    All named sets survive because they are label-based.
    """
    path = _inp_path(cfg)
    if not os.path.isfile(path):
        raise IOError(
            'Geometry .inp not found: %s\n'
            '  Check INP_DIR and SPECIMEN_WIDTH in config.py.' % path)

    # Write a temporary *Part-wrapped version of the geometry file
    wrapped_path = path.replace('.inp', '_wrapped.inp')
    with open(path, 'r') as f:
        content = f.read()
    with open(wrapped_path, 'w') as f:
        f.write('*Part, name=Specimen\n')
        f.write(content)
        f.write('\n*End Part\n')

    _TOOL_NAMES = {'Punch', 'Matrix', 'Die'}
    m = mdb.models[cfg.MODEL_NAME]
    parts_before = set(m.parts.keys())
    try:
        m.PartFromInputFile(inputFileName=wrapped_path)
    finally:
        os.remove(wrapped_path)

    parts_after = set(m.parts.keys())
    new_parts = parts_after - parts_before - _TOOL_NAMES
    if not new_parts:
        raise RuntimeError(
            'PartFromInputFile did not add any new part to the model.\n'
            '  File: %s' % path)
    spec_name = sorted(new_parts)[0]
    print('  Specimen imported from: %s  (part: "%s")' % (path, spec_name))
    print('  Sets available: %s' % sorted(m.parts[spec_name].sets.keys()))
    _ensure_surface_elsets(path, m.parts[spec_name])
    spec_part = m.parts[spec_name]
    factor = getattr(cfg, 'MESH_REFINEMENT_FACTOR', 1.0)
    if abs(factor - 1.0) > 1e-6:
        nodes = spec_part.nodes
        new_coords = [(n.coordinates[0] * factor,
                       n.coordinates[1] * factor,
                       n.coordinates[2]) for n in nodes]
        spec_part.editNode(nodes=nodes, coordinates=new_coords)
        print('  In-plane scaled by x%.4f  (element count unchanged, '
              'blank XY dims scale by same factor)' % factor)
    _scale_specimen_thickness(cfg, spec_part)
    _add_elout_set(cfg, spec_part)
    _add_dome_zone_set(cfg, spec_part)


def _ensure_surface_elsets(inp_path, part):
    """
    Guarantee that the backing elsets for ZMAX and ZMIN contact surfaces
    exist on *part*.

    Abaqus 2023 PartFromInputFile silently drops elsets whose names begin
    with an underscore (e.g. _ZMAX_S1, _ZMIN_S2), even when they use the
    *generate* syntax that normally survives the import.  We recover them
    by re-parsing the original geometry .inp and creating any missing sets
    directly via the Abaqus Python API.
    """
    import re
    needed = {'_ZMAX_S1', '_ZMIN_S2'}
    missing = needed - set(part.sets.keys())
    if not missing:
        print('  Backing elsets already present: %s' % sorted(needed))
        return

    parsed = {}
    gen_pattern = re.compile(
        r'^\*Elset\s*,.*elset\s*=\s*(_[A-Za-z0-9_]+)\s*,.*generate',
        re.IGNORECASE)
    with open(inp_path, 'r') as fh:
        lines = fh.readlines()

    i = 0
    while i < len(lines):
        hit = gen_pattern.match(lines[i])
        if hit:
            set_name = hit.group(1)
            if set_name in missing and i + 1 < len(lines):
                parts_data = lines[i + 1].split(',')
                if len(parts_data) >= 3:
                    start = int(parts_data[0].strip())
                    end   = int(parts_data[1].strip())
                    step  = int(parts_data[2].strip())
                    parsed[set_name] = range(start, end + 1, step)
        i += 1

    for set_name in sorted(missing):
        if set_name not in parsed:
            raise RuntimeError('Could not parse elset "%s" from %s — '
                               'required for ZMIN/ZMAX contact surfaces.' % (set_name, inp_path))
        elem_labels = list(parsed[set_name])
        elems = part.elements.sequenceFromLabels(elem_labels)
        part.Set(name=set_name, elements=elems)
        print('  Created missing elset "%s" (%d elements) from .inp parse.'
              % (set_name, len(elem_labels)))


def _scale_specimen_thickness(cfg, part):
    """
    Rescale node z-coordinates so that [z_min, z_max] maps to
    [0, cfg.BLANK_THICKNESS].

    The native mesh may have any thickness encoded in its z-extent.
    Scaling is a simple linear stretch; all nsets, elsets and surfaces
    (NALL, XSYMM, YSYMM, EDGE, ELALL, ELOUT, ZMIN, ZMAX) reference
    node/element labels and are therefore unaffected.
    """
    nodes = part.nodes
    z_vals = [n.coordinates[2] for n in nodes]
    z_min  = min(z_vals)
    z_max  = max(z_vals)
    native_t = z_max - z_min

    if native_t < 1.0e-10:
        print('  WARNING: blank z-extent ~ 0 — thickness scaling skipped.')
        return

    target_t = float(cfg.BLANK_THICKNESS)
    scale    = target_t / native_t

    if abs(scale - 1.0) < 1.0e-6:
        print('  Thickness: %.4f mm — no scaling needed.' % target_t)
        return

    new_coords = [
        (n.coordinates[0],
         n.coordinates[1],
         (n.coordinates[2] - z_min) * scale)
        for n in nodes
    ]
    part.editNode(nodes=nodes, coordinates=new_coords)
    print('  Thickness scaled: %.6f → %.4f mm  (x %.6f)'
          % (native_t, target_t, scale))


def _verify_symmetry_sets(part):
    """
    After mesh regeneration, verify that XSYMM and YSYMM node sets still exist
    and have nodes.  If a set is empty (can happen when the .cae geometry-based
    set loses its face reference after unlock/regenerate), rebuild it from node
    coordinates:

      'XSYMM' set  →  nodes at  y ≈ 0  (naming from Lennard's rotated frame)
      'YSYMM' set  →  nodes at  x ≈ 0

    The EDGE set is also verified / rebuilt as nodes at r ≥ (max_r - tol).
    """
    tol = 1.0e-3   # mm — tight tolerance for planar sets

    node_coords = {n.label: n.coordinates for n in part.nodes}
    x_vals = [c[0] for c in node_coords.values()]
    y_vals = [c[1] for c in node_coords.values()]
    x_plane = min(x_vals) if x_vals else 0.0
    y_plane = min(y_vals) if y_vals else 0.0

    def _rebuild_planar(set_name, coord_idx, plane):
        """Rebuild a symmetry-plane nset from coordinate scanning."""
        labels = [lbl for lbl, c in node_coords.items()
                  if abs(c[coord_idx] - plane) < tol]
        if not labels:
            labels = [lbl for lbl, c in node_coords.items()
                      if abs(c[coord_idx] - plane) < max(tol, 1.0e-2)]
        if not labels:
            print('  WARNING _verify_symmetry_sets: no nodes found at '
                 'coord[%d]≈%.4f for set "%s".' % (coord_idx, plane, set_name))
            return
        node_seq = part.nodes.sequenceFromLabels(labels)
        part.Set(name=set_name, nodes=node_seq)
        print('  Rebuilt "%s" from coordinates: %d nodes at coord[%d]=%.4f'
              % (set_name, len(labels), coord_idx, plane))

    for set_name, coord_idx, plane in (('XSYMM', 1, y_plane), ('YSYMM', 0, x_plane)):
        if set_name not in part.sets.keys():
            print('  "%s" set missing after mesh generation — rebuilding...'
                  % set_name)
            _rebuild_planar(set_name, coord_idx, plane)
        else:
            n = len(part.sets[set_name].nodes)
            if n == 0:
                print('  "%s" set has 0 nodes after mesh generation — rebuilding...'
                      % set_name)
                _rebuild_planar(set_name, coord_idx, plane)
            else:
                print('  "%s" set OK: %d nodes.' % (set_name, n))

    # EDGE: nodes at r ≥ (max_r - tol)
    import math
    r_vals = {lbl: math.sqrt(c[0]**2 + c[1]**2)
              for lbl, c in node_coords.items()}
    max_r = max(r_vals.values()) if r_vals else 0.0
    edge_tol = max(tol, max_r * 1.0e-4)

    if 'EDGE' not in part.sets.keys():
        print('  "EDGE" set missing — rebuilding from max_r=%.3f...' % max_r)
        edge_labels = [lbl for lbl, r in r_vals.items()
                       if r >= max_r - edge_tol]
        if edge_labels:
            part.Set(name='EDGE',
                     nodes=part.nodes.sequenceFromLabels(edge_labels))
            print('  Rebuilt "EDGE": %d nodes at r≥%.3f mm'
                  % (len(edge_labels), max_r - edge_tol))
    else:
        n = len(part.sets['EDGE'].nodes)
        if n == 0:
            print('  "EDGE" set has 0 nodes — rebuilding from max_r=%.3f...'
                  % max_r)
            edge_labels = [lbl for lbl, r in r_vals.items()
                           if r >= max_r - edge_tol]
            if edge_labels:
                part.Set(name='EDGE',
                         nodes=part.nodes.sequenceFromLabels(edge_labels))
                print('  Rebuilt "EDGE": %d nodes at r≥%.3f mm'
                      % (len(edge_labels), max_r - edge_tol))
        else:
            print('  "EDGE" set OK: %d nodes.' % n)


def _rebuild_contact_surfaces(cfg, part):
    """
    Recreate ZMIN and ZMAX element-based surfaces on the orphan-mesh specimen.

    Geometric faces (part.faces) are unavailable for orphan mesh parts.
    Instead, element connectivity is used: for each C3D8R element, check all
    6 faces to find which one has all 4 nodes at z=0 (ZMIN) or z=t (ZMAX).

    C3D8R face-to-local-node-index map (0-based connectivity array):
      S1: [0,1,2,3]   S2: [4,7,6,5]
      S3: [0,4,5,1]   S4: [1,5,6,2]
      S5: [2,6,7,3]   S6: [3,7,4,0]
    """
    existing_surfaces = set(getattr(part, 'surfaces', {}).keys())
    if {'ZMIN', 'ZMAX'}.issubset(existing_surfaces):
        print('  Surface ZMIN/ZMAX already present — keeping imported surfaces.')
        return

    tol = 1.0e-4
    node_z_vals = [n.coordinates[2] for n in part.nodes]
    if not node_z_vals:
        raise RuntimeError('_rebuild_contact_surfaces: no nodes found.')
    z_bot = min(node_z_vals)
    z_top = max(node_z_vals)
    span = max(1.0e-9, z_top - z_bot)
    tol_z = max(tol, span * 1.0e-3, 1.0e-4)

    # C3D8R face → local node indices (0-based)
    FACE_NODES = {
        1: [0,1,2,3],
        2: [4,7,6,5],
        3: [0,4,5,1],
        4: [1,5,6,2],
        5: [2,6,7,3],
        6: [3,7,4,0],
    }

    node_z = {n.label: n.coordinates[2] for n in part.nodes}

    # face_num → list of element labels having that face at z_bot or z_top
    bot_by_face = {i: [] for i in range(1, 7)}
    top_by_face = {i: [] for i in range(1, 7)}

    for elem in part.elements:
        elem_nodes = elem.getNodes()
        if len(elem_nodes) != 8:
            continue
        node_labels = [n.label for n in elem_nodes]
        for face_num, idx in FACE_NODES.items():
            zs = [node_z[node_labels[i]] for i in idx]
            if all(abs(z - z_bot) < tol_z for z in zs):
                bot_by_face[face_num].append(elem.label)
            elif all(abs(z - z_top) < tol_z for z in zs):
                top_by_face[face_num].append(elem.label)

    def _make_surface(by_face, surf_name, z_desc):
        total = sum(len(v) for v in by_face.values())
        if total == 0:
            raise RuntimeError('_rebuild_contact_surfaces: no elements found '
                               'at %s — %s cannot be created.' % (z_desc, surf_name))
        kwargs = {}
        face_kw = {1:'face1Elements', 2:'face2Elements', 3:'face3Elements',
                   4:'face4Elements', 5:'face5Elements', 6:'face6Elements'}
        for face_num, labels in by_face.items():
            if not labels:
                continue
            elems = part.elements.sequenceFromLabels(labels)
            set_name = '_%s_S%d' % (surf_name, face_num)
            part.Set(name=set_name, elements=elems)
            kwargs[face_kw[face_num]] = part.sets[set_name].elements
        part.Surface(name=surf_name, **kwargs)
        print('  Surface %s rebuilt: %d element faces at %s'
              % (surf_name, total, z_desc))

    _make_surface(bot_by_face, 'ZMIN', 'z=%.4f' % z_bot)
    _make_surface(top_by_face, 'ZMAX', 'z=%.4f' % z_top)


# ─────────────────────────────────────────────────────────────
# PiP inner punch — import from CAE file
# ─────────────────────────────────────────────────────────────

def import_pip_punch2_cae(cfg):
    """
    Import the inner punch (Punch2) geometry from PIP_PUNCH_CAE.

    Each punch variant lives in its own .cae file inside PiP_Punches/.
    The file is expected to contain a single part; if the part name matches
    PIP_PUNCH2_ID it is used directly, otherwise the first (and only) part
    is taken with a warning so the import still works even if the internal
    name differs.

    If the .cae was saved with an older Abaqus release it is upgraded in-place
    before opening, using the same _upgrade_cae helper as the specimen import.
    """
    path = os.path.abspath(cfg.PIP_PUNCH_CAE)
    if not os.path.isfile(path):
        raise IOError(
            'Inner punch .cae not found: %s\n'
            '  Check PIP_PUNCH2_ID in config.py and verify PiP_Punches/ contains the file.'
            % path)

    punch_id = cfg.PIP_PUNCH2_ID
    temp_model_name = '__punch2_import_temp__'

    try:
        mdb.openAuxMdb(pathName=path)
    except Exception as e:
        if 'incompatible release' in str(e).lower():
            print('  .cae version mismatch — upgrading via upgradeMdb...')
            _upgrade_cae(path)
            mdb.openAuxMdb(pathName=path)
        else:
            raise

    # The CAE may contain multiple models — try 'Model-1' first, then any other.
    aux_model_names = list(mdb.models.keys())
    src_model_name  = 'Model-1' if 'Model-1' in aux_model_names else aux_model_names[0]
    mdb.copyAuxMdbModel(fromName=src_model_name, toName=temp_model_name)
    mdb.closeAuxMdb()

    temp_model = mdb.models[temp_model_name]
    part_names = list(temp_model.parts.keys())

    if punch_id in part_names:
        src_part_name = punch_id
    elif len(part_names) == 1:
        # Single-part CAE — accept it regardless of internal name.
        src_part_name = part_names[0]
        print('  WARNING: part "%s" not found in %s; using only part "%s".'
              % (punch_id, os.path.basename(path), src_part_name))
    else:
        del mdb.models[temp_model_name]
        raise RuntimeError(
            'Part "%s" not found in %s.\n'
            '  Available parts: %s\n'
            '  Set PIP_PUNCH2_ID in config.py to one of the names above.'
            % (punch_id, path, part_names))

    m = mdb.models[cfg.MODEL_NAME]
    m.Part(name='Punch2', objectToCopy=temp_model.parts[src_part_name])
    del mdb.models[temp_model_name]

    # Imported punch is already correctly oriented along Z and has an RP at
    # its topmost point — no node normalisation or rotation needed.
    print('  Punch2 imported from: %s  (part: "%s")' % (path, src_part_name))


# ─────────────────────────────────────────────────────────────
# Reference points and contact surfaces for rigid tools
# ─────────────────────────────────────────────────────────────

def create_tool_rp_and_surfaces(cfg):
    """
    For each rigid tool: create RP set and 'Outer' surface.
    Tool names depend on TEST_TYPE (PiP has Punch1 + Punch2 instead of Punch).
    """
    test_type = getattr(cfg, 'TEST_TYPE', 'nakazima').lower()
    if test_type == 'pip':
        tool_names = ('Punch1', 'Punch2', 'Matrix', 'Die')
    else:
        tool_names = ('Punch', 'Matrix', 'Die')

    for tool_name in tool_names:
        p = mdb.models[cfg.MODEL_NAME].parts[tool_name]
        r = p.referencePoints
        if len(r) == 0:
            p.ReferencePoint(point=(0.0, 0.0, 0.0))
            r = p.referencePoints
            print('  RP created on %s' % tool_name)
        else:
            print('  RP already exists on %s (imported from CAE)' % tool_name)
        p.Set(referencePoints=(r[max(r.keys())],), name='RP')
        try:
            if len(p.faces) == 0:
                raise ValueError('p.faces is empty for analytic rigid part')
            p.Surface(side1Faces=p.faces, name='Outer')
            print('  Surface "Outer" created on %s (%d face(s))'
                  % (tool_name, len(p.faces)))
        except Exception as e:
            raise RuntimeError('Surface "Outer" creation failed on %s: %s' % (tool_name, e))

    print('  RPs, Sets and tool surfaces: OK')


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def create_parts(cfg):
    """Create all parts according to GEOMETRY_SOURCE and TEST_TYPE."""
    print('--- Part creation ---')
    test_type = getattr(cfg, 'TEST_TYPE', 'nakazima').lower()
    if test_type == 'nakazima':
        create_punch(cfg)
        create_die(cfg)
        create_matrix(cfg)
    elif test_type == 'marciniak':
        create_flat_punch(cfg)
        create_die(cfg)
        create_matrix(cfg)
    elif test_type == 'pip':
        create_pip_punch1(cfg)
        pip_punch2_id = getattr(cfg, 'PIP_PUNCH2_ID', None)
        if pip_punch2_id:
            import_pip_punch2_cae(cfg)
        else:
            create_pip_punch2(cfg)
        create_pip_die(cfg)
        create_pip_matrix(cfg)
    else:
        raise ValueError("Unknown TEST_TYPE: '%s'." % test_type)

    if cfg.GEOMETRY_SOURCE == 'cae':
        import_specimen_cae(cfg)
    elif cfg.GEOMETRY_SOURCE == 'inp':
        import_specimen(cfg)
    else:
        raise ValueError("Invalid GEOMETRY_SOURCE: '%s'" % cfg.GEOMETRY_SOURCE)

    create_tool_rp_and_surfaces(cfg)
    print('--- Parts done ---')
