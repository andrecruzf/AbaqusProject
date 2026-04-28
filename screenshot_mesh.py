# -*- coding: utf-8 -*-
"""
screenshot_mesh.py  —  Render a PNG of the specimen mesh from a saved .cae.

Run via submit_one.sh / submit_all.sh immediately after the build step:
    OUTPUT_DIR=<path>  JOB_NAME=<name>  xvfb-run -a abaqus cae noGUI=screenshot_mesh.py

Output:
    <OUTPUT_DIR>/<JOB_NAME>_mesh.png
    <OUTPUT_DIR>/<JOB_NAME>_mesh_log.txt   (stdout mirror for diagnostics)
"""
from abaqus import *
from abaqusConstants import *
import visualization
import os
import sys
import shutil

_LOG_PATH = '/tmp/screenshot_mesh_out.txt'
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

    out_png = os.path.join(out_dir, job_name + '_mesh')

    print('=' * 60)
    print('  screenshot_mesh.py')
    print('  CAE  : %s' % cae_path)
    print('  OUT  : %s.png' % out_png)
    print('=' * 60)

    openMdb(pathName=cae_path)

    model_name = mdb.models.keys()[0]
    m = mdb.models[model_name]

    # Find the specimen (only deformable part — has elements)
    specimen_part = None
    for pname, part in m.parts.items():
        print('  Part: %-28s  elements=%d  nodes=%d'
              % (pname, len(part.elements), len(part.nodes)))
        if specimen_part is None and len(part.elements) > 0:
            specimen_part = part
            print('    → specimen')

    if specimen_part is None:
        print('ERROR: no deformable part with elements found.')
        return

    vp = session.viewports['Viewport: 1']

    # Switch viewport to the specimen part
    vp.setValues(displayedObject=specimen_part)

    # Dump available display attrs for diagnostics
    part_attrs = [a for a in dir(vp) if 'display' in a.lower() or 'render' in a.lower()]
    print('  vp display/render attrs: %s' % part_attrs)

    # Try to get mesh lines via partDisplayOptions (Part module context)
    for kwargs in [
        {'renderStyle': FILLED, 'visibleEdges': ALL},
        {'renderStyle': FILLED},
    ]:
        try:
            vp.partDisplayOptions.setValues(**kwargs)
            print('  partDisplayOptions.setValues(%s): OK' % kwargs)
            break
        except Exception as _e:
            print('  partDisplayOptions.setValues(%s): %s' % (kwargs, _e))

    # Fall back to trying assemblyDisplay if partDisplayOptions is absent
    if not hasattr(vp, 'partDisplayOptions'):
        for kwargs in [
            {'renderStyle': FILLED, 'visibleEdges': ALL},
            {'renderStyle': FILLED},
            {'renderStyle': WIREFRAME},
        ]:
            try:
                vp.assemblyDisplay.setValues(**kwargs)
                print('  assemblyDisplay.setValues(%s): OK' % kwargs)
                break
            except Exception as _e:
                print('  assemblyDisplay.setValues(%s): %s' % (kwargs, _e))

    # White background
    try:
        session.graphicsOptions.setValues(backgroundColor='#FFFFFF')
    except Exception as _e:
        print('  backgroundColor: %s' % _e)

    vp.view.setValues(session.views['Iso'])
    vp.view.fitView()

    session.pngOptions.setValues(imageSize=(1280, 960))
    session.printOptions.setValues(vpDecorations=OFF, vpBackground=ON)
    session.printToFile(fileName=out_png, format=PNG, canvasObjects=(vp,))

    print('  Done → %s.png' % out_png)
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

try:
    if job_name and out_dir and os.path.isdir(out_dir):
        shutil.copy(_LOG_PATH,
                    os.path.join(out_dir, job_name + '_mesh_log.txt'))
except Exception:
    pass
