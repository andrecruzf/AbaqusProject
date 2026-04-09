# -*- coding: utf-8 -*-
"""
modules/material.py
Defines the user material (VUMAT) and assigns the solid section.

Material:
  *User Material, constants=46  (Hosford-Coulomb via VUMAT_explicit.f)
  *Depvar, DELETE=7  →  17 state-dependent variables (EQPS, damage, …)
  *Density

Section:
  *Section Controls  →  HOURGLASS=RELAX STIFFNESS, ELEMENT DELETION=YES
  *Solid Section     →  applied to elset ELALL with material orientation

The VUMAT must be linked at submission time:
  abaqus job=Nakazima_Job user=../Engin_Input_Files/VUMAT_explicit.f interactive
"""
from abaqus import mdb
from abaqusConstants import (
    CARTESIAN, AXIS_1, STACK_3, DISCRETE,
    RELAX_STIFFNESS, ON, OFF
)
import math


_TOOL_NAMES = {'Matrix', 'Die', 'Punch'}


def _get_specimen_name(cfg):
    if cfg.SPECIMEN_PART_NAME:
        return cfg.SPECIMEN_PART_NAME
    candidates = [n for n in mdb.models[cfg.MODEL_NAME].parts.keys()
                  if n not in _TOOL_NAMES]
    if not candidates:
        raise RuntimeError('No specimen part found.')
    return candidates[0]


def define_material(cfg):
    """
    1. Create the VUMAT user material with 46 constants + 17 SDVs.
    2. Create SectionControls (hourglass + element deletion).
    3. Create a HomogeneousSolidSection and assign it to the specimen.
    4. Apply material orientation (rolling direction angle).
    """
    print('--- Material definition ---')
    m = mdb.models[cfg.MODEL_NAME]

    # ── User material ──────────────────────────────────────────
    mat = m.Material(name=cfg.MATERIAL_NAME)
    mat.UserMaterial(mechanicalConstants=cfg.VUMAT_CONSTANTS)
    mat.Depvar(n=cfg.DEPVAR_COUNT, deleteVar=cfg.DEPVAR_DELETE)
    mat.Density(table=((7.85e-9,),))

    print('  UserMaterial "%s": 46 constants, %d SDVs (delete on SDV%d)'
          % (cfg.MATERIAL_NAME, cfg.DEPVAR_COUNT, cfg.DEPVAR_DELETE))
    print('  VUMAT source: %s' % cfg.VUMAT_PATH)
    print('  >> Submit with: abaqus job=%s user=%s interactive'
          % (cfg.JOB_NAME, cfg.VUMAT_PATH))

    # ── Section controls ──────────────────────────────────────
    # Hourglass stabilisation + element deletion when SDV7 = 1
    try:
        m.SectionControls(
            name='SOLID_CONTROLS',
            hourglass=RELAX_STIFFNESS,
            elementDeletion=ON)
        print('  SectionControls "SOLID_CONTROLS": hourglass=RELAX_STIFFNESS, deletion=ON')
    except Exception as e:
        print('  WARNING SectionControls: %s' % e)

    # ── Solid section ─────────────────────────────────────────
    section_name = 'BlankSection'
    try:
        m.HomogeneousSolidSection(
            name=section_name,
            material=cfg.MATERIAL_NAME,
            thickness=None,
            controlName='SOLID_CONTROLS')
    except TypeError:
        # Older Abaqus versions may not accept controlName
        m.HomogeneousSolidSection(
            name=section_name,
            material=cfg.MATERIAL_NAME,
            thickness=None)
        print('  NOTE: controlName not supported — add CONTROLS=SOLID_CONTROLS '
              'to *Solid Section in the .inp manually if needed.')

    print('  HomogeneousSolidSection "%s": material=%s'
          % (section_name, cfg.MATERIAL_NAME))

    # ── Assign section to specimen ────────────────────────────
    spec_name = _get_specimen_name(cfg)
    p = m.parts[spec_name]

    # Use the ELALL elset from the imported .inp, or create one
    if 'ELALL' in p.sets.keys():
        region = p.sets['ELALL']
    else:
        p.Set(name='ELALL', elements=p.elements[:])
        region = p.sets['ELALL']

    p.SectionAssignment(region=region, sectionName=section_name)
    print('  Section assigned to "%s" (elset ELALL)' % spec_name)

    # ── Material orientation ──────────────────────────────────
    _apply_orientation(cfg, p, region)

    print('--- Material done ---')


def _apply_orientation(cfg, part, region):
    """
    Creates a local CSYS aligned with the rolling direction and applies
    it as a material orientation on the solid section.

    Rolling direction angle is measured from the global X-axis:
      0°  → RD along X  (default)
      90° → RD along Y
    """
    angle = cfg.MATERIAL_ORIENTATION_ANGLE
    a_rad = math.radians(angle)
    c, s  = math.cos(a_rad), math.sin(a_rad)

    # Two points that define RD (point1 on local X = RD) and TD (point2)
    rd_point = (c, s, 0.0)
    td_point = (-s, c, 0.0)

    try:
        csys = part.DatumCsysByThreePoints(
            origin=(0.0, 0.0, 0.0),
            point1=rd_point,
            point2=td_point,
            name='MaterialOrient',
            coordSysType=CARTESIAN)
        datum_csys = part.datums[csys.id]

        part.MaterialOrientation(
            region=region,
            localCsys=datum_csys,
            axis=AXIS_1,
            angle=0.0,
            stackDirection=STACK_3,
            orientationType=DISCRETE)

        print('  Material orientation: RD at %.1f° from X-axis' % angle)

    except Exception as e:
        print('  WARNING MaterialOrientation: %s' % e)
        print('  >> Apply orientation manually in CAE '
              '(Module: Property → Assign Material Orientation).')
