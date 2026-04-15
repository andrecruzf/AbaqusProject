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
from abaqusConstants import (
    THREE_D, ANALYTIC_RIGID_SURFACE, DEFORMABLE_BODY,
    STANDALONE, CLOCKWISE, OFF
)
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


def _add_elout_set(cfg, part):
    """
    Create the ELOUT element set on *part* by reading the element label from
    the geometry .inp file.

    ELOUT is defined in the .inp as a single-element set at the punch apex.
    When the specimen is imported from a .cae file this set is absent — the
    .cae only carries the geometry/mesh, not the named sets defined in .inp.
    Parsing the label here ensures it propagates to the ODB and is available
    in postproc.py without any extra lookup.
    """
    import re
    inp = _inp_path(cfg)
    if not os.path.isfile(inp):
        print('  WARNING _add_elout_set: .inp not found (%s) — ELOUT skipped.' % inp)
        return

    label = None
    with open(inp, 'r') as f:
        in_elout = False
        for line in f:
            if re.match(r'\*Elset.*elset\s*=\s*ELOUT', line, re.IGNORECASE):
                in_elout = True
                continue
            if in_elout:
                stripped = line.strip().rstrip(',')
                if stripped.isdigit():
                    label = int(stripped)
                break

    if label is None:
        print('  WARNING _add_elout_set: could not parse ELOUT label from %s.' % inp)
        return

    try:
        elems = part.elements.sequenceFromLabels([label])
        part.Set(name='ELOUT', elements=elems)
        print('  ELOUT set  : element %d  (from %s)' % (label, os.path.basename(inp)))
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
    try:
        subprocess.call(['abaqus', 'cae', 'noGUI=' + tmp_script.name])
    finally:
        os.remove(tmp_script.name)

    if not os.path.exists(tmp_path):
        raise RuntimeError('upgradeMdb did not produce output: %s' % tmp_path)

    os.remove(abs_path)
    os.rename(tmp_path, abs_path)
    print('  Upgrade complete: %s' % os.path.basename(abs_path))


def import_specimen_cae(cfg):
    """
    Import the specimen mesh from the supervisor's geometry .cae file.
    All named sets (XSYMM, YSYMM, EDGE, ZMIN, ZMAX) propagate correctly
    to inst.sets when the part is instanced.
    If the .cae was saved with an older Abaqus release it is upgraded
    in-place via upgradeMdb() before opening.
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
        spec.features[feature_name].setValues(depth=cfg.BLANK_THICKNESS)
        spec.regenerate()
        spec.generateMesh()
        print('  Extrusion depth set to %.4f mm — geometry + mesh updated.'
              % cfg.BLANK_THICKNESS)
    else:
        # Fallback: feature not found (e.g. truly orphan mesh) — scale nodes
        print('  Feature "%s" not found (orphan mesh?) — falling back to '
              'node scaling.' % feature_name)
        _scale_specimen_thickness(cfg, spec)

    _rebuild_contact_surfaces(cfg, spec)
    _verify_symmetry_sets(spec)
    _add_elout_set(cfg, spec)


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
    _scale_specimen_thickness(cfg, m.parts[spec_name])
    _add_elout_set(cfg, m.parts[spec_name])


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
            print('  WARNING: could not parse "%s" from %s — '
                  'ZMIN/ZMAX surface creation will fail.' % (set_name, inp_path))
            continue
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

    def _rebuild_planar(set_name, coord_idx):
        """Rebuild a symmetry-plane nset from coordinate scanning."""
        labels = [lbl for lbl, c in node_coords.items()
                  if abs(c[coord_idx]) < tol]
        if not labels:
            print('  WARNING _verify_symmetry_sets: no nodes found at '
                  'coord[%d]≈0 for set "%s".' % (coord_idx, set_name))
            return
        node_seq = part.nodes.sequenceFromLabels(labels)
        part.Set(name=set_name, nodes=node_seq)
        print('  Rebuilt "%s" from coordinates: %d nodes at coord[%d]=0'
              % (set_name, len(labels), coord_idx))

    for set_name, coord_idx in (('XSYMM', 1), ('YSYMM', 0)):
        if set_name not in part.sets.keys():
            print('  "%s" set missing after mesh generation — rebuilding...'
                  % set_name)
            _rebuild_planar(set_name, coord_idx)
        else:
            n = len(part.sets[set_name].nodes)
            if n == 0:
                print('  "%s" set has 0 nodes after mesh generation — rebuilding...'
                      % set_name)
                _rebuild_planar(set_name, coord_idx)
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
    tol   = 1.0e-4
    z_bot = 0.0
    z_top = float(cfg.BLANK_THICKNESS)

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
            if all(abs(z - z_bot) < tol for z in zs):
                bot_by_face[face_num].append(elem.label)
            elif all(abs(z - z_top) < tol for z in zs):
                top_by_face[face_num].append(elem.label)

    def _make_surface(by_face, surf_name, z_desc):
        total = sum(len(v) for v in by_face.values())
        if total == 0:
            print('  WARNING _rebuild_contact_surfaces: no elements found '
                  'at %s — %s not created.' % (z_desc, surf_name))
            return
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

    _make_surface(bot_by_face, 'ZMIN', 'z=0')
    _make_surface(top_by_face, 'ZMAX', 'z=%.4f' % z_top)


# ─────────────────────────────────────────────────────────────
# PiP inner punch — import from CAE file
# ─────────────────────────────────────────────────────────────

def import_pip_punch2_cae(cfg):
    """
    Import the inner punch (Punch2) geometry from PIP_PUNCH_CAE (a single CAE
    file containing all inner punch variants as separate parts).  The part
    named cfg.PIP_PUNCH2_ID is copied into the current model as 'Punch2'.

    If the .cae was saved with an older Abaqus release it is upgraded in-place
    before opening, using the same _upgrade_cae helper as the specimen import.
    If PIP_PUNCH2_ID does not match any part, available part names are printed.
    """
    path = os.path.abspath(cfg.PIP_PUNCH_CAE)
    if not os.path.isfile(path):
        raise IOError(
            'Inner punch .cae not found: %s\n'
            '  Check PIP_PUNCH_CAE in config.py.' % path)

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

    temp_model  = mdb.models[temp_model_name]
    part_names  = list(temp_model.parts.keys())

    if punch_id not in part_names:
        del mdb.models[temp_model_name]
        raise RuntimeError(
            'Part "%s" not found in %s.\n'
            '  Available parts: %s\n'
            '  Set PIP_PUNCH2_ID in config.py to one of the names above.'
            % (punch_id, path, part_names))

    m = mdb.models[cfg.MODEL_NAME]
    m.Part(name='Punch2', objectToCopy=temp_model.parts[punch_id])
    del mdb.models[temp_model_name]

    # Imported punch is already correctly oriented along Z and has an RP at
    # its topmost point — no node normalisation or rotation needed.
    print('  Punch2 imported from: %s  (part: "%s")' % (path, punch_id))


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
            print('  WARNING surface "%s": %s' % (tool_name, e))

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
