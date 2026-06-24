# -*- coding: utf-8 -*-
"""
modules/boundary.py
Boundary conditions for the Nakazima quarter-model.

Convention (after assembly rotation):
  Z = forming direction — punch moves +Z (U3 = PUNCH_DISPLACEMENT)
  Blank in the XY plane: symmetry at X=0 (XSYMM) and Y=0 (YSYMM)

BCs applied:
  1. Matrix-1.RP  → ENCASTRE  (blank holder fixed)
  2. Die-1.RP     → ENCASTRE  (die fixed)
  3. Punch-1.RP   → U1=U2=UR1=UR2=UR3=0, U3=PUNCH_DISPLACEMENT (SmoothStep)
  4. Specimen XSYMM nset → XSYMM
  5. Specimen YSYMM nset → YSYMM
  6. Specimen EDGE nset  → ENCASTRE  (optional, controlled by USE_EDGE_ENCASTRE)

The XSYMM, YSYMM, and EDGE nsets are defined in the geometry .inp files
and imported with the specimen part.
"""
from abaqus import mdb
from abaqusConstants import SET
import math


def apply_bcs(cfg):
    """Apply all boundary conditions."""
    print('--- Boundary conditions ---')
    m = mdb.models[cfg.MODEL_NAME]
    a = m.rootAssembly
    test_type = getattr(cfg, 'TEST_TYPE', 'nakazima').lower()

    # Die and blank holder always fixed
    m.EncastreBC(name='BC_Matrix_Fixed',
                 createStepName='Initial',
                 region=a.instances['Matrix-1'].sets['RP'])
    print('  BC_Matrix_Fixed: ENCASTRE')

    m.EncastreBC(name='BC_Die_Fixed',
                 createStepName='Initial',
                 region=a.instances['Die-1'].sets['RP'])
    print('  BC_Die_Fixed: ENCASTRE')

    if test_type == 'pip':
        _apply_pip_punch_bcs(cfg, m, a)
    else:
        _apply_punch_bc(cfg, m, a)

    if getattr(cfg, 'ENABLE_SYMMETRIES', True):
        _apply_symmetry_bcs(cfg, m, a)
    else:
        print('  Symmetry BCs disabled by ENABLE_SYMMETRIES=0')

    if cfg.USE_EDGE_ENCASTRE:
        _apply_edge_bc(cfg, m, a)

    print('--- BCs done ---')


def _apply_punch_bc(cfg, m, a):
    """
    Standard single-punch BC.
    Initial: all DOFs fixed.
    Forming: U3 = +PUNCH_DISPLACEMENT with SmoothStep.
    """
    region = a.instances['Punch-1'].sets['RP']

    m.DisplacementBC(
        name='BC_Punch',
        createStepName='Initial',
        region=region,
        u1=SET, u2=SET, u3=SET,
        ur1=SET, ur2=SET, ur3=SET)

    m.boundaryConditions['BC_Punch'].setValuesInStep(
        stepName='Forming',
        u3=cfg.PUNCH_DISPLACEMENT,
        amplitude='Amp_Punch')

    print('  BC_Punch: U3 = +%.1f mm (SmoothStep Amp_Punch)' % cfg.PUNCH_DISPLACEMENT)


def _apply_pip_punch_bcs(cfg, m, a):
    """
    PiP two-punch BCs across two steps.

    Step1_Clamp (both punches move together):
      Punch1: U3 = +PIP_PUNCH1_DISPLACEMENT  (Amp_Step1)
      Punch2: U3 = +PIP_PUNCH1_DISPLACEMENT  (same travel, Amp_Step1)

    Step2_Form (Punch1 locked, Punch2 continues):
      Punch1: ENCASTRE (velocity=0 → holds at end-of-Step1 position, 20 mm)
      Punch2: U3 = +PIP_PUNCH2_DISPLACEMENT  (Amp_Step2)
    """
    d1 = cfg.PIP_PUNCH1_DISPLACEMENT
    d2 = cfg.PIP_PUNCH2_DISPLACEMENT
    r1 = a.instances['Punch1-1'].sets['RP']
    r2 = a.instances['Punch2-1'].sets['RP']

    # Punch1 — Initial: all fixed
    m.DisplacementBC(
        name='BC_Punch1',
        createStepName='Initial',
        region=r1,
        u1=SET, u2=SET, u3=SET,
        ur1=SET, ur2=SET, ur3=SET)
    # Step1: drive +d1
    m.boundaryConditions['BC_Punch1'].setValuesInStep(
        stepName='Step1_Clamp',
        u3=d1,
        amplitude='Amp_Step1')
    # Step2: deactivate the ramping BC; apply ENCASTRE to lock Punch1 at its
    # end-of-Step1 position.  In Abaqus/Explicit, ENCASTRE constrains nodal
    # velocity to zero — it holds the node in place, NOT forces it back to the
    # reference (undeformed) origin.  This matches the reference INP:
    #   *Boundary
    #   PUNCH_1-1.PUNCH1_RP_SET, ENCASTRE
    m.boundaryConditions['BC_Punch1'].deactivate(stepName='Step2_Form')
    m.EncastreBC(name='BC_Punch1_Hold',
                 createStepName='Step2_Form',
                 region=r1)

    # Punch2 — Initial: all fixed
    m.DisplacementBC(
        name='BC_Punch2',
        createStepName='Initial',
        region=r2,
        u1=SET, u2=SET, u3=SET,
        ur1=SET, ur2=SET, ur3=SET)
    # Step1: drive +d1 (same as Punch1)
    m.boundaryConditions['BC_Punch2'].setValuesInStep(
        stepName='Step1_Clamp',
        u3=d1,
        amplitude='Amp_Step1')
    # Step2: drive additional +d2
    m.boundaryConditions['BC_Punch2'].setValuesInStep(
        stepName='Step2_Form',
        u3=d2,
        amplitude='Amp_Step2')

    print('  BC_Punch1: Step1 U3=+%.1f mm; Step2 held' % d1)
    print('  BC_Punch2: Step1 U3=+%.1f mm; Step2 U3=+%.1f mm' % (d1, d2))


