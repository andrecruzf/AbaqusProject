# -*- coding: utf-8 -*-
"""
modules/material.py
Defines the user material (VUMAT) and assigns the solid section.

Material:
  *User Material, constants=46  (Hosford-Coulomb via VUMAT_explicit.f)
  *Depvar, DELETE=7  →  17 state-dependent variables
  *Density

Section:
  *Section Controls → HOURGLASS=RELAX STIFFNESS, ELEMENT DELETION=YES
  *Solid Section    → applied to specimen elset ELALL

IMPORTANT:
- VUMAT must be linked at job submission:
  abaqus job=... user=VUMAT_explicit.f interactive
"""

from abaqus import mdb
from abaqusConstants import (
    CARTESIAN, AXIS_1, STACK_3, DISCRETE,
    RELAX_STIFFNESS, ON, FROM_SECTION
)
import math


def define_material(cfg):
    print('--- Material definition ---')
    m = mdb.models[cfg.MODEL_NAME]

    # ── User material ────────────────────────────────────────
    mat = m.Material(name=cfg.MATERIAL_NAME)
    mat.UserMaterial(mechanicalConstants=cfg.VUMAT_CONSTANTS)
    mat.Depvar(n=cfg.DEPVAR_COUNT, deleteVar=cfg.DEPVAR_DELETE)
    mat.Density(table=((7.85e-9,),))

    print('  UserMaterial "%s" created' % cfg.MATERIAL_NAME)

    # ── Section controls ──────────────────────────────────────
    try:
        m.SectionControls(
            name='SOLID_CONTROLS',
            hourglass=RELAX_STIFFNESS,
            elementDeletion=ON)
        print('  SectionControls created')
    except Exception as e:
        print('  WARNING SectionControls: %s' % e)

    # ── Solid section ────────────────────────────────────────
    section_name = 'BlankSection'

    try:
        m.HomogeneousSolidSection(
            name=section_name,
            material=cfg.MATERIAL_NAME,
            thickness=None,
            controlName='SOLID_CONTROLS')
    except TypeError:
        m.HomogeneousSolidSection(
            name=section_name,
            material=cfg.MATERIAL_NAME,
            thickness=None)

    print('  SolidSection "%s" created' % section_name)

    # ── Assign to specimen ONLY ──────────────────────────────
    spec_name = cfg.SPECIMEN_PART_NAME
    p = m.parts[spec_name]

    # Rebuild ELALL safely every run
    if 'ELALL' in p.sets.keys():
        del p.sets['ELALL']

    p.Set(name='ELALL', elements=p.elements[:])
    region = p.sets['ELALL']

    p.SectionAssignment(
        region=region,
        sectionName=section_name,
        offset=0.0,
        thicknessAssignment=FROM_SECTION
    )

    print('  Section assigned to specimen: %s' % spec_name)

    # ── Material orientation ──────────────────────────────────
    _apply_orientation(cfg, p, region)

    print('--- Material definition complete ---')


def _apply_orientation(cfg, part, region):
    angle = cfg.MATERIAL_ORIENTATION_ANGLE
    a = math.radians(angle)

    rd = (math.cos(a), math.sin(a), 0.0)
    td = (-math.sin(a), math.cos(a), 0.0)

    try:
        csys = part.DatumCsysByThreePoints(
            origin=(0.0, 0.0, 0.0),
            point1=rd,
            point2=td,
            name='MaterialOrient',
            coordSysType=CARTESIAN)

        datum = part.datums[csys.id]

        part.MaterialOrientation(
            region=region,
            localCsys=datum,
            axis=AXIS_1,
            angle=0.0,
            stackDirection=STACK_3,
            orientationType=DISCRETE)

        print('  Material orientation applied')

    except Exception as e:
        print('  WARNING orientation failed: %s' % e)