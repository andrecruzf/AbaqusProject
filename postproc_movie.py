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

_BG = '#1a1a2e'


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


def make_movie(odb_path, out_dir=None):
    odb_path = os.path.abspath(odb_path)
    if out_dir is None:
        out_dir = os.path.dirname(odb_path)

    job_name  = os.path.splitext(os.path.basename(odb_path))[0]
    frame_dir = os.path.join(out_dir, 'frames_tmp')
    out_file  = os.path.join(out_dir, job_name + '_movie.webm')

    if not os.path.isdir(frame_dir):
        os.makedirs(frame_dir)

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
        compass=OFF, title=OFF, state=ON, legend=ON,
        legendFont='-*-verdana-bold-r-normal-*-*-140-*-*-p-*-*-*',
        legendNumberFormat=ENGINEERING)

    # ── Per-frame auto color range — full spectrum at every frame ──
    vp.odbDisplay.contourOptions.setValues(
        minAutoCompute=ON, maxAutoCompute=ON)
    print('  Contour range: per-frame auto')

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

    # ── Camera ────────────────────────────────────────────────
    session.graphicsOptions.setValues(backgroundColor=_BG)
    vp.view.setValues(session.views['Iso'])
    vp.view.fitView()
    vp.view.zoom(zoomFactor=1.25)
    _cam = dict(
        cameraPosition=vp.view.cameraPosition,
        cameraUpVector=vp.view.cameraUpVector,
        cameraTarget=vp.view.cameraTarget,
        width=vp.view.width,
        height=vp.view.height,
    )

    # ── Export frames ─────────────────────────────────────────
    step_keys = odb.steps.keys()
    total = 0
    for k in step_keys:
        total += len(odb.steps[k].frames)
    print('  Steps: %d   Frames: %d' % (len(step_keys), total))

    global_idx = 0
    for step_idx in range(len(step_keys)):
        step_name = step_keys[step_idx]
        n_frames  = len(odb.steps[step_name].frames)
        for frame_idx in range(n_frames):
            vp.odbDisplay.setFrame(step=step_idx, frame=frame_idx)
            try:
                vp.view.setValues(**_cam)
            except Exception:
                pass
            session.graphicsOptions.setValues(backgroundColor=_BG)
            session.printToFile(
                fileName=os.path.join(frame_dir, 'frame_%04d' % global_idx),
                format=PNG, canvasObjects=(vp,))
            if global_idx % 10 == 0:
                print('    frame %d / %d' % (global_idx, total))
            global_idx += 1

    odb.close()

    # ── ffmpeg encode ─────────────────────────────────────────
    print('  Running ffmpeg ...')
    pattern = os.path.join(frame_dir, 'frame_%04d.png')
    cmd = [
        'ffmpeg', '-y', '-framerate', '10', '-i', pattern,
        '-vf', 'format=yuv420p',
        '-vcodec', 'libvpx', '-crf', '10', '-b:v', '1M',
        out_file,
    ]

    ret = subprocess.call(cmd)
    if ret != 0:
        print('  WARNING: ffmpeg failed (exit %d). Frames in %s' % (ret, frame_dir))
    else:
        import glob
        for f in glob.glob(os.path.join(frame_dir, 'frame_*.png')):
            os.remove(f)
        try:
            os.rmdir(frame_dir)
        except OSError:
            pass
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
