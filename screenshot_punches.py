# -*- coding: utf-8 -*-
"""
screenshot_punches.py  —  Render a PNG preview for every punch .cae in PiP_Punches/.

Run once on Euler (from AbaqusProject/):
    for cae in PiP_Punches/*.cae; do
        PUNCH_CAE=$cae xvfb-run -a abaqus cae noGUI=screenshot_punches.py
    done

Or via the helper:
    bash render_punch_previews.sh

Output:
    PiP_Punches/PUNCH_XX.png   — ISO view of the punch solid
"""
from abaqus import *
from abaqusConstants import *
import os

EULER_DIR  = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
PUNCH_DIR  = os.path.join(EULER_DIR, 'PiP_Punches')
cae_path   = os.environ.get('PUNCH_CAE', '').strip()

if not cae_path:
    print('ERROR: set PUNCH_CAE env var to the .cae path.')
else:
    punch_id  = os.path.splitext(os.path.basename(cae_path))[0]   # e.g. PUNCH_21
    out_png   = os.path.join(PUNCH_DIR, punch_id)                  # Abaqus appends .png

    print('=== screenshot_punches.py ===')
    print('  CAE : %s' % cae_path)
    print('  OUT : %s.png' % out_png)

    openMdb(pathName=cae_path)
    m = mdb.models[mdb.models.keys()[0]]

    # Find the punch part (first part with geometry)
    part = None
    for pname, p in m.parts.items():
        part = p
        break

    if part is None:
        print('ERROR: no part found in %s' % cae_path)
    else:
        vp = session.viewports['Viewport: 1']
        vp.setValues(displayedObject=part)
        try:
            vp.partDisplay.setValues(renderStyle=SHADED)
        except Exception:
            pass

        session.graphicsOptions.setValues(backgroundColor='#F5F5F5')
        session.pngOptions.setValues(imageSize=(800, 800))
        session.printOptions.setValues(vpDecorations=OFF, vpBackground=ON)

        vp.view.setValues(session.views['Iso'])
        vp.view.fitView()
        session.printToFile(fileName=out_png, format=PNG, canvasObjects=(vp,))
        print('  Saved %s.png' % out_png)
