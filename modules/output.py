# -*- coding: utf-8 -*-
"""
modules/output.py
Field and history output requests.

Field output (100 intervals over the full step):
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
    """
    Configure field and history output requests.
    These are later replaced by _inject_output_requests in job.py,
    but must not crash for any TEST_TYPE.
    """
    print('--- Output requests ---')
    m = mdb.models[cfg.MODEL_NAME]
    test_type = getattr(cfg, 'TEST_TYPE', 'nakazima').lower()

    # First step name differs between standard and PiP
    first_step = 'Step1_Clamp' if test_type == 'pip' else 'Forming'

    # ── Delete Abaqus auto-generated default requests ─────────
    if hasattr(m, 'fieldOutputRequests'):
        for name in list(m.fieldOutputRequests.keys()):
            del m.fieldOutputRequests[name]
            print('  Deleted default field output request: %s' % name)
    if hasattr(m, 'historyOutputRequests'):
        for name in list(m.historyOutputRequests.keys()):
            del m.historyOutputRequests[name]
            print('  Deleted default history output request: %s' % name)

    # ── Field output — whole model ─────────────────────────────
    m.FieldOutputRequest(
        name='FO_Forming',
        createStepName=first_step,
        variables=('S', 'LE', 'PEEQ', 'SDV', 'U', 'RF', 'STATUS'),
        numIntervals=100)
    print('  FO_Forming: S, LE, PEEQ, SDV, U, RF, STATUS  (100 frames)'
          ' + TRIAX, SP, MISES, LEP injected post-writeInput')

    a = m.rootAssembly

    # ── History output — punch RP(s) ──────────────────────────
    if test_type == 'pip':
        _add_history_rp(cfg, m, a, 'Punch1-1', 'HO_Punch1',
                        variables=('U3', 'RF3'), step=first_step)
        _add_history_rp(cfg, m, a, 'Punch2-1', 'HO_Punch2',
                        variables=('U3', 'RF3'), step=first_step)
    else:
        _add_history_rp(cfg, m, a, 'Punch-1',  'HO_Punch',
                        variables=('U3', 'RF3'), step=first_step)

    _add_history_rp(cfg, m, a, 'Die-1',    'HO_Die',
                    variables=('RF3',), step=first_step)
    _add_history_rp(cfg, m, a, 'Matrix-1', 'HO_Matrix',
                    variables=('RF3',), step=first_step)

    # ── History output — tracked element (ELOUT) ──────────────
    _add_history_elout(cfg, m, a, step=first_step)

    # ── History output — whole-model energy (ALLKE, ALLIE) ───
    try:
        m.HistoryOutputRequest(
            name='HO_Energy',
            createStepName=first_step,
            variables=('ALLKE', 'ALLIE'),
            region=MODEL)
        print('  HO_Energy: ALLKE, ALLIE on whole model')
    except Exception as e:
        print('  WARNING HO_Energy: %s' % e)

    print('--- Output done ---')


def _add_history_rp(cfg, m, a, instance_name, request_name, variables, step='Forming'):
    """History output on the reference point of a tool instance."""
    try:
        region = a.instances[instance_name].sets['RP']
        m.HistoryOutputRequest(
            name=request_name,
            createStepName=step,
            variables=variables,
            region=region,
            sectionPoints=DEFAULT,
            rebar=EXCLUDE)
        print('  %s: %s on %s.RP' % (request_name, ', '.join(variables), instance_name))
    except Exception as e:
        print('  WARNING %s: %s' % (request_name, e))


def _add_history_elout(cfg, m, a, step='Forming'):
    """
    History output on the ELOUT element set (tracked element defined in
    the geometry .inp). Outputs stress, strain, SDVs and damage indicators.
    """
    try:
        inst   = a.instances['Specimen-1']
        region = inst.sets['ELOUT']
        m.HistoryOutputRequest(
            name='HO_ElOut',
            createStepName=step,
            variables=('S', 'LE', 'LEP', 'SDV', 'PEEQ'),
            region=region,
            sectionPoints=DEFAULT,
            rebar=EXCLUDE)
        print('  HO_ElOut: S, LE, LEP, SDV, PEEQ on Specimen-1.ELOUT')
    except Exception as e:
        print('  WARNING HO_ElOut (ELOUT set not found or inaccessible): %s' % e)
