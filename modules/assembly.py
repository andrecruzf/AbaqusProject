# -*- coding: utf-8 -*-
"""
modules/assembly.py
Instantiates all parts and orients the rigid tools.

Coordinate convention:
  Blank lies in the XY plane (z=0 to z=t) — imported directly from .inp.
  All rigid body parts are sketched with Y as the local revolution axis.
  Each tool instance is rotated +90° around the global X-axis so that:
    local Y  →  global Z  (forming / punch direction)
    local Z  →  global -Y
    local X  →  global X  (unchanged)

After rotation:
  Punch tip at global z=0 (blank bottom), moves in +Z.
  Die contact face at global z=t (blank top / ZMAX).
  Blank holder contact face at global z=0 (blank bottom / ZMIN).
"""
from abaqus import mdb
from abaqusConstants import CARTESIAN, ON, OFF


_TOOL_NAMES = {'Matrix', 'Die', 'Punch', 'Punch1', 'Punch2'}


def _get_specimen_name(cfg):
    """Return the name of the specimen part (auto-detect if not specified)."""
    if cfg.SPECIMEN_PART_NAME is not None:
        return cfg.SPECIMEN_PART_NAME

    candidates = [name for name in mdb.models[cfg.MODEL_NAME].parts.keys()
                  if name not in _TOOL_NAMES]
    if not candidates:
        raise RuntimeError('No specimen part found in the model.')
    for preferred in ('Specimen', 'Sample_Circ', 'Blank_Var'):
        if preferred in candidates:
            return preferred
    return candidates[0]


def create_assembly(cfg):
    """
    1. Instantiate all parts (tools + specimen).
    2. Rotate each tool instance +90° around X so forming direction = Z.
    3. Position tools for initial contact.
    4. Verify symmetry sets on the specimen.
    """
    print('--- Assembly ---')
    m = mdb.models[cfg.MODEL_NAME]
    a = m.rootAssembly
    a.DatumCsysByDefault(CARTESIAN)

    spec_name = _get_specimen_name(cfg)
    test_type = getattr(cfg, 'TEST_TYPE', 'nakazima').lower()

    if test_type == 'pip':
        _create_assembly_pip(cfg, m, a, spec_name)
    else:
        _create_assembly_standard(cfg, m, a, spec_name)

    _setup_symmetry_sets(cfg, a, spec_name)
    print('--- Assembly done ---')


def _create_assembly_standard(cfg, m, a, spec_name):
    """Nakazima / Marciniak: single punch."""
    instances = {
        'Punch-1':    'Punch',
        'Die-1':      'Die',
        'Matrix-1':   'Matrix',
        'Specimen-1': spec_name,
    }
    for inst_name, part_name in instances.items():
        a.Instance(name=inst_name, part=m.parts[part_name], dependent=ON)
        print('  Instanced: %s  ←  %s' % (inst_name, part_name))

    for tool_inst in ('Punch-1', 'Die-1', 'Matrix-1'):
        a.instances[tool_inst].rotateAboutAxis(
            axisPoint=(0.0, 0.0, 0.0),
            axisDirection=(1.0, 0.0, 0.0),
            angle=90.0)
        print('  Rotated +90° around X: %s' % tool_inst)

    a.instances['Punch-1'].translate(vector=(0.0, 0.0, -0.01))
    print('  Punch-1 translated -0.01 mm in Z (initial gap)')


def _create_assembly_pip(cfg, m, a, spec_name):
    """
    PiP: two punches.
    After +90° rotation (local Y → global Z):
      • Punch1 bore face lands at z=0 — the annular punch sits on blank bottom.
      • Punch2 hemisphere tip at z=0 — same as Nakazima punch.
    Both are given a -0.01 mm gap to avoid initial contact activation.
    """
    instances = {
        'Punch1-1':   'Punch1',
        'Punch2-1':   'Punch2',
        'Die-1':      'Die',
        'Matrix-1':   'Matrix',
        'Specimen-1': spec_name,
    }
    for inst_name, part_name in instances.items():
        a.Instance(name=inst_name, part=m.parts[part_name], dependent=ON)
        print('  Instanced: %s  ←  %s' % (inst_name, part_name))

    for tool_inst in ('Punch1-1', 'Punch2-1', 'Die-1', 'Matrix-1'):
        a.instances[tool_inst].rotateAboutAxis(
            axisPoint=(0.0, 0.0, 0.0),
            axisDirection=(1.0, 0.0, 0.0),
            angle=90.0)
        print('  Rotated +90° around X: %s' % tool_inst)

    a.instances['Punch1-1'].translate(vector=(0.0, 0.0, -0.01))
    a.instances['Punch2-1'].translate(vector=(0.0, 0.0, -0.01))
    print('  Punch1-1 and Punch2-1 translated -0.01 mm in Z (initial gap)')


def _setup_symmetry_sets(cfg, assembly, spec_name):
    """
    Verify that XSYMM and YSYMM nsets are present on the instanced specimen.
    With .cae import the sets propagate directly to inst.sets.

    NOTE — naming convention in the geometry files (W20/W50/W80/W100/W120/W200):
      'XSYMM' nset contains nodes at y=0  (apply YsymmBC)
      'YSYMM' nset contains nodes at x=0  (apply XsymmBC)
    The names are swapped relative to Abaqus global axes because the source
    files used a *SYSTEM/*NMAP rotation that is not reproduced here.
    boundary.py handles this correctly.
    """
    inst = assembly.instances['Specimen-1']

    for set_name in ('XSYMM', 'YSYMM'):
        if set_name in inst.sets.keys():
            region = inst.sets[set_name]
            nodes = list(region.nodes)
            n_nodes = len(nodes)
            if n_nodes > 0:
                # Sample first node to confirm coordinate plane
                sample = nodes[0]
                print('  Set "%s": %d nodes — sample node coords (%.3f, %.3f, %.3f)'
                      % (set_name, n_nodes,
                         sample.coordinates[0],
                         sample.coordinates[1],
                         sample.coordinates[2]))
            else:
                print('  WARNING: set "%s" found but has 0 nodes — '
                      'mesh regeneration may have cleared it.' % set_name)
        else:
            print('  WARNING: set "%s" not found on Specimen-1 — '
                  'apply symmetry BC manually in CAE.' % set_name)
