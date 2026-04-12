# -*- coding: utf-8 -*-
"""
modules/step.py
Creates the Dynamic Explicit step and the Smooth Step amplitude.

Mass scaling:
  *Fixed Mass Scaling, TYPE=UNIFORM, DT=<DTIME> is injected directly into
  the .inp after writeInput() in job.py, because the CAE Python API does
  not support the FIXED mechanism type.

Step time:
  STEP_TIME = PUNCH_DISPLACEMENT / 5.0  (time-scaled, not real speed)
  Verify ALLKE/ALLIE < 5 % in post-processing to confirm quasi-static regime.
"""
from abaqus import mdb
from abaqusConstants import STEP, ON


def create_step(cfg):
    """
    Creates Dynamic Explicit step(s) and amplitude(s).

    Nakazima / Marciniak:
      • Step 'Forming', SmoothStep amplitude 'Amp_Punch'

    PiP (Punch-in-Punch):
      • Step 'Step1_Clamp'  — both punches advance together (linear amplitude)
      • Step 'Step2_Form'   — only Punch2 continues (linear amplitude)
      • Amplitudes: 'Amp_Step1' (0→1 over Step1), 'Amp_Step2' (0→1 over Step2)

    Fixed mass scaling is injected into the .inp by job.py after writeInput().
    """
    print('--- Step creation ---')
    m = mdb.models[cfg.MODEL_NAME]
    test_type = getattr(cfg, 'TEST_TYPE', 'nakazima').lower()

    if test_type == 'pip':
        _create_steps_pip(cfg, m)
    else:
        _create_step_standard(cfg, m)

    print('--- Step done ---')


def _create_step_standard(cfg, m):
    m.ExplicitDynamicsStep(
        name='Forming',
        previous='Initial',
        timePeriod=cfg.STEP_TIME,
        improvedDtMethod=ON,
        description='Nakazima/Marciniak forming — punch %.1f mm' % cfg.PUNCH_DISPLACEMENT)

    print('  Step "Forming": timePeriod=%.4e s  (%.1f mm / 5.0)'
          % (cfg.STEP_TIME, cfg.PUNCH_DISPLACEMENT))
    if cfg.USE_MASS_SCALING:
        print('  Fixed mass scaling DT=%.2e s will be injected into .inp by job.py'
              % cfg.MASS_SCALING_DT)

    m.SmoothStepAmplitude(
        name='Amp_Punch',
        timeSpan=STEP,
        data=((0.0, 0.0), (cfg.STEP_TIME, 1.0)))
    print('  Amplitude "Amp_Punch": SmoothStep (0,0)→(%.4e,1)' % cfg.STEP_TIME)


def _create_steps_pip(cfg, m):
    t1 = cfg.PIP_STEP1_TIME
    t2 = cfg.PIP_STEP2_TIME

    m.ExplicitDynamicsStep(
        name='Step1_Clamp',
        previous='Initial',
        timePeriod=t1,
        improvedDtMethod=ON,
        description='PiP Step1 — Punch1+Punch2 advance %.1f mm' % cfg.PIP_PUNCH1_DISPLACEMENT)

    m.ExplicitDynamicsStep(
        name='Step2_Form',
        previous='Step1_Clamp',
        timePeriod=t2,
        improvedDtMethod=ON,
        description='PiP Step2 — Punch2 only, additional %.1f mm' % cfg.PIP_PUNCH2_DISPLACEMENT)

    print('  Step "Step1_Clamp": timePeriod=%.1f s' % t1)
    print('  Step "Step2_Form" : timePeriod=%.1f s' % t2)
    if cfg.USE_MASS_SCALING:
        print('  Fixed mass scaling DT=%.2e s will be injected into .inp by job.py'
              % cfg.MASS_SCALING_DT)

    # Linear (tabular) amplitudes — matches PinP_CR210H reference
    m.TabularAmplitude(
        name='Amp_Step1',
        timeSpan=STEP,
        smooth=0.0,
        data=((0.0, 0.0), (t1, 1.0)))
    m.TabularAmplitude(
        name='Amp_Step2',
        timeSpan=STEP,
        smooth=0.0,
        data=((0.0, 0.0), (t2, 1.0)))
    print('  Amplitude "Amp_Step1": linear (0,0)→(%.1f,1)' % t1)
    print('  Amplitude "Amp_Step2": linear (0,0)→(%.1f,1)' % t2)
