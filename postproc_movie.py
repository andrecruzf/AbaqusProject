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

_BG = '#F2F2F2'


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
    vp = session.viewports['Viewport: 1']
    session.linkedViewportCommands.setValues(_highlightLinkedViewports=True)

    leaf = dgo.LeafFromConstraintNames(name=(
        "RigidBody_DIE-1        1",
        "RigidBody_MATRIX-1        1",
        "RigidBody_PUNCH-1        1",
    ), type=RIGID_BODY)
    session.DisplayGroup(leaf=leaf, name='Rigid Bodies')

    leaf = dgo.LeafFromSurfaceSets(surfaceSets=(
        "SPECIMEN-1.ZMAX", "SPECIMEN-1.ZMIN",
    ))
    session.DisplayGroup(leaf=leaf, name='Specimen')

    dg_rb = session.displayGroups['Rigid Bodies']
    dg_sp = session.displayGroups['Specimen']

    # Rigid bodies: must set DEFORMED *before* locking — lockOptions freezes
    # whatever plotState is active at lock time. Without DEFORMED locked in,
    # the punch stays at its frame-0 position for the whole animation.
    # Do NOT set renderStyle/visibleEdges here — locking before those global
    # calls are made keeps the default shaded+edges look (mesh visible through
    # the translucency), which is the intended tooling appearance.
    vp.odbDisplay.setValues(visibleDisplayGroups=(dg_rb,))
    vp.odbDisplay.display.setValues(plotState=(DEFORMED,))
    vp.odbDisplay.commonOptions.setValues(
        translucency=ON, translucencyFactor=0.25)
    vp.odbDisplay.displayGroupInstances['Rigid Bodies'].setValues(lockOptions=ON)

    # Specimen: contours on deformed, filled, no edges, true scale
    vp.odbDisplay.setValues(visibleDisplayGroups=(dg_sp, dg_rb))
    vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
    vp.odbDisplay.commonOptions.setValues(
        renderStyle=FILLED,
        visibleEdges=NONE,
        translucency=OFF,
        deformationScaling=UNIFORM,
        uniformScaleFactor=1.0,
    )
    vp.odbDisplay.setPrimaryVariable(
        variableLabel='SDV1', outputPosition=INTEGRATION_POINT)
    vp.odbDisplay.basicOptions.setValues(
        mirrorAboutXzPlane=True, mirrorAboutYzPlane=True)
    vp.odbDisplay.displayGroupInstances['Specimen'].setValues(lockOptions=ON)


# ── Display setup — two punches (PiP) ─────────────────────────────
def _setup_two_punches():
    vp = session.viewports['Viewport: 1']
    session.linkedViewportCommands.setValues(_highlightLinkedViewports=True)

    leaf = dgo.LeafFromConstraintNames(name=(
        "RigidBody_DIE-1        1",
        "RigidBody_MATRIX-1        1",
        "RigidBody_PUNCH1-1        1",
        "RigidBody_PUNCH2-1        1",
    ), type=RIGID_BODY)
    session.DisplayGroup(leaf=leaf, name='Rigid Bodies')

    leaf = dgo.LeafFromSurfaceSets(surfaceSets=(
        "SPECIMEN-1.ZMAX", "SPECIMEN-1.ZMIN",
    ))
    session.DisplayGroup(leaf=leaf, name='Specimen')

    dg_rb = session.displayGroups['Rigid Bodies']
    dg_sp = session.displayGroups['Specimen']

    vp.odbDisplay.setValues(visibleDisplayGroups=(dg_rb,))
    vp.odbDisplay.display.setValues(plotState=(DEFORMED,))
    vp.odbDisplay.commonOptions.setValues(
        translucency=ON, translucencyFactor=0.25)
    vp.odbDisplay.displayGroupInstances['Rigid Bodies'].setValues(lockOptions=ON)

    vp.odbDisplay.setValues(visibleDisplayGroups=(dg_sp, dg_rb))
    vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
    vp.odbDisplay.commonOptions.setValues(
        renderStyle=FILLED,
        visibleEdges=NONE,
        translucency=OFF,
        deformationScaling=UNIFORM,
        uniformScaleFactor=1.0,
    )
    vp.odbDisplay.setPrimaryVariable(
        variableLabel='SDV1', outputPosition=INTEGRATION_POINT)
    vp.odbDisplay.basicOptions.setValues(
        mirrorAboutXzPlane=True, mirrorAboutYzPlane=True)
    vp.odbDisplay.displayGroupInstances['Specimen'].setValues(lockOptions=ON)


