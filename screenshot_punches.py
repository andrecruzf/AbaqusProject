# -*- coding: utf-8 -*-
"""
screenshot_punches.py  —  Render PNG + export mesh JSON for every punch .cae.

Run once on Euler via render_punch_previews.sh.

Output per punch:
    PiP_Punches/PUNCH_XX.png          — shaded ISO screenshot
    PiP_Punches/PUNCH_XX_mesh.json    — {nodes: [[x,y,z],...], triangles: [[i,j,k],...]}
"""
from abaqus import *
from abaqusConstants import *
import os, json

EULER_DIR = os.getcwd()
PUNCH_DIR = os.environ.get('PUNCH_DIR', '').strip() or os.path.join(EULER_DIR, 'PiP_Punches')
cae_path  = os.environ.get('PUNCH_CAE', '').strip()

if not cae_path:
    print('ERROR: set PUNCH_CAE env var to the .cae path.')
else:
    punch_id = os.path.splitext(os.path.basename(cae_path))[0]

    print('=== screenshot_punches.py  %s ===' % punch_id)
    print('  CAE : %s' % cae_path)

    openMdb(pathName=cae_path)
    m    = mdb.models[mdb.models.keys()[0]]
    part = m.parts[m.parts.keys()[0]]

    # ── PNG screenshot ────────────────────────────────────────────────────────
    out_png = os.path.join(PUNCH_DIR, punch_id)
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
    print('  PNG  -> %s.png' % out_png)

    # ── Mesh JSON export ──────────────────────────────────────────────────────
    # Build label→index map from the part's node array
    nodes      = part.nodes           # MeshNodeArray
    elements   = part.elements        # MeshElementArray

    label_to_idx = {}
    coords       = []
    for i, n in enumerate(nodes):
        coords.append(list(n.coordinates))
        label_to_idx[n.label] = i

    triangles = []
    for el in elements:
        conn = el.connectivity          # tuple of node labels
        # Quads → 2 triangles; tris → 1 triangle; ignore other types
        if len(conn) >= 3:
            a = label_to_idx.get(conn[0])
            b = label_to_idx.get(conn[1])
            c = label_to_idx.get(conn[2])
            if None not in (a, b, c):
                triangles.append([a, b, c])
            if len(conn) >= 4:
                d = label_to_idx.get(conn[3])
                if None not in (a, c, d):
                    triangles.append([a, c, d])

    out_json = os.path.join(PUNCH_DIR, punch_id + '_mesh.json')
    with open(out_json, 'w') as f:
        json.dump({'nodes': coords, 'triangles': triangles}, f, separators=(',', ':'))
    print('  JSON -> %s  (%d nodes, %d triangles)'
          % (out_json, len(coords), len(triangles)))
