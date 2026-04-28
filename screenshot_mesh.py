# -*- coding: utf-8 -*-
"""
screenshot_mesh.py  —  Render PNG screenshots of the specimen mesh from a .cae.

Run via submit_one.sh / submit_all.sh immediately after the build step:
    OUTPUT_DIR=<path>  JOB_NAME=<name>  xvfb-run -a abaqus cae noGUI=screenshot_mesh.py

Output (per job):
    <OUTPUT_DIR>/<JOB_NAME>_mesh.png        — ISO view
    <OUTPUT_DIR>/<JOB_NAME>_mesh_top.png    — face-on view (+Z camera)

API confirmed from macro recording (Abaqus 2023):
  - Switch viewport to the Part object (not the assembly).
  - partDisplay.setValues(mesh=ON)
  - partDisplay.meshOptions.setValues(meshTechnique=ON)   ← shows technique coloring
  - partDisplay.geometryOptions.setValues(referenceRepresentation=OFF)
"""
from abaqus import *
from abaqusConstants import *
import visualization
import os


def _resolve_params():
    job_name = os.environ.get('JOB_NAME', '').strip()
    out_dir  = os.environ.get('OUTPUT_DIR', '').strip()

    if not job_name or not out_dir:
        env_file = os.path.join(os.getcwd(), 'last_build.env')
        if os.path.isfile(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('JOB_NAME='):
                        job_name = line.split('=', 1)[1].strip('"\'')
                    elif line.startswith('OUTPUT_SUBDIR='):
                        sub = line.split('=', 1)[1].strip('"\'')
                        if not out_dir:
                            out_dir = os.path.join(os.getcwd(), sub)

    return job_name, out_dir


def take_screenshot(job_name, out_dir):
    cae_path = None
    for f in sorted(os.listdir(out_dir)):
        if f.endswith('.cae'):
            cae_path = os.path.join(out_dir, f)
            break
    if cae_path is None:
        print('ERROR: no .cae file found in %s' % out_dir)
        return

    out_iso = os.path.join(out_dir, job_name + '_mesh')
    out_top = os.path.join(out_dir, job_name + '_mesh_top')

    print('=' * 60)
    print('  screenshot_mesh.py')
    print('  CAE : %s' % cae_path)
    print('=' * 60)

    openMdb(pathName=cae_path)
    m = mdb.models[mdb.models.keys()[0]]

    # Find the specimen (only deformable part with elements)
    specimen_part = None
    for pname, part in m.parts.items():
        print('  Part: %-28s  elements=%d  nodes=%d'
              % (pname, len(part.elements), len(part.nodes)))
        if specimen_part is None and len(part.elements) > 0:
            specimen_part = part
            print('    -> specimen')

    if specimen_part is None:
        print('ERROR: no meshed part found.')
        return

    vp = session.viewports['Viewport: 1']

    # ── Switch to Part module context (confirmed by macro recording) ──────────
    vp.setValues(displayedObject=specimen_part)
    vp.partDisplay.setValues(mesh=ON)
    vp.partDisplay.meshOptions.setValues(meshTechnique=ON)
    vp.partDisplay.geometryOptions.setValues(referenceRepresentation=OFF)

    session.graphicsOptions.setValues(backgroundColor='#FFFFFF')
    session.pngOptions.setValues(imageSize=(1280, 960))
    session.printOptions.setValues(vpDecorations=OFF, vpBackground=ON)

    # ── ISO view ──────────────────────────────────────────────────────────────
    vp.view.setValues(session.views['Iso'])
    vp.view.fitView()
    session.printToFile(fileName=out_iso, format=PNG, canvasObjects=(vp,))
    print('  ISO -> %s.png' % out_iso)

    # ── Face-on view: blank in XY plane, look from +Z ─────────────────────────
    try:
        vp.view.setProjection(projection=PARALLEL)
        vp.view.setValues(
            cameraPosition=(0.0, 0.0, 1000.0),
            cameraUpVector=(0.0, 1.0, 0.0),
            cameraTarget=(0.0, 0.0, 0.0),
        )
        vp.view.fitView()
        session.printToFile(fileName=out_top, format=PNG, canvasObjects=(vp,))
        print('  Top -> %s.png' % out_top)
    except Exception as e:
        print('  Top view failed: %s' % e)

    print('=' * 60)


job_name, out_dir = _resolve_params()
print('  JOB_NAME  : %s' % job_name)
print('  OUTPUT_DIR: %s' % out_dir)

if not job_name or not out_dir:
    print('ERROR: JOB_NAME and OUTPUT_DIR must be set.')
elif not os.path.isdir(out_dir):
    print('ERROR: output directory not found: %s' % out_dir)
else:
    take_screenshot(job_name, out_dir)
