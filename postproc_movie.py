# -*- coding: utf-8 -*-
"""
postproc_movie.py  —  Generate a SDV1 (EQPS) animation from an ODB.

Standalone:
    ODB_PATH=path/to/job.odb abaqus cae noGUI=postproc_movie.py

From pipeline (called by run_cluster.sh after solver):
    ODB_PATH=<OUTPUT_DIR>/<JOB_NAME>.odb abaqus cae noGUI=postproc_movie.py

Output:
    <odb_dir>/<job_name>_movie.webm

Supports Nakazima, Marciniak (single punch) and PiP (two punches).
Display setup is detected automatically from ODB instance names.
"""
from abaqus import *
from abaqusConstants import *
import __main__
import visualization
import displayGroupOdbToolset as dgo
import os
import subprocess
import sys

# Mirror print() to a log file (Abaqus CAE swallows stdout in noGUI mode).
_LOG_PATH = '/tmp/postproc_movie_out.txt'
try:
    _log_fh = open(_LOG_PATH, 'w')

    class _Tee(object):
        def __init__(self, a, b):
            self.a, self.b = a, b
        def write(self, s):
            self.a.write(s); self.b.write(s)
        def flush(self):
            self.a.flush(); self.b.flush()

    sys.stdout = _Tee(sys.stdout, _log_fh)
except Exception:
    pass

_BG = '#cccaca'


def _resolve_odb_path():
    env_odb = os.environ.get('ODB_PATH', '')
    if env_odb:
        return os.path.abspath(env_odb)

    env_file = os.path.join(os.getcwd(), 'last_build.env')
    if not os.path.isfile(env_file):
        return None

    job_name = subdir = ''
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith('JOB_NAME='):
                job_name = line.split('=', 1)[1].strip('"\'')
            elif line.startswith('OUTPUT_SUBDIR='):
                subdir = line.split('=', 1)[1].strip('"\'')

    if job_name and subdir:
        return os.path.join(os.getcwd(), subdir, job_name + '.odb')
    return None


