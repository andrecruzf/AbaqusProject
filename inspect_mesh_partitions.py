# -*- coding: utf-8 -*-
from __future__ import print_function
from abaqus import *
from abaqusConstants import *
import os
import math


cae_path = os.environ.get('CAE_PATH', '').strip()
if not cae_path:
    raise RuntimeError('Set CAE_PATH to a generated .cae file')
out_path = os.environ.get('INSPECT_OUT', '').strip()
_out = open(out_path, 'w') if out_path else None


def log(msg):
    print(msg)
    if _out:
        _out.write(msg + '\n')
        _out.flush()

openMdb(pathName=cae_path)
model = mdb.models[mdb.models.keys()[0]]

part = None
for name, candidate in model.parts.items():
    if len(candidate.cells) and len(candidate.elements):
        part = candidate
        log('PART %s cells=%d faces=%d edges=%d elems=%d nodes=%d'
            % (name, len(candidate.cells), len(candidate.faces),
               len(candidate.edges), len(candidate.elements),
               len(candidate.nodes)))
        break
if part is None:
    raise RuntimeError('No meshed solid part found')

log('FEATURES')
for name in part.features.keys():
    log('  %s' % name)

log('CELLS')
for i, cell in enumerate(part.cells):
    x, y, z = cell.pointOn[0]
    r = math.sqrt(x*x + y*y)
    try:
        tech = part.getMeshControls(region=cell, attribute=TECHNIQUE)
    except Exception as exc:
        tech = 'ERR:%s' % exc
    try:
        shape = part.getMeshControls(region=cell, attribute=ELEM_SHAPE)
    except Exception as exc:
        shape = 'ERR:%s' % exc
    log('  cell=%03d r=%.3f point=(%.3f,%.3f,%.3f) technique=%s shape=%s'
        % (i, r, x, y, z, tech, shape))

log('FACES_TOP')
z_ref = max(n.coordinates[2] for n in part.nodes)
for i, face in enumerate(part.faces):
    if not face.pointOn:
        continue
    x, y, z = face.pointOn[0]
    if abs(z - z_ref) < 0.1:
        r = math.sqrt(x*x + y*y)
        log('  face=%03d r=%.3f point=(%.3f,%.3f,%.3f)' % (i, r, x, y, z))

if _out:
    _out.close()
