# -*- coding: utf-8 -*-
from abaqus import mdb
from abaqusConstants import ANALYSIS, PERCENTAGE, OFF, SINGLE
import os
import math


def save_and_export(cfg):
    import shutil
    m = mdb.models[cfg.MODEL_NAME]
    out_dir = getattr(cfg, 'OUTPUT_DIR', cfg.JOB_NAME)

    j = mdb.Job(
        name=cfg.JOB_NAME,
        model=cfg.MODEL_NAME,
        description='Nakazima — W%d — t=%.2f mm'
                    % (cfg.SPECIMEN_WIDTH, cfg.BLANK_THICKNESS),
        type=ANALYSIS,
        numCpus=cfg.NUM_CPUS,
        numDomains=cfg.NUM_CPUS,
        numGPUs=0,
        memoryUnits=PERCENTAGE,
        memory=90,
        explicitPrecision=SINGLE,
        nodalOutputPrecision=SINGLE)

    # Write .inp to CWD (Abaqus always writes here), then inject and move
    j.writeInput(consistencyChecking=OFF)
    inp_file = cfg.JOB_NAME + '.inp'

    if getattr(cfg, 'USE_MASS_SCALING', False):
        _inject_mass_scaling(inp_file, cfg.MASS_SCALING_DT)
    _inject_output_requests(inp_file)
    _inject_initial_conditions(inp_file, cfg)

    # Move .inp into output directory
    shutil.move(inp_file, os.path.join(out_dir, inp_file))
    print('  Moved %s → %s/' % (inp_file, out_dir))

    # Save .cae directly into output directory
    mdb.saveAs(pathName=os.path.join(out_dir, cfg.CAE_NAME))
    print('  Saved %s → %s/' % (cfg.CAE_NAME, out_dir))

    # Copy VUMAT into output directory so the cluster job is self-contained
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vumat_src = os.path.join(project_root, cfg.VUMAT_PATH)
    if os.path.isfile(vumat_src):
        shutil.copy2(vumat_src, os.path.join(out_dir, os.path.basename(cfg.VUMAT_PATH)))
        print('  Copied %s → %s/' % (os.path.basename(cfg.VUMAT_PATH), out_dir))
    else:
        print('  WARNING: VUMAT not found at %s — copy it manually.' % vumat_src)

    _write_build_env(cfg.JOB_NAME, out_dir)
    _update_cluster_script(cfg.JOB_NAME, out_dir)