def _resolve_eqps_max(odb):
    """Return a physically meaningful fixed upper bound for the EQPS color scale.

    Method B (preferred): scan frames backward to find the last frame where
    deleted elements still had SDV1 output — their EQPS there is the true
    fracture strain.  Deleted elements vanish from field output after deletion,
    so the first backward frame that contains their label is their last alive
    frame.

    Method A (fallback): global max of SDV1 in the last frame (surviving
    elements only).  Used when no deletions occurred or STATUS is absent.

    The result is rounded up to the next clean power-of-10 multiple for
    legible legend ticks.
    """
    import math as _math

    print('  Resolving EQPS max ...')
    try:
        last_step_name = odb.steps.keys()[-1]
        step = odb.steps[last_step_name]
        frames = step.frames
        n_frames = len(frames)
        print('  Step: %s   Frames: %d' % (last_step_name, n_frames))
    except Exception as e:
        print('  NOTE: cannot access frames (%s) — using auto range.' % e)
        return None

    if n_frames == 0:
        print('  NOTE: no frames in last step — using auto range.')
        return None

    # Diagnostic: list available field outputs
    try:
        fo_keys = list(frames[n_frames - 1].fieldOutputs.keys())
        print('  Field outputs in last frame: %s' % fo_keys)
    except Exception as e:
        print('  NOTE: cannot list field outputs (%s)' % e)

    eqps_max = None

    # ── Method B: backward scan for fracture EQPS of deleted elements ─────────
    try:
        last_frame = frames[n_frames - 1]
        fo_keys_last = list(last_frame.fieldOutputs.keys())
        if 'STATUS' in fo_keys_last:
            fo_status_last = last_frame.fieldOutputs['STATUS']
            deleted_labels = []
            for v in fo_status_last.values:
                if v.data < 0.5:
                    deleted_labels.append(v.elementLabel)
            deleted = frozenset(deleted_labels)
            print('  Deleted elements (STATUS=0) in last frame: %d' % len(deleted))
            if deleted:
                for i in range(n_frames - 1, -1, -1):
                    frame = frames[i]
                    try:
                        fo_sdv1 = frame.fieldOutputs['SDV1']
                    except (KeyError, Exception):
                        continue
                    found = []
                    for v in fo_sdv1.values:
                        if v.elementLabel in deleted:
                            found.append(v.data)
                    if found:
                        cur_max = found[0]
                        for x in found[1:]:
                            if x > cur_max:
                                cur_max = x
                        eqps_max = cur_max
                        print('  EQPS max: %.4f  (fracture — %d deleted elements, method B, frame %d)'
                              % (eqps_max, len(deleted), i))
                        break
        else:
            print('  STATUS not in field outputs — skipping method B')
    except Exception as e:
        print('  NOTE: method B failed (%s) — using fallback.' % e)

    # ── Method A fallback: global max of survivors in last frame ──────────────
    if not eqps_max or eqps_max < 1e-6:
        try:
            last_frame = frames[n_frames - 1]
            fo_sdv1 = last_frame.fieldOutputs['SDV1']
            cur_max = None
            for v in fo_sdv1.values:
                if cur_max is None or v.data > cur_max:
                    cur_max = v.data
            if cur_max is not None:
                eqps_max = cur_max
                print('  EQPS max: %.4f  (last-frame survivors, method A)' % eqps_max)
            else:
                print('  NOTE: SDV1 has no values in last frame — using auto range.')
                return None
        except KeyError:
            print('  NOTE: SDV1 not in last frame — using auto range.')
            return None
        except Exception as e:
            print('  NOTE: method A failed (%s) — using auto range.' % e)
            return None

    if not eqps_max or eqps_max < 1e-6:
        print('  NOTE: EQPS max is zero/tiny (%.4g) — using auto range.' % (eqps_max or 0.0))
        return None

    # Round up to the nearest clean power-of-10 multiple
    mag = 10.0 ** _math.floor(_math.log10(eqps_max))
    result = _math.ceil(eqps_max / mag) * mag
    print('  EQPS max (rounded up): %.4f' % result)
    return result


# ── Display setup — one punch (Nakazima / Marciniak) ──────────────
def _setup_single_punch():
    session.linkedViewportCommands.setValues(_highlightLinkedViewports=True)
    leaf = dgo.LeafFromConstraintNames(name=("RigidBody_DIE-1        1",
        "RigidBody_MATRIX-1        1", "RigidBody_PUNCH-1        1", ),
        type=RIGID_BODY)
    dg = session.DisplayGroup(leaf=leaf, name='Rigid Bodies')
    leaf = dgo.LeafFromSurfaceSets(surfaceSets=("SPECIMEN-1.ZMAX",
        "SPECIMEN-1.ZMIN", ))
    dg = session.DisplayGroup(leaf=leaf, name='Specimen')
    dg1= session.displayGroups['Rigid Bodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        DEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=ON, translucencyFactor=0.15)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Rigid Bodies'].setValues(
        lockOptions=ON)
    dg1= session.displayGroups['Specimen']
    dg2= session.displayGroups['Rigid Bodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, dg2, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        UNDEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        DEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        renderStyle=FILLED, visibleEdges=NONE)
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=OFF)
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.setPrimaryVariable(
        variableLabel='SDV1', outputPosition=INTEGRATION_POINT, )
    session.viewports['Viewport: 1'].odbDisplay.basicOptions.setValues(
        mirrorAboutXzPlane=True, mirrorAboutYzPlane=True)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Specimen'].setValues(
        lockOptions=ON)


