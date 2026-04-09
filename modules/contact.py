# -*- coding: utf-8 -*-
"""
modules/contact.py
Defines contact properties and surface-to-surface kinematic contact pairs.

Matches the reference model (nakazima.inp):
  *Contact Pair, mechanical constraint=KINEMATIC

Three pairs (main = rigid tool, secondary = deformable blank):
  CP_Punch  : Punch-1.Outer  <-> Specimen-1.ZMIN   mu = FR_PUNCH
  CP_Die    : Die-1.Outer    <-> Specimen-1.ZMAX   mu = FR_CLAMP
  CP_Matrix : Matrix-1.Outer <-> Specimen-1.ZMIN   mu = FR_CLAMP

Note on surface availability:
  Element-based surfaces (type=ELEMENT) imported from the geometry .inp are
  stored on the part, but are NOT automatically propagated to the assembly
  instance in Abaqus 2023 CAE. _get_specimen_surface() creates them at the
  assembly level on demand from the part's internal elsets (_ZMIN_S2, _ZMAX_S1).
"""
from abaqus import mdb
from abaqusConstants import (
    PENALTY, ISOTROPIC, HARD, ON, OFF,
    FRACTION, DEFAULT, FINITE
)


def _make_friction_prop(model, name, mu):
    """Contact property: Coulomb friction + hard normal contact."""
    model.ContactProperty(name)
    prop = model.interactionProperties[name]
    prop.TangentialBehavior(
        formulation=PENALTY,
        directionality=ISOTROPIC,
        slipRateDependency=OFF,
        pressureDependency=OFF,
        temperatureDependency=OFF,
        dependencies=0,
        table=((mu,),),
        shearStressLimit=None,
        maximumElasticSlip=FRACTION,
        fraction=0.005,
        elasticSlipStiffness=None)
    prop.NormalBehavior(
        pressureOverclosure=HARD,
        allowSeparation=ON,
        constraintEnforcementMethod=DEFAULT)
    return prop


def _get_specimen_surface(a, m, inst_name, surf_name):
    """
    Return an assembly surface from the specimen instance.
    Surfaces must be accessed at assembly level for contact.
    """
    inst = a.instances[inst_name]

    if surf_name not in inst.surfaces.keys():
        raise RuntimeError(
            'Surface "%s" not found on instance "%s".\n'
            'Available instance surfaces: %s'
            % (surf_name, inst_name, list(inst.surfaces.keys()))
        )

    return inst.surfaces[surf_name]




def _make_contact_pair(model, name, step_name, main_surf, secondary_surf, prop_name):
    """Surface-to-surface kinematic contact pair — Abaqus 2023.

    Abaqus 2022+ API:
      - Surface keywords: main / secondary  (master/slave removed in 2022)
      - mechanicalConstraintFormulation removed (KINEMATIC is implicit for
        Explicit surface-to-surface contact and cannot be overridden)
    """
    model.SurfaceToSurfaceContactExp(
        name=name,
        createStepName=step_name,
        main=main_surf,
        secondary=secondary_surf,
        sliding=FINITE,
        interactionProperty=prop_name)


def define_contact(cfg):
    """
    1. Create two friction contact properties (punch / clamp).
    2. Create three kinematic contact pairs matching the reference model.
    """
    print('--- Contact definition ---')
    m = mdb.models[cfg.MODEL_NAME]
    a = m.rootAssembly

    # ── Contact properties ────────────────────────────────────
    _make_friction_prop(m, 'IntPropPunch', cfg.FR_PUNCH)
    _make_friction_prop(m, 'IntPropClamp', cfg.FR_CLAMP)
    print('  IntPropPunch: mu=%.2f  (punch / blank)' % cfg.FR_PUNCH)
    print('  IntPropClamp: mu=%.2f  (die and blank-holder / blank)' % cfg.FR_CLAMP)

    # ── Tool surfaces (always on instance — created in parts.py) ──
    punch_outer  = a.instances['Punch-1'].surfaces['Outer']
    die_outer    = a.instances['Die-1'].surfaces['Outer']
    matrix_outer = a.instances['Matrix-1'].surfaces['Outer']

    # ── Specimen surfaces (with fallback creation) ────────────
    blank_zmin = _get_specimen_surface(a, m, 'Specimen-1', 'ZMIN')
    blank_zmax = _get_specimen_surface(a, m, 'Specimen-1', 'ZMAX')

    # ── Kinematic contact pairs ───────────────────────────────
    _make_contact_pair(m, 'CP_Punch',  'Forming',
                       punch_outer,  blank_zmin, 'IntPropPunch')
    _make_contact_pair(m, 'CP_Die',    'Forming',
                       die_outer,    blank_zmax, 'IntPropClamp')
    _make_contact_pair(m, 'CP_Matrix', 'Forming',
                       matrix_outer, blank_zmin, 'IntPropClamp')

    print('  CP_Punch  : Punch-1.Outer  <-> Specimen-1.ZMIN  (kinematic, mu=%.2f)'
          % cfg.FR_PUNCH)
    print('  CP_Die    : Die-1.Outer    <-> Specimen-1.ZMAX  (kinematic, mu=%.2f)'
          % cfg.FR_CLAMP)
    print('  CP_Matrix : Matrix-1.Outer <-> Specimen-1.ZMIN  (kinematic, mu=%.2f)'
          % cfg.FR_CLAMP)
    print('--- Contact done ---')