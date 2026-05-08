# -*- coding: utf-8 -*-
"""
screenshot_punches.py  —  Render PNG + export STL for every punch .cae.

Run once on Euler via render_punch_previews.sh.

Output per punch:
    PiP_Punches/PUNCH_XX.png   — shaded ISO screenshot
    PiP_Punches/PUNCH_XX.stl   — binary STL from geometric surface (viewport tessellation)
"""
from abaqus import *
from abaqusConstants import *
import os

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

    vp = session.viewports['Viewport: 1']
    vp.setValues(displayedObject=part)
    try:
        vp.partDisplay.setValues(renderStyle=SHADED)
    except Exception:
        pass
    session.graphicsOptions.setValues(backgroundColor='#F5F5F5')
    vp.view.setValues(session.views['Iso'])
    vp.view.fitView()

    # ── PNG screenshot ────────────────────────────────────────────────────────
    out_png = os.path.join(PUNCH_DIR, punch_id)
    session.pngOptions.setValues(imageSize=(800, 800))
    session.printOptions.setValues(vpDecorations=OFF, vpBackground=ON)
    session.printToFile(fileName=out_png, format=PNG, canvasObjects=(vp,))
    print('  PNG  -> %s.png' % out_png)

    # ── STL export — geometric surface via viewport tessellation ─────────────
    out_stl = os.path.join(PUNCH_DIR, punch_id + '.stl')
    try:
        session.writeStlFile(fileName=out_stl, canvasObjects=(vp,))
        print('  STL  -> %s' % out_stl)
    except Exception as e:
        print('  WARNING: writeStlFile failed (%s), falling back to mesh export' % e)
        # Fallback: build binary STL from mesh elements
        import struct as _struct, math as _math

        def _cross(a, b):
            return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

        def _norm3(v):
            l = _math.sqrt(sum(x*x for x in v)) or 1.0
            return [x/l for x in v]

        mesh_nodes = part.nodes
        label_to_idx = {}
        coords = []
        for idx, nd in enumerate(mesh_nodes):
            coords.append(list(nd.coordinates))
            label_to_idx[nd.label] = idx

        triangles = []
        for el in part.elements:
            conn = el.connectivity
            if len(conn) >= 3:
                a = label_to_idx.get(conn[0])
                b = label_to_idx.get(conn[1])
                c = label_to_idx.get(conn[2])
                if None not in (a, b, c):
                    triangles.append((a, b, c))
                if len(conn) >= 4:
                    d = label_to_idx.get(conn[3])
                    if None not in (a, c, d):
                        triangles.append((a, c, d))

        with open(out_stl, 'wb') as _f:
            _f.write(('Abaqus mesh: ' + punch_id).ljust(80)[:80].encode('ascii', 'replace'))
            _f.write(_struct.pack('<I', len(triangles)))
            for tri in triangles:
                va, vb, vc = coords[tri[0]], coords[tri[1]], coords[tri[2]]
                ab = [vb[i]-va[i] for i in range(3)]
                ac = [vc[i]-va[i] for i in range(3)]
                n = _norm3(_cross(ab, ac))
                _f.write(_struct.pack('<3f', n[0], n[1], n[2]))
                _f.write(_struct.pack('<3f', va[0], va[1], va[2]))
                _f.write(_struct.pack('<3f', vb[0], vb[1], vb[2]))
                _f.write(_struct.pack('<3f', vc[0], vc[1], vc[2]))
                _f.write(_struct.pack('<H', 0))
        print('  STL  -> %s  (mesh fallback, %d triangles)' % (out_stl, len(triangles)))
