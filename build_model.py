# -*- coding: utf-8 -*-
"""
build_model.py  —  Orchestrateur principal du pipeline Nakazima
================================================================
Lance via Abaqus CAE en mode script (pas de GUI) :

    abaqus cae noGUI=build_model.py

Le script exécute séquentiellement les 8 modules pour :
  1. Créer les pièces (outils rigides + éprouvette)
  2. Assembler le modèle
  3. Définir le matériau et la section coque
  4. Créer le step Dynamic Explicit + amplitude Smooth Step
  5. Définir le contact général
  6. Appliquer les conditions aux limites
  7. Définir les demandes de sortie (Field + History)
  8. Sauvegarder le .cae et écrire le .inp

Sorties :
  • nakazima_model.cae   → ouvrir dans Abaqus CAE pour vérification
  • nakazima_job.inp     → soumettre sur cluster pour la simulation FEA

Modifier uniquement config.py pour changer de configuration.
"""
from __future__ import print_function
import sys
import os

# ── Chemin du projet (nécessaire pour les imports relatifs) ───
_THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# ── Imports modules ───────────────────────────────────────────


import config as cfg
from modules.parts    import create_parts
from modules.assembly import create_assembly
from modules.material import define_material
from modules.step     import create_step
from modules.contact  import define_contact
from modules.boundary import apply_bcs
from modules.output   import define_output
from modules.job      import save_and_export


# ─────────────────────────────────────────────────────────────
def run():
    print('=' * 60)
    print('  Pipeline Nakazima — démarrage')
    print('  Modèle    : %s' % cfg.MODEL_NAME)
    print('  Specimen  : W%d (source=%s)' % (cfg.SPECIMEN_WIDTH,
                                              cfg.GEOMETRY_SOURCE))
    print('  Épaisseur : %.2f mm' % cfg.BLANK_THICKNESS)
    print('  Punch     : %.1f mm  →  step=%.4e s'
          % (cfg.PUNCH_DISPLACEMENT, cfg.STEP_TIME))
    print('  Output    : %s/' % cfg.OUTPUT_DIR)
    print('=' * 60)

    if not os.path.isdir(cfg.OUTPUT_DIR):
        os.makedirs(cfg.OUTPUT_DIR)
        print('  Created output directory: %s/' % cfg.OUTPUT_DIR)

    print('\n[1/8] Pièces ...')
    create_parts(cfg)

    print('\n[2/8] Assembly ...')
    create_assembly(cfg)

    print('\n[3/8] Matériau ...')
    define_material(cfg)

    print('\n[4/8] Step & amplitude ...')
    create_step(cfg)

    print('\n[5/8] Contact ...')
    define_contact(cfg)

    print('\n[6/8] Conditions aux limites ...')
    apply_bcs(cfg)

    # Output requests are injected into the .inp by job.py (_inject_output_requests)
    # to avoid 'Model has no attribute FieldOutputRequest' in Abaqus 2023 noGUI.

    print('\n[8/8] Sauvegarde .cae + écriture .inp ...')
    save_and_export(cfg)

    print('\n' + '=' * 60)
    print('  BUILD COMPLET')
    print('  .cae : %s/%s' % (cfg.OUTPUT_DIR, cfg.CAE_NAME))
    print('  .inp : %s/%s.inp' % (cfg.OUTPUT_DIR, cfg.JOB_NAME))
    print('=' * 60)


# ─────────────────────────────────────────────────────────────
if __name__ == '__main__' or 'abaqus' in sys.version.lower() or True:
    run()
