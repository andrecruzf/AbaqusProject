# -*- coding: utf-8 -*-
"""
modules/output.py
Field and history output requests.

Field output (50 intervals over the full step):
  S, LE, PEEQ, SDV, TRIAX, SP, MISES, U, RF, STATUS
  → matches the reference output variables including all 17 SDVs

History output:
  Punch RP : U3, RF3   (force-displacement curve for the punch)
  Die RP   : RF3       (reaction at die for clamping force monitoring)
  ELOUT    : S, LE, SDV, TRIAX, SP, MISES, PEEQ
             tracked element from the geometry .inp
"""
from abaqus import mdb
from abaqusConstants import MODEL, DEFAULT, EXCLUDE


def define_output(cfg):
    """Configure field and history output requests."""
    print('--- Output requests ---')
    m = mdb.models[cfg.MODEL_NAME]

    # ── Delete Abaqus auto-generated default requests ─────────
    # ExplicitDynamicsStep creates F-Output-1 and H-Output-1 automatically.
    # They must be removed before creating custom requests to avoid the
    # 'Model has no attribute fieldOutputRequests' error in noGUI mode.
    if hasattr(m, 'fieldOutputRequests'):
        for name in list(m.fieldOutputRequests.keys()):
            del m.fieldOutputRequests[name]
            print('  Deleted default field output request: %s' % name)
    if hasattr(m, 'historyOutputRequests'):
        for name in list(m.historyOutputRequests.keys()):
            del m.historyOutputRequests[name]
            print('  Deleted default history output request: %s' % name)

    # ── Field output — whole model ─────────────────────────────
    # Note: TRIAX, SP, MISES, LEP are valid .inp variables but rejected by the
    # CAE API. They are injected into the .inp by job.py after writeInput().
    m.FieldOutputRequest(
        name='FO_Forming',
        createStepName='Forming',
        variables=('S', 'LE', 'PEEQ', 'SDV', 'U', 'RF', 'STATUS'),
        numIntervals=50)
    print('  FO_Forming: S, LE, PEEQ, SDV, U, RF, STATUS  (50 frames)'
          ' + TRIAX, SP, MISES, LEP injected post-writeInput')

    # ── History output — punch RP ─────────────────────────────
    a = m.rootAssembly
    _add_history_rp(cfg, m, a, 'Punch-1',  'HO_Punch',
                    variables=('U3', 'RF3'))
    _add_history_rp(cfg, m, a, 'Die-1',    'HO_Die',
                    variables=('RF3',))
    _add_history_rp(cfg, m, a, 'Matrix-1', 'HO_Matrix',
                    variables=('RF3',))

    # ── History output — tracked element (ELOUT) ──────────────
    _add_history_elout(cfg, m, a)

    print('--- Output done ---')


def _add_history_rp(cfg, m, a, instance_name, request_name, variables):
    """History output on the reference point of a tool instance."""
    try:
        region = a.instances[instance_name].sets['RP']
        m.HistoryOutputRequest(
            name=request_name,
            createStepName='Forming',
            variables=variables,
            region=region,
            sectionPoints=DEFAULT,
            rebar=EXCLUDE)
        print('  %s: %s on %s.RP' % (request_name, ', '.join(variables), instance_name))
    except Exception as e:
        print('  WARNING %s: %s' % (request_name, e))


def _add_history_elout(cfg, m, a):
    """
    History output on the ELOUT element set (tracked element defined in
    the geometry .inp). Outputs stress, strain, SDVs and damage indicators.
    """
    try:
        inst   = a.instances['Specimen-1']
        # ELOUT may be an element set on the instance
        region = inst.sets['ELOUT']
        m.HistoryOutputRequest(
            name='HO_ElOut',
            createStepName='Forming',
            variables=('S', 'LE', 'LEP', 'SDV', 'PEEQ'),
            region=region,
            sectionPoints=DEFAULT,
            rebar=EXCLUDE)
        print('  HO_ElOut: S, LE, LEP, SDV, PEEQ on Specimen-1.ELOUT')
    except Exception as e:
        print('  WARNING HO_ElOut (ELOUT set not found or inaccessible): %s' % e)