def _setup_cut_view(vp, cut_rb_names):
    """
    Half-model front view — the Y=0 symmetry face acts as the 'cut'.

    cut_rb_names : tuple of constraint names (LeafFromConstraintNames) to show
                   as translucent rigid bodies in the cut view.  Typically the
                   punch + the rim tool that does NOT cover the deformation zone
                   (die below the blank or matrix/blank-holder above).

    Show all specimen elements (element-based leaf, not just ZMAX/ZMIN surfaces)
    with mirrorAboutXzPlane=OFF so only the Y>0 quarter is drawn.  Looking from
    -Y toward +Y the Y=0 face of the specimen is the front face, exposing the
    10 through-thickness element layers with FEATURE edges.
    mirrorAboutYzPlane=ON keeps the full ±X width.

    Returns True on success, False if display groups cannot be built.
    """
    # ── Specimen: element-based so the Y=0 face renders ──────────────────────
    try:
        leaf = dgo.LeafFromPartInstance(name=('SPECIMEN-1',))
    except Exception:
        try:
            leaf = dgo.LeafFromElementSets(elementSets=('SPECIMEN-1.ELALL',))
        except Exception as e:
            print('  WARNING _setup_cut_view: cannot build element leaf (%s).' % e)
            return False
    try:
        session.DisplayGroup(leaf=leaf, name='Specimen_Section')
    except Exception:
        pass  # already exists — reuse

    # ── Rigid bodies for cut view (subset chosen by caller) ──────────────────
    try:
        rb_leaf = dgo.LeafFromConstraintNames(name=cut_rb_names, type=RIGID_BODY)
        try:
            session.DisplayGroup(leaf=rb_leaf, name='Cut Rigid Bodies')
        except Exception:
            session.displayGroups['Cut Rigid Bodies'].setValues(newLeaf=rb_leaf)
        print('  Cut RB group: %s' % (cut_rb_names,))
    except Exception as e:
        print('  WARNING _setup_cut_view: cannot build Cut RB group (%s) — using all.' % e)
        try:
            session.displayGroups['Cut Rigid Bodies']
        except KeyError:
            try:
                session.displayGroups['Rigid Bodies']
                # fall back silently — name adjusted below
            except Exception:
                pass

    try:
        dg_sec = session.displayGroups['Specimen_Section']
    except KeyError as e:
        print('  WARNING _setup_cut_view: Specimen_Section not found (%s).' % e)
        return False
    try:
        dg_cut_rb = session.displayGroups['Cut Rigid Bodies']
    except KeyError:
        try:
            dg_cut_rb = session.displayGroups['Rigid Bodies']
            print('  NOTE: Cut Rigid Bodies not found, falling back to Rigid Bodies.')
        except KeyError as e:
            print('  WARNING _setup_cut_view: no rigid body group found (%s).' % e)
            return False

    # ── Lock specimen first, then add rigid bodies ────────────────────────────
    # Problem: when _setup_cut_view runs, commonOptions is already in
    # renderStyle=FILLED + translucency=OFF (left over from main movie).
    # Locking rigid bodies at that point freezes them as FILLED+opaque.
    #
    # Fix: invert the order.
    #   1. Show only specimen → set CONTOURS_ON_DEF + FILLED + no translucency
    #      → lock specimen so these settings survive the later global changes.
    #   2. ADD rigid bodies (lock on specimen survives — adding preserves locks).
    #   3. Set global DEFORMED + SHADED + translucency=ON.
    #      Unlocked rigid bodies pick up the translucent global state.
    #      Locked specimen keeps its CONTOURS_ON_DEF + FILLED + opaque settings.
    try:
        vp.odbDisplay.setValues(visibleDisplayGroups=(dg_sec,))
        vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
        vp.odbDisplay.commonOptions.setValues(
            renderStyle=FILLED,
            visibleEdges=FEATURE,
            translucency=OFF,
            deformationScaling=UNIFORM,
            uniformScaleFactor=1.0,
        )
        vp.odbDisplay.displayGroupInstances['Specimen_Section'].setValues(lockOptions=ON)
    except Exception as e:
        print('  WARNING _setup_cut_view: specimen lock failed (%s).' % e)
        return False

    # Add rigid bodies — specimen stays in the set so its lock is preserved.
    try:
        vp.odbDisplay.setValues(visibleDisplayGroups=(dg_sec, dg_cut_rb))
    except Exception as e:
        print('  WARNING _setup_cut_view: setValues failed (%s).' % e)
        return False

    # Global settings now apply to the unlocked rigid bodies only.
    # Locked specimen ignores these.
    vp.odbDisplay.display.setValues(plotState=(DEFORMED,))
    vp.odbDisplay.commonOptions.setValues(
        renderStyle=SHADED,
        visibleEdges=FEATURE,
        translucency=ON,
        translucencyFactor=0.25,
    )

    # Half model: X mirror for full ±X width; NO Y mirror so Y=0 face is exposed
    vp.odbDisplay.basicOptions.setValues(
        mirrorAboutXzPlane=False,
        mirrorAboutYzPlane=True,
    )

    # Camera: -Y looking toward +Y, Z up — Y=0 face is front-facing
    vp.view.setValues(
        cameraPosition=(0., -500., 0.),
        cameraUpVector=(0., 0., 1.),
        cameraTarget=(0., 0., 0.),
    )
    return True


