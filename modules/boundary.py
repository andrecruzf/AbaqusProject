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
from abaqusConstants import SET, XSYMM, YSYMM, ON


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

    _apply_symmetry_bcs(cfg, m, a)

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


def _apply_symmetry_bcs(cfg, m, a):
    """
    Apply XSYMM and YSYMM BCs from the node sets defined in the geometry .inp.
    Search order: instance sets → assembly sets → warning.

    IMPORTANT — nset naming convention in the geometry files:
      The .inp/.cae geometry files were created in Lennard's reference model,
      which applies a *SYSTEM/*NMAP coordinate transformation that swaps X and Y
      relative to the Python model's global axes.  After direct import (no
      transformation), the labels are therefore reversed:

        'XSYMM' nset  →  nodes at  y = 0  →  apply YsymmBC (U2=UR1=UR3=0)
        'YSYMM' nset  →  nodes at  x = 0  →  apply XsymmBC (U1=UR2=UR3=0)

      Applying the wrong BC type is silent in the CAE viewer (BCs appear) but
      causes the blank to deform without proper symmetry enforcement in the
      solver, which is exactly the failure mode reported.
    """
    inst = a.instances['Specimen-1']

    # Symmetry plane at X=0 (U1=UR2=UR3=0) — nodes are in the 'YSYMM' nset
    region = _get_region(a, inst, 'YSYMM')
    if region is not None:
        n_nodes = len(region.nodes)
        m.XsymmBC(name='BC_Sym_X', createStepName='Initial', region=region)
        print('  BC_Sym_X: XsymmBC on "YSYMM" set (x=0 nodes, %d nodes)' % n_nodes)
        if n_nodes == 0:
            print('  WARNING: BC_Sym_X region has 0 nodes — '
                  'check that YSYMM set survived mesh regeneration.')
    else:
        print('  WARNING: "YSYMM" set not found — BC_Sym_X (x=0 plane) NOT applied.')

    # Symmetry plane at Y=0 (U2=UR1=UR3=0) — nodes are in the 'XSYMM' nset
    region = _get_region(a, inst, 'XSYMM')
    if region is not None:
        n_nodes = len(region.nodes)
        m.YsymmBC(name='BC_Sym_Y', createStepName='Initial', region=region)
        print('  BC_Sym_Y: YsymmBC on "XSYMM" set (y=0 nodes, %d nodes)' % n_nodes)
        if n_nodes == 0:
            print('  WARNING: BC_Sym_Y region has 0 nodes — '
                  'check that XSYMM set survived mesh regeneration.')
    else:
        print('  WARNING: "XSYMM" set not found — BC_Sym_Y (y=0 plane) NOT applied.')


def _apply_edge_bc(cfg, m, a):
    """
    Optional: encastre the outer rim of the blank.
    Uses the EDGE nset from the geometry .inp.
    """
    inst = a.instances['Specimen-1']
    if 'EDGE' in inst.sets.keys():
        m.EncastreBC(name='BC_Edge',
                     createStepName='Initial',
                     region=inst.sets['EDGE'])
        print('  BC_Edge: ENCASTRE on Specimen-1.EDGE')
    else:
        print('  WARNING: USE_EDGE_ENCASTRE=True but EDGE set not found — skipped.')