def _write_build_env(job_name, out_dir):
    """Write last_build.env so run_cluster.sh can source it after the build step."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(project_root, 'last_build.env')
    with open(env_file, 'w') as f:
        f.write('JOB_NAME="%s"\n' % job_name)
        f.write('OUTPUT_SUBDIR="%s"\n' % os.path.basename(out_dir))
    print('  Written last_build.env (JOB_NAME=%s)' % job_name)


def _update_cluster_script(job_name, out_dir):
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'run_cluster.sh')
    if not os.path.isfile(script):
        return
    import re
    with open(script, 'r') as f:
        content = f.read()
    content = re.sub(r'^JOB_NAME=.*$',      'JOB_NAME="%s"' % job_name,                  content, flags=re.MULTILINE)
    content = re.sub(r'^OUTPUT_SUBDIR=.*$', 'OUTPUT_SUBDIR="%s"' % os.path.basename(out_dir), content, flags=re.MULTILINE)
    with open(script, 'w') as f:
        f.write(content)
    print('  Updated run_cluster.sh: JOB_NAME=%s, OUTPUT_SUBDIR=%s' % (job_name, os.path.basename(out_dir)))


def _inject_output_requests(inp_file):
    """
    Replace the default Abaqus output section (PRESELECT) with custom requests:
      Field : S, LE, PEEQ, SDV, STATUS, TRIAX, SP, MISES, LEP — 50 intervals
      History: U3/RF3 on Punch RP, RF3 on Die/Matrix RPs
    Replaces everything between '** OUTPUT REQUESTS' and '*End Step'.
    """
    custom_output = (
        '** OUTPUT REQUESTS\n'
        '** \n'
        '*Restart, write, number interval=1, time marks=NO\n'
        '** \n'
        '** FIELD OUTPUT: FO_Forming\n'
        '** \n'
        '*Output, field, number interval=50\n'
        '*Element Output, directions=YES\n'
        'S, LE, PEEQ, SDV, STATUS, TRIAX, SP, MISES, LEP\n'
        '*Node Output\n'
        'U, RF\n'
        '** \n'
        '** HISTORY OUTPUT: HO_Tools\n'
        '** \n'
        '*Output, history\n'
        '*Node Output, nset=Punch-1.RP\n'
        'U3, RF3\n'
        '*Node Output, nset=Die-1.RP\n'
        'RF3\n'
        '*Node Output, nset=Matrix-1.RP\n'
        'RF3\n'
        '*End Step\n'
    )

    with open(inp_file, 'r') as f:
        content = f.read()

    # Find the output section start and replace to *End Step
    marker = '** OUTPUT REQUESTS'
    start = content.find(marker)
    if start == -1:
        print('  WARNING _inject_output_requests: "** OUTPUT REQUESTS" not found — '
              'output NOT replaced.')
        return

    end = content.find('*End Step', start)
    if end == -1:
        print('  WARNING _inject_output_requests: "*End Step" not found — '
              'output NOT replaced.')
        return

    # end points to '*End Step'; advance past it
    end += len('*End Step')

    content = content[:start] + custom_output + content[end:]

    with open(inp_file, 'w') as f:
        f.write(content)

    print('  Injected custom output requests (50 intervals, SDV, TRIAX, SP, MISES, LEP)')


def _inject_extra_output_vars(inp_file):
    extra = ', TRIAX, SP, MISES, LEP'
    with open(inp_file, 'r') as f:
        lines = f.readlines()
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        if line.strip().lower().startswith('*element output'):
            i += 1
            if i < len(lines):
                new_lines.append(lines[i].rstrip() + extra + '\n')
                i += 1
                continue
        i += 1
    with open(inp_file, 'w') as f:
        f.writelines(new_lines)


def _inject_mass_scaling(inp_file, dt):
    with open(inp_file, 'r') as f:
        lines = f.readlines()
    new_lines = []
    i = 0
    while i < len(lines):
        new_lines.append(lines[i])
        if lines[i].strip().startswith('*Dynamic') and 'Explicit' in lines[i]:
            # Must append the time-period data line first, then inject
            i += 1
            if i < len(lines):
                new_lines.append(lines[i])   # ", <time_period>" data line
            new_lines.append('*Fixed Mass Scaling, TYPE=UNIFORM, DT=%g\n' % dt)
        i += 1
    with open(inp_file, 'w') as f:
        f.writelines(new_lines)


def _compute_eqpsf0_hc(props):
    """
    Compute the initial failure strain EQPSf at TRIAX=0, LODE=0 using the
    Hosford-Coulomb (HC) criterion — PROPS(33-36): a, b, c, n.
    This gives a non-zero SDV17 seed so the Newton denominator never hits 0/0.
    """
    a = props[32]   # PROPS(33)
    b = props[33]   # PROPS(34)
    c = props[34]   # PROPS(35)
    n = props[35]   # PROPS(36)
    PI = math.acos(-1.0)
    # Lode-angle-dependent stress state functions at LODE=0
    f1 =  (2.0/3.0) * math.cos((PI / 6.0))   # = sqrt(3)/3
    f2 =  (2.0/3.0) * math.cos((PI / 2.0))   # = 0
    f3 = -(2.0/3.0) * math.cos((PI / 6.0))   # = -sqrt(3)/3
    # Hosford effective stress at TRIAX=0, LODE=0
    inner = (0.5 * (abs(f1 - f2)**a +
                    abs(f2 - f3)**a +
                    abs(f1 - f3)**a))**(1.0 / a)
    # HC failure locus: EQPSf = b*(1+c)^(1/n) * (inner + c*(2*TRIAX+f1+f3))^(-1/n)
    # At TRIAX=0: 2*TRIAX + f1 + f3 = 0  →  bracket = inner
    bracket = inner   # + c*(0 + f1 + f3) = inner + 0
    EQPSf0 = b * (1.0 + c)**(1.0 / n) * bracket**(-1.0 / n)
    return EQPSf0


def _inject_initial_conditions(inp_file, cfg):
    """
    Inject *Initial Conditions, type=SOLUTION before *Step.

    Bypasses the VUMAT stateOld/stateNew initialisation bug (Abaqus 2023):
    the VUMAT init block writes to stateOld (read-only in Abaqus 2023), so
    SDV8 (Beta softening) arrives at increment 1 as 0 instead of 1, driving
    the yield stress to zero and forcing every element into plasticity.
    SDV17 (EQPSf) also arrives as 0, causing Hbeta*(1/EQPSf) = 0*(1/0) = NaN
    in the Newton denominator.

    Initial SDV values:
      SDV 8  (Beta)   = 1.0        — undamaged softening variable
      SDV 10 (T)      = T0         — initial temperature [PROPS(28)]
      SDV 11 (EQPSdot)= Eps0       — reference strain rate [PROPS(25)]
      SDV 12 (ySRH)   = 1.0        — SRH factor (C=0 → no rate hardening)
      SDV 13 (yTS)    = 1.0        — thermal softening (T=Tr → no softening)
      SDV 14 (fSR)    = 1.0        — failure SRH factor (D4=0)
      SDV 15 (fTS)    = 1.0        — failure TS factor (D5=0)
      SDV 17 (EQPSf)  = HC(0,0)   — failure strain at TRIAX=0, LODE=0
    """
    props = cfg.VUMAT_CONSTANTS
    T0   = props[27]   # PROPS(28) — initial temperature
    Eps0 = props[24]   # PROPS(25) — reference strain rate

    # EQPSf initial value — use HC criterion (FAILflag=2 or 3)
    fail_flag = props[39]   # PROPS(40)
    if abs(fail_flag - 2.0) < 0.1 or abs(fail_flag - 3.0) < 0.1:
        eqpsf0 = _compute_eqpsf0_hc(props)
    else:
        eqpsf0 = 1.0   # safe non-zero default for CL / JCX modes

    # All 17 SDVs in order
    sdv = [
        0.0,     # 1  EQPS
        0.0,     # 2  Seq
        0.0,     # 3  Qeq
        0.0,     # 4  TRIAX
        0.0,     # 5  LODE
        0.0,     # 6  D
        0.0,     # 7  FAIL
        1.0,     # 8  Beta     ← must be 1 (undamaged)
        0.0,     # 9  eeV
        T0,      # 10 T
        Eps0,    # 11 EQPSdot
        1.0,     # 12 ySRH
        1.0,     # 13 yTS
        1.0,     # 14 fSR
        1.0,     # 15 fTS
        0.0,     # 16 Wcl
        eqpsf0,  # 17 EQPSf   ← must be non-zero
    ]

    # In the CAE-generated .inp, the specimen instance is always 'SPECIMEN-1'
    elset = 'SPECIMEN-1.ELALL'

    # Abaqus allows max 8 data items per line.
    # First line: elset name + first 7 SDV values (= 8 items total).
    # Continuation lines: up to 8 SDV values each (no set name repeated).
    chunks = []
    chunks.append('%s, %s' % (elset, ', '.join('%g' % v for v in sdv[:7])))
    remaining = sdv[7:]
    while remaining:
        batch = remaining[:8]
        remaining = remaining[8:]
        chunks.append(', '.join('%g' % v for v in batch))

    ic_block = (
        '** Initial SDV values — injected by job.py (Abaqus 2023 VUMAT fix)\n'
        '*Initial Conditions, type=SOLUTION\n'
        + '\n'.join(chunks) + '\n'
    )

    with open(inp_file, 'r') as f:
        lines = f.readlines()

    insert_at = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith('*step'):
            insert_at = i
            break

    if insert_at is None:
        print('  WARNING _inject_initial_conditions: *Step not found — '
              'initial conditions NOT injected.')
        return

    lines.insert(insert_at, ic_block)
    with open(inp_file, 'w') as f:
        f.writelines(lines)

    print('  Injected *Initial Conditions (17 SDVs) for %s' % elset)
    print('    SDV8(Beta)=1.0  SDV17(EQPSf)=%.4g  T0=%.1f  Eps0=%.2e'
          % (eqpsf0, T0, Eps0))