# ── Display setup — two punches (PiP) ─────────────────────────────
def _setup_two_punches():
    session.linkedViewportCommands.setValues(_highlightLinkedViewports=True)
    leaf = dgo.LeafFromConstraintNames(name=("RigidBody_DIE-1        1",
        "RigidBody_MATRIX-1        1", "RigidBody_PUNCH1-1        1",
        "RigidBody_PUNCH2-1        1", ),
        type=RIGID_BODY)
    dg = session.DisplayGroup(leaf=leaf, name='Rigid Bodies')
    leaf = dgo.LeafFromSurfaceSets(surfaceSets=("SPECIMEN-1.ZMAX",
        "SPECIMEN-1.ZMIN", ))
    dg = session.DisplayGroup(leaf=leaf, name='Specimen')
    dg1= session.displayGroups['Rigid Bodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        DEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=ON, translucencyFactor=0.15)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Rigid Bodies'].setValues(
        lockOptions=ON)
    dg1= session.displayGroups['Specimen']
    dg2= session.displayGroups['Rigid Bodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, dg2, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        UNDEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        DEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        renderStyle=FILLED, visibleEdges=NONE)
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=OFF)
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.setPrimaryVariable(
        variableLabel='SDV1', outputPosition=INTEGRATION_POINT, )
    session.viewports['Viewport: 1'].odbDisplay.basicOptions.setValues(
        mirrorAboutXzPlane=True, mirrorAboutYzPlane=True)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Specimen'].setValues(
        lockOptions=ON)


def _render_animation(vp, out_file):
    """Export animation via Abaqus's built-in writeImageAnimation (TIME_HISTORY),
    then convert the AVI to webm with ffmpeg.

    Using the built-in exporter means Abaqus drives the animation controller
    internally — no manual setFrame() loop, no per-frame contour re-apply.
    Display options (contour range, camera, display groups) set on the viewport
    before this call are respected for the whole export.

    Returns ffmpeg exit code, or 0 if the AVI itself is kept as fallback.
    """
    tmp_avi = '/tmp/abaqus_movie_%d.avi' % os.getpid()

    vp.animationController.setValues(animationType=TIME_HISTORY)
    session.imageAnimationOptions.setValues(
        frameRate=10, compass=OFF, timeScale=1)
    session.writeImageAnimation(
        fileName=tmp_avi, format=AVI, canvasObjects=(vp,))
    vp.animationController.setValues(animationType=NONE)

    # Abaqus may append .avi itself — find whichever exists.
    actual_avi = tmp_avi if os.path.isfile(tmp_avi) else tmp_avi + '.avi'
    if not os.path.isfile(actual_avi):
        print('  WARNING: AVI not found at %s — skipping webm conversion.' % actual_avi)
        return 1

    cmd = [
        'ffmpeg', '-y', '-i', actual_avi,
        '-vf', 'format=yuv420p',
        '-vcodec', 'libvpx', '-crf', '10', '-b:v', '1M',
        out_file,
    ]
    ret = subprocess.call(cmd)
    try:
        os.remove(actual_avi)
    except OSError:
        pass
    return ret


