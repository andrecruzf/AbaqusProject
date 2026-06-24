# -*- coding: utf-8 -*-
"""
build_mesh_only.py  —  Minimal CAE mesh import
===============================================

Import only the specimen mesh from the CAE geometry file, regenerate the
mesh if needed, and save the resulting .cae without creating tools,
material, contact, step, or boundary conditions.
"""
from __future__ import print_function
import sys
import os

from abaqus import mdb

_THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import config as cfg
from modules.parts import import_specimen_mesh_only


def run():
    print('=' * 60)
    print('  Mesh-only CAE import')
    print('  Modèle    : %s' % cfg.MODEL_NAME)
    print('  Specimen  : W%d' % cfg.SPECIMEN_WIDTH)
    print('  Output    : %s/' % cfg.OUTPUT_DIR)
    print('=' * 60)

    if not os.path.isdir(cfg.OUTPUT_DIR):
        os.makedirs(cfg.OUTPUT_DIR)
        print('  Created output directory: %s/' % cfg.OUTPUT_DIR)

    if cfg.MODEL_NAME not in mdb.models:
        mdb.Model(name=cfg.MODEL_NAME)

    import_specimen_mesh_only(cfg)

    mesh_cae = os.path.join(cfg.OUTPUT_DIR, cfg.CAE_NAME)
    mdb.saveAs(pathName=mesh_cae)
    print('  Saved mesh-only CAE: %s' % mesh_cae)
    print('=' * 60)


if __name__ == '__main__' or 'abaqus' in sys.version.lower():
    run()
