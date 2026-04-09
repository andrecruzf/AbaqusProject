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
    Creates:
      1. Step 'Forming'  —  Dynamic, Explicit  (no mass scaling via API)
      2. Amplitude 'Amp_Punch'  —  Smooth Step  (0, 0) → (STEP_TIME, 1)

    Fixed mass scaling is injected into the .inp by job.py after writeInput().
    """
    print('--- Step creation ---')
    m = mdb.models[cfg.MODEL_NAME]

    # ── Dynamic Explicit step (no mass scaling here) ───────────
    m.ExplicitDynamicsStep(
        name='Forming',
        previous='Initial',
        timePeriod=cfg.STEP_TIME,
        improvedDtMethod=ON,
        description='Nakazima forming — punch %.1f mm' % cfg.PUNCH_DISPLACEMENT)

    print('  Step "Forming": timePeriod=%.4e s  (%.1f mm / 5.0)'
          % (cfg.STEP_TIME, cfg.PUNCH_DISPLACEMENT))
    if cfg.USE_MASS_SCALING:
        print('  Fixed mass scaling DT=%.2e s will be injected into .inp by job.py'
              % cfg.MASS_SCALING_DT)

    # ── Smooth Step amplitude ─────────────────────────────────
    m.SmoothStepAmplitude(
        name='Amp_Punch',
        timeSpan=STEP,
        data=((0.0, 0.0), (cfg.STEP_TIME, 1.0)))

    print('  Amplitude "Amp_Punch": SmoothStep (0,0)→(%.4e,1)' % cfg.STEP_TIME)
    print('--- Step done ---')