def _render_animation(vp, out_file):
    """Export animation via Abaqus's built-in writeImageAnimation (TIME_HISTORY),
    then convert the lossless AVI to webm (VP9) + MP4 (H.264) with ffmpeg.

    Returns ffmpeg exit code for the webm pass (0 = success).
    """
    tmp_avi = '/tmp/abaqus_movie_%d.avi' % os.getpid()

    # Lossless 32-bit AVI intermediate — no color loss before ffmpeg re-encodes.
    session.aviOptions.setValues(
        compressionMethod=RAW32,
        sizeDefinition=USER_DEFINED,
        imageSize=(1920, 1080),
    )
    vp.animationController.setValues(animationType=TIME_HISTORY)
    session.imageAnimationOptions.setValues(
        frameRate=15, compass=OFF, timeScale=1)
    session.writeImageAnimation(
        fileName=tmp_avi, format=AVI, canvasObjects=(vp,))
    vp.animationController.setValues(animationType=NONE)

    # Abaqus may append .avi itself — find whichever exists.
    actual_avi = tmp_avi if os.path.isfile(tmp_avi) else tmp_avi + '.avi'
    if not os.path.isfile(actual_avi):
        print('  WARNING: AVI not found at %s — skipping conversion.' % actual_avi)
        return 1

    _vf = 'format=yuv420p,unsharp=5:5:0.8:3:3:0.4'

    # webm / VP9 — constant quality, no bitrate cap
    ret = subprocess.call([
        'ffmpeg', '-y', '-i', actual_avi,
        '-vf', _vf,
        '-vcodec', 'libvpx-vp9', '-crf', '18', '-b:v', '0',
        '-deadline', 'good', '-cpu-used', '2',
        out_file,
    ])

    # MP4 / H.264 — side output for broad player compatibility
    mp4_file = out_file.replace('.webm', '.mp4')
    subprocess.call([
        'ffmpeg', '-y', '-i', actual_avi,
        '-vf', _vf,
        '-c:v', 'libx264', '-crf', '18',
        mp4_file,
    ])
    if os.path.isfile(mp4_file):
        print('  MP4  -> %s' % mp4_file)

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
    vp.maximize()
    vp.setValues(displayedObject=odb)
    session.printOptions.setValues(vpDecorations=OFF, vpBackground=ON)
    session.pngOptions.setValues(imageSize=(1920, 1080))

    # ── Annotations ───────────────────────────────────────────
    vp.viewportAnnotationOptions.setValues(
        compass=OFF, title=OFF, state=OFF, legend=ON,
        legendFont='-*-verdana-bold-r-normal-*-*-140-*-*-p-*-*-*',
        legendNumberFormat=FIXED, legendDecimalPlaces=2)

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
        _co.setValues(
            maxAutoCompute=OFF, maxValue=_cmax,
            minAutoCompute=OFF, minValue=_cmin,
            numIntervals=12,
            spectrum='Rainbow',
        )
    try:
        session.defaultOdbDisplay.contourOptions.setValues(
            maxAutoCompute=OFF, maxValue=_cmax,
            minAutoCompute=OFF, minValue=_cmin,
            numIntervals=12,
            spectrum='Rainbow',
        )
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

    # ── Cut view movie (Y=0 cross-section, front camera) ──────────────────────
    # Rigid bodies shown in cut view: punch + blank holder (MATRIX, rim tool
    # above the blank).  DIE is below and obscures the punch in the front view.
    if two_punches:
        _cut_rb_names = (
            "RigidBody_PUNCH1-1        1",
            "RigidBody_PUNCH2-1        1",
            "RigidBody_MATRIX-1        1",
        )
    else:
        _cut_rb_names = (
            "RigidBody_PUNCH-1        1",
            "RigidBody_MATRIX-1        1",
        )

    cut_file = os.path.join(out_dir, job_name + '_cut.webm')
    print('  Rendering cut view -> %s ...' % os.path.basename(cut_file))
    if _setup_cut_view(vp, _cut_rb_names):
        vp.odbDisplay.setFrame(step=_last_s_idx, frame=_last_f_idx)
        vp.view.fitView()
        # Re-apply camera after fitView(): fitView shifts cameraTarget to the
        # Y>0 model centroid, tilting the -Y look direction and making the
        # translucent punch shape appear visually offset from the Y=0 cut face.
        vp.view.setValues(
            cameraPosition=(0., -500., 0.),
            cameraUpVector=(0., 0., 1.),
            cameraTarget=(0., 0., 0.),
        )
        ret_cut = _render_animation(vp, cut_file)
        if ret_cut != 0:
            print('  WARNING: cut video ffmpeg exited with code %d' % ret_cut)
        else:
            print('  Done (cut) -> %s' % cut_file)

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
