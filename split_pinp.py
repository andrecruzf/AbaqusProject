# -*- coding: utf-8 -*-
"""
split_pinp.py  —  Split PinP.cae into one .cae per part
=========================================================
Run from the AbaqusProject/ directory:

    abaqus cae noGUI=split_pinp.py

Parts are routed automatically based on their name prefix:
    PUNCH_*   → PiP_Punches/<PART_NAME>.cae
    SPECIMEN* → PiP_Geometries/<PART_NAME>.cae
    other     → skipped with a warning (e.g. DIE, BLANKHOLDER)

Each output file contains a single Model-1 with a single part that is an
exact copy of the source part — mesh, element sets, node sets, surfaces,
and reference points are all preserved by Abaqus's Part(objectToCopy=...)
mechanism.
"""
from __future__ import print_function

from abaqus import mdb, openMdb
import os

# ── Configuration ─────────────────────────────────────────────
SRC_CAE   = 'PinP.cae'         # source CAE with all variants
PUNCH_DIR = 'PiP_Punches'      # output for PUNCH_* parts
SPEC_DIR  = 'PiP_Geometries'   # output for SPECIMEN* parts
SRC_MODEL = 'Model-1'          # model name inside PinP.cae to read from


# ── Helpers ───────────────────────────────────────────────────

def _find_src_model(models):
    """Return the model to read parts from (prefer 'Model-1')."""
    if SRC_MODEL in models:
        return SRC_MODEL
    return list(models.keys())[0]


def _open_fresh(path):
    """Open PinP.cae and return (model_name, part_name_list)."""
    openMdb(pathName=path)
    model_name = _find_src_model(mdb.models)
    part_names = list(mdb.models[model_name].parts.keys())
    return model_name, part_names


def _out_dir(part_name):
    """Route part to the correct output directory, or None to skip."""
    if part_name.startswith('PUNCH'):
        return PUNCH_DIR
    if part_name.startswith('SPECIMEN'):
        return SPEC_DIR
    return None


# ── Main ──────────────────────────────────────────────────────

def run():
    src_path = os.path.abspath(SRC_CAE)
    if not os.path.isfile(src_path):
        raise IOError('Source CAE not found: %s' % src_path)

    for d in (PUNCH_DIR, SPEC_DIR):
        if not os.path.isdir(d):
            os.makedirs(d)
            print('Created: %s/' % d)

    # --- discover parts ---
    model_name, part_names = _open_fresh(src_path)
    print('Source  : %s' % src_path)
    print('Model   : %s' % model_name)
    print('Parts   : %s' % part_names)
    print('')

    saved   = []
    skipped = []

    # --- split ---
    for part_name in part_names:
        out_dir = _out_dir(part_name)
        if out_dir is None:
            print('  SKIP  : %s (not a punch or specimen)' % part_name)
            skipped.append(part_name)
            continue

        print('── %s → %s/ ──' % (part_name, out_dir))

        # Re-open source so every iteration starts from a clean state.
        model_name, _ = _open_fresh(src_path)
        src_model = mdb.models[model_name]

        # Create a new empty model that will hold only this part.
        isolated = '__isolated_%s__' % part_name
        mdb.Model(name=isolated)
        mdb.models[isolated].Part(
            name=part_name,
            objectToCopy=src_model.parts[part_name]
        )

        # Remove every model except the isolated one.
        for m in list(mdb.models.keys()):
            if m != isolated:
                del mdb.models[m]

        # Rename to 'Model-1' so the output looks like a normal CAE.
        mdb.models.changeKey(fromName=isolated, toName='Model-1')

        out_path = os.path.join(os.path.abspath(out_dir), '%s.cae' % part_name)
        mdb.saveAs(pathName=out_path)
        print('  Saved : %s' % out_path)
        saved.append(out_path)

    print('')
    print('Done — %d saved, %d skipped %s' % (len(saved), len(skipped), skipped))


# ── Entry point ───────────────────────────────────────────────
if __name__ == '__main__' or 'abaqus' in __import__('sys').version.lower() or True:
    run()
