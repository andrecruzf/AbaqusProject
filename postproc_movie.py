# -*- coding: utf-8 -*-
"""
postproc_movie.py  —  Generate a SDV1 (EQPS) animation from a Nakajima ODB.

Standalone:
    ODB_PATH=Nakazima_W50_t1.odb abaqus cae noGUI=postproc_movie.py

From pipeline (called by run_cluster.sh after solver):
    ODB_PATH=<OUTPUT_DIR>/<JOB_NAME>.odb abaqus cae noGUI=postproc_movie.py

Output:
    <odb_dir>/<job_name>_movie.webm

Exports each frame as PNG then combines with ffmpeg.
The quarter model is mirrored about both symmetry planes.
"""
from __future__ import print_function
from abaqus import session
from abaqusConstants import (CONTOURS_ON_DEF, UNDEFORMED, PARALLEL,
                              INTEGRATION_POINT, PNG, ON, OFF,
                              ENGINEERING, SCIENTIFIC, FREE, FEATURE, WIREFRAME)
import visualization
import os
import sys
import subprocess
import glob


def _resolve_odb_path():
    env_odb = os.environ.get('ODB_PATH', '')
    if env_odb:
        return os.path.abspath(env_odb)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_file   = os.path.join(script_dir, 'last_build.env')
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
        return os.path.join(script_dir, subdir, job_name + '.odb')
    return None


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
    print('  ODB : %s' % odb_path)
    print('  OUT : %s' % out_file)
    print('=' * 60)

    if not os.path.isfile(odb_path):
        print('ERROR: ODB not found: %s' % odb_path)
        return

    # ── Open ODB ──────────────────────────────────────────────
    odb = session.openOdb(name=odb_path, readOnly=True)
    vp  = session.viewports['Viewport: 1']
    vp.setValues(displayedObject=odb, width=280, height=210)
    session.printOptions.setValues(vpDecorations=ON, vpBackground=ON)
    session.pngOptions.setValues(imageSize=(1280, 960))

    # ── Modern look ───────────────────────────────────────────
    # Dark background
    session.graphicsOptions.setValues(backgroundColor='#1a1a2e')

    # Clean up annotations
    vp.viewportAnnotationOptions.setValues(
        compass=OFF,
        title=OFF,
        state=ON,
        legend=ON,
        legendFont='-*-verdana-bold-r-normal-*-*-140-*-*-p-*-*-*',
        legendNumberFormat=ENGINEERING)

    # ── Display settings ──────────────────────────────────────
    vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
    vp.odbDisplay.commonOptions.setValues(visibleEdges=FREE)
    vp.view.setProjection(projection=PARALLEL)

    vp.odbDisplay.basicOptions.setValues(
        mirrorAboutXzPlane=True,
        mirrorAboutYzPlane=True)

    vp.odbDisplay.setPrimaryVariable(
        variableLabel='SDV1',
        outputPosition=INTEGRATION_POINT)

    # ── Show rigid tools (punch shape) ────────────────────────
    # Overlay the undeformed rigid surfaces (Punch, Die, Matrix) as a
    # translucent wireframe so the punch profile (flat vs. hemispherical)
    # is clearly visible against the SDV1 contour plot.
    try:
        vp.odbDisplay.display.setValues(
            plotState=(CONTOURS_ON_DEF, UNDEFORMED))
        vp.odbDisplay.superimposeOptions.setValues(
            visibleEdges=FEATURE,
            translucency=ON,
            translucencyFactor=0.55)
    except Exception as e:
        print('  NOTE: superimpose options not applied (%s)' % e)

    # ── Isometric view — shows punch shape clearly ────────────
    # Front view (along -Y) clips the punch if fitView re-centres on the
    # blank each frame.  Iso shows the 3-D geometry (flat vs. hemisphere)
    # without needing to tilt manually.
    vp.view.setValues(session.views['Iso'])
    vp.view.fitView()
    vp.view.zoom(zoomFactor=1.25)

    # Snapshot the camera once so it stays locked across all frames.
    # (setFrame resets the view in some Abaqus versions.)
    _cam = dict(
        cameraPosition=vp.view.cameraPosition,
        cameraUpVector=vp.view.cameraUpVector,
        cameraTarget=vp.view.cameraTarget,
        width=vp.view.width,
        height=vp.view.height,
    )

    # ── Export frames ─────────────────────────────────────────
    step   = odb.steps.values()[0]
    frames = step.frames
    n      = len(frames)
    print('  Exporting %d frames ...' % n)

    for i in range(n):
        vp.odbDisplay.setFrame(step=0, frame=i)
        try:
            vp.view.setValues(**_cam)   # restore locked camera
        except Exception:
            pass
        frame_file = os.path.join(frame_dir, 'frame_%04d' % i)
        session.printToFile(
            fileName=frame_file,
            format=PNG,
            canvasObjects=(vp,))
        if i % 10 == 0:
            print('    frame %d / %d' % (i, n))

    odb.close()

    # ── Combine with ffmpeg ───────────────────────────────────
    pattern = os.path.join(frame_dir, 'frame_%04d.png')
    cmd = ['ffmpeg', '-y', '-framerate', '10', '-i', pattern,
           '-vcodec', 'libvpx', '-crf', '10', '-b:v', '1M', out_file]
    print('  Running ffmpeg ...')
    ret = subprocess.call(cmd)
    if ret != 0:
        print('  WARNING: ffmpeg failed (exit %d). Frames kept in %s' % (ret, frame_dir))
    else:
        # Clean up frames
        for f in glob.glob(os.path.join(frame_dir, 'frame_*.png')):
            os.remove(f)
        os.rmdir(frame_dir)
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
