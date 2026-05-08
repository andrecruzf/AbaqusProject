# -*- coding: utf-8 -*-
"""
screenshot_punches.py  —  Render PNG + export STEP for every punch .cae.

Run once on Euler via render_punch_previews.sh.

Output per punch:
    PiP_Punches/PUNCH_XX.png    — shaded ISO screenshot
    PiP_Punches/PUNCH_XX.step   — STEP geometry (analytical, smooth)
    PiP_Punches/PUNCH_XX.stl    — binary STL fallback (viewport tessellation)
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
    model_key = mdb.models.keys()[0]
    part_key  = mdb.models[model_key].parts.keys()[0]
    m    = mdb.models[model_key]
    part = m.parts[part_key]

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

    # ── STEP export — analytical geometry, no tessellation ───────────────────
    # Abaqus records this command when you use File > Export > Part > STEP.
    # If your version uses a different method, record a macro to get the exact call.
    out_step = os.path.join(PUNCH_DIR, punch_id + '.step')
    step_ok = False
    try:
        part.writeGeomQuery(fileName=out_step, compressedFormat=False)
        if os.path.exists(out_step) and os.path.getsize(out_step) > 200:
            step_ok = True
            print('  STEP -> %s  (%d KB)' % (out_step, os.path.getsize(out_step) // 1024))
        else:
            print('  WARNING: writeGeomQuery produced empty/missing file; falling back to STL')
    except Exception as e:
        print('  WARNING: STEP export failed (%s); falling back to STL' % e)
        print('  Hint: record File > Export > Part > STEP in Abaqus to get the exact command')

    # ── STL fallback — viewport tessellation (smooth-ish) ────────────────────
    if not step_ok:
        out_stl = os.path.join(PUNCH_DIR, punch_id + '.stl')
        stl_ok  = False
        try:
            session.writeStlFile(fileName=out_stl, canvasObjects=(vp,))
            if os.path.exists(out_stl) and os.path.getsize(out_stl) > 84:
                stl_ok = True
                print('  STL  -> %s  (viewport tessellation)' % out_stl)
        except Exception as e:
            print('  WARNING: writeStlFile failed (%s); falling back to mesh STL' % e)

        if not stl_ok:
            # Final fallback: build binary STL from mesh elements.
            # Avoid generator expressions — Abaqus wraps coordinates in a
            # non-standard C float type that breaks sum(x*x for x in v).
            import struct as _struct, math as _math

            def _cross3(a, b):
                return (a[1]*b[2]-a[2]*b[1],
                        a[2]*b[0]-a[0]*b[2],
                        a[0]*b[1]-a[1]*b[0])

            def _norm3(v):
                s = v[0]*v[0] + v[1]*v[1] + v[2]*v[2]
                l = _math.sqrt(s) if s > 0.0 else 1.0
                return (v[0]/l, v[1]/l, v[2]/l)

            label_to_idx = {}
            coords = []
            for idx, nd in enumerate(part.nodes):
                # Cast to plain Python float — Abaqus coordinate type breaks
                # arithmetic inside generator expressions / sum().
                c = nd.coordinates
                coords.append((float(c[0]), float(c[1]), float(c[2])))
                label_to_idx[nd.label] = idx

            triangles = []
            for el in part.elements:
                conn = el.connectivity
                if len(conn) >= 3:
                    a = label_to_idx.get(conn[0])
                    b = label_to_idx.get(conn[1])
                    c = label_to_idx.get(conn[2])
                    if a is not None and b is not None and c is not None:
                        triangles.append((a, b, c))
                    if len(conn) >= 4:
                        d = label_to_idx.get(conn[3])
                        if a is not None and c is not None and d is not None:
                            triangles.append((a, c, d))

            out_stl = os.path.join(PUNCH_DIR, punch_id + '.stl')
            with open(out_stl, 'wb') as _f:
                _f.write(('Abaqus mesh: ' + punch_id).ljust(80)[:80].encode('ascii', 'replace'))
                _f.write(_struct.pack('<I', len(triangles)))
                for tri in triangles:
                    va = coords[tri[0]]; vb = coords[tri[1]]; vc = coords[tri[2]]
                    ab = (vb[0]-va[0], vb[1]-va[1], vb[2]-va[2])
                    ac = (vc[0]-va[0], vc[1]-va[1], vc[2]-va[2])
                    n  = _norm3(_cross3(ab, ac))
                    _f.write(_struct.pack('<3f', n[0],  n[1],  n[2]))
                    _f.write(_struct.pack('<3f', va[0], va[1], va[2]))
                    _f.write(_struct.pack('<3f', vb[0], vb[1], vb[2]))
                    _f.write(_struct.pack('<3f', vc[0], vc[1], vc[2]))
                    _f.write(_struct.pack('<H', 0))
            print('  STL  -> %s  (mesh fallback, %d triangles)' % (out_stl, len(triangles)))
