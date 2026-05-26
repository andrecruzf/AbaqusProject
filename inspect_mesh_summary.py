# -*- coding: utf-8 -*-
from __future__ import print_function
from abaqus import *
import os


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

log('MODEL %s' % model.name)
for name, part in model.parts.items():
    log('PART %s cells=%d faces=%d edges=%d elems=%d nodes=%d features=%d'
        % (name, len(part.cells), len(part.faces), len(part.edges),
           len(part.elements), len(part.nodes), len(part.features)))
    if len(part.elements):
        try:
            log('  first_element_label=%s' % part.elements[0].label)
        except Exception:
            pass

if _out:
    _out.close()