def make_movie(odb_path, out_dir=None):
    odb_path = os.path.abspath(odb_path)
    if out_dir is None:
        out_dir = os.path.dirname(odb_path)

    job_name = os.path.splitext(os.path.basename(odb_path))[0]
    out_file = os.path.join(out_dir, job_name + '_movie.webm')

    print('=' * 60)
    print('  postproc_movie.py — animation export')
    print('  ODB    : %s' % odb_path)
    print('  OUT    : %s' % out_file)
    print('=' * 60)

    if not os.path.isfile(odb_path):
        print('ERROR: ODB not found: %s' % odb_path)
        return

    # ── Open ODB ──────────────────────────────────────────────
    odb = session.openOdb(name=odb_path, readOnly=True)
    vp  = session.viewports['Viewport: 1']
    vp.setValues(displayedObject=odb, width=280, height=210)
    session.printOptions.setValues(vpDecorations=OFF, vpBackground=ON)
    session.pngOptions.setValues(imageSize=(1280, 960))

    # ── Annotations ───────────────────────────────────────────
    vp.viewportAnnotationOptions.setValues(
        compass=OFF, title=OFF, state=OFF, legend=ON,
        legendFont='-*-verdana-bold-r-normal-*-*-140-*-*-p-*-*-*',
        legendNumberFormat=FIXED, legendDecimalPlaces=3)

    # ── Compute EQPS max before display setup touches contour options ─────────
    eqps_max = _resolve_eqps_max(odb)

    # ── Display setup — detect one vs two punches ──────────────
    inst_names = list(odb.rootAssembly.instances.keys())
    two_punches = any('PUNCH2' in n.upper() for n in inst_names)
    print('  Instances  : %s' % inst_names)
    print('  Two punches: %s' % two_punches)
    if two_punches:
        _setup_two_punches()
        print('  Display: PiP (two punches)')
    else:
        _setup_single_punch()
        print('  Display: single punch')

    # ── Fixed contour range — applied after display setup so setPrimaryVariable
    #    and plotState changes cannot reset it back to auto.
    #    Two separate calls (max then min) match what the Abaqus macro recorder
    #    generates; a combined call may be silently ignored in Abaqus 2023.
    #    session.defaultOdbDisplay is also set so that setFrame() cannot reset
    #    the range to the session default (which has autocompute ON). ─────────────
    _cmax = float(eqps_max) if eqps_max else 1.0
    # minValue=0.0 is a sentinel in some Abaqus builds; use 1e-9 instead.
    _cmin = 1e-9
    for _co in (vp.odbDisplay.contourOptions,):
        _co.setValues(maxAutoCompute=OFF, maxValue=_cmax,
                      minAutoCompute=OFF, minValue=_cmin)
    try:
        session.defaultOdbDisplay.contourOptions.setValues(
            maxAutoCompute=OFF, maxValue=_cmax,
            minAutoCompute=OFF, minValue=_cmin)
    except Exception as _e:
        print('  NOTE: defaultOdbDisplay contour set failed (%s)' % _e)
    if eqps_max:
        print('  Contour range: 0 — %.4f (fixed)' % eqps_max)
    else:
        print('  Contour range: 0 — 1 (no SDV1 data found)')

    # ── Camera ────────────────────────────────────────────────
    # Fit to the rigid bodies (die + blank holder) at the last frame.
    # They are always the same physical size regardless of specimen width,
    # so this gives a consistent zoom across all geometries.  The specimen
    # is hidden during fitView so its varying width doesn't affect the zoom;
    # the punch is also hidden so its initial standoff height doesn't force
    # a zoomed-out view.
    _s_keys = odb.steps.keys()
    _last_s_idx = len(_s_keys) - 1
    _last_f_idx = max(0, len(odb.steps[_s_keys[-1]].frames) - 1)
    session.graphicsOptions.setValues(backgroundColor=_BG)
    vp.view.setValues(session.views['Iso'])
    vp.odbDisplay.setFrame(step=_last_s_idx, frame=_last_f_idx)
    dg_sp = session.displayGroups['Specimen']
    dg_rb = session.displayGroups['Rigid Bodies']
    vp.odbDisplay.setValues(visibleDisplayGroups=(dg_rb,))
    vp.view.fitView()
    vp.odbDisplay.setValues(visibleDisplayGroups=(dg_sp, dg_rb))

    step_keys = odb.steps.keys()
    total = 0
    for k in step_keys:
        total += len(odb.steps[k].frames)
    print('  Steps: %d   Frames: %d' % (len(step_keys), total))
    print('  Exporting via writeImageAnimation → ffmpeg → webm ...')

    ret = _render_animation(vp, out_file)

    odb.close()

    if ret != 0:
        print('  WARNING: ffmpeg exited with code %d' % ret)
        print('  Check /tmp/postproc_movie_out.txt for render errors.')
    else:
        print('  Done -> %s' % out_file)

    print('=' * 60)


# ── Entry point ───────────────────────────────────────────────
odb_path = _resolve_odb_path()
if odb_path is None:
    print('ERROR: no ODB path found.')
    print('  Set ODB_PATH env var:')
    print('    ODB_PATH=path/to/job.odb abaqus cae noGUI=postproc_movie.py')
else:
    make_movie(odb_path)