def _get_region(a, inst, set_name):
    inst_name = inst.name

    # 1️⃣ Normal propagated set (best case)
    if set_name in inst.sets.keys():
        return inst.sets[set_name]

    # 2️⃣ Assembly-level renamed set (PartFromInputFile case)
    asm_name = 'ASSEMBLY_%s_%s' % (inst_name, set_name)
    if asm_name in a.sets.keys():
        return a.sets[asm_name]

    # 3️⃣ Old fallback
    if set_name in a.sets.keys():
        return a.sets[set_name]

    return None


def _rebuild_instance_region(a, inst, set_name, kind):
    """
    Rebuild an assembly-level node set from instance coordinates when the
    propagated part set is missing or empty after mesh regeneration.
    """
    tol = 1.0e-3
    labels = []
    xs = [n.coordinates[0] for n in inst.nodes]
    ys = [n.coordinates[1] for n in inst.nodes]
    x_plane = min(xs) if xs else 0.0
    y_plane = min(ys) if ys else 0.0

    if kind == 'x':
        coords = [abs(n.coordinates[0] - x_plane) for n in inst.nodes]
        if coords:
            tol = max(tol, max(coords) * 1.0e-4)
        labels = [n.label for n in inst.nodes if abs(n.coordinates[0] - x_plane) <= tol]
    elif kind == 'y':
        coords = [abs(n.coordinates[1] - y_plane) for n in inst.nodes]
        if coords:
            tol = max(tol, max(coords) * 1.0e-4)
        labels = [n.label for n in inst.nodes if abs(n.coordinates[1] - y_plane) <= tol]
    elif kind == 'edge':
        r_vals = [math.sqrt(n.coordinates[0] ** 2 + n.coordinates[1] ** 2)
                  for n in inst.nodes]
        if r_vals:
            max_r = max(r_vals)
            edge_tol = max(tol, max_r * 1.0e-4)
            labels = [n.label for n, r in zip(inst.nodes, r_vals)
                      if r >= max_r - edge_tol]
    else:
        raise ValueError('Unknown rebuild kind: %s' % kind)

    if not labels:
        return None

    asm_name = 'ASSEMBLY_%s_%s' % (inst.name, set_name)
    region = inst.nodes.sequenceFromLabels(labels)
    a.Set(name=asm_name, nodes=region)
    return a.sets[asm_name]


def _apply_symmetry_bcs(cfg, m, a):
    """
    Apply XSYMM and YSYMM BCs from the node sets defined in the geometry .inp.
    Search order: instance sets → assembly sets → warning.

    The geometry sets are expected to follow the standard quarter-model naming:
      'XSYMM' nset -> nodes on the x = 0 plane -> apply XsymmBC
      'YSYMM' nset -> nodes on the y = 0 plane -> apply YsymmBC
    """
    inst = a.instances['Specimen-1']

    # Symmetry plane at X=0 (U1=UR2=UR3=0) — nodes are in the 'XSYMM' nset
    region = _get_region(a, inst, 'XSYMM')
    if region is None or len(region.nodes) == 0:
        region = _rebuild_instance_region(a, inst, 'XSYMM', 'x')
    if region is None:
        raise RuntimeError('"XSYMM" set not found on Specimen-1 — BC_Sym_X (x=0 plane) cannot be applied.')
    if len(region.nodes) == 0:
        raise RuntimeError('"XSYMM" set has 0 nodes — check that the set survived mesh regeneration.')
    m.XsymmBC(name='BC_Sym_X', createStepName='Initial', region=region)
    print('  BC_Sym_X: XsymmBC on "XSYMM" set (%d nodes)' % len(region.nodes))

    # Symmetry plane at Y=0 (U2=UR1=UR3=0) — nodes are in the 'YSYMM' nset
    region = _get_region(a, inst, 'YSYMM')
    if region is None or len(region.nodes) == 0:
        region = _rebuild_instance_region(a, inst, 'YSYMM', 'y')
    if region is None:
        raise RuntimeError('"YSYMM" set not found on Specimen-1 — BC_Sym_Y (y=0 plane) cannot be applied.')
    if len(region.nodes) == 0:
        raise RuntimeError('"YSYMM" set has 0 nodes — check that the set survived mesh regeneration.')
    m.YsymmBC(name='BC_Sym_Y', createStepName='Initial', region=region)
    print('  BC_Sym_Y: YsymmBC on "YSYMM" set (%d nodes)' % len(region.nodes))


def _apply_edge_bc(cfg, m, a):
    """
    Optional: encastre the outer rim of the blank.
    Uses the EDGE nset from the geometry .inp.
    """
    inst = a.instances['Specimen-1']
    region = _get_region(a, inst, 'EDGE')
    if region is None or len(region.nodes) == 0:
        region = _rebuild_instance_region(a, inst, 'EDGE', 'edge')
    if region is not None and len(region.nodes) > 0:
        m.EncastreBC(name='BC_Edge',
                     createStepName='Initial',
                     region=region)
        print('  BC_Edge: ENCASTRE on Specimen-1.EDGE')
    else:
        print('  WARNING: USE_EDGE_ENCASTRE=True but EDGE set not found — skipped.')
