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
from abaqusConstants import SET, XSYMM, YSYMM


def apply_bcs(cfg):
    """Apply all boundary conditions."""
    print('--- Boundary conditions ---')
    m = mdb.models[cfg.MODEL_NAME]
    a = m.rootAssembly

    # 1. Blank holder — fixed
    m.EncastreBC(name='BC_Matrix_Fixed',
                 createStepName='Initial',
                 region=a.instances['Matrix-1'].sets['RP'])
    print('  BC_Matrix_Fixed: ENCASTRE')

    # 2. Die — fixed
    m.EncastreBC(name='BC_Die_Fixed',
                 createStepName='Initial',
                 region=a.instances['Die-1'].sets['RP'])
    print('  BC_Die_Fixed: ENCASTRE')

    # 3. Punch — driven in +Z
    _apply_punch_bc(cfg, m, a)

    # 4 & 5. Specimen symmetry planes
    _apply_symmetry_bcs(cfg, m, a)

    # 6. Outer edge (optional)
    if cfg.USE_EDGE_ENCASTRE:
        _apply_edge_bc(cfg, m, a)

    print('--- BCs done ---')


def _apply_punch_bc(cfg, m, a):
    """
    Initial step: punch fully fixed (including U3).
    Forming step: U3 = +PUNCH_DISPLACEMENT driven by Amp_Punch.
    All rotations and lateral translations remain fixed throughout.
    """
    region = a.instances['Punch-1'].sets['RP']

    # Initial — all DOFs fixed
    m.DisplacementBC(
        name='BC_Punch',
        createStepName='Initial',
        region=region,
        u1=SET, u2=SET, u3=SET,
        ur1=SET, ur2=SET, ur3=SET)

    # Forming — drive U3, keep the rest fixed
    m.boundaryConditions['BC_Punch'].setValuesInStep(
        stepName='Forming',
        u3=cfg.PUNCH_DISPLACEMENT,
        amplitude='Amp_Punch')

    print('  BC_Punch: U3 = +%.1f mm (SmoothStep Amp_Punch)' % cfg.PUNCH_DISPLACEMENT)


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
