#!/bin/bash
# =============================================================
# run.sh  —  Lance le pipeline Nakazima via Abaqus CAE noGUI
# =============================================================
# Usage :
#   ./run.sh                   → utilise config.py tel quel
#   ./run.sh 2>&1 | tee build.log
#
# Prérequis :
#   • Abaqus CAE installé et accessible via la commande 'abaqus'
#   • Les fichiers .inp du superviseur présents dans INP_DIR (config.py)
#   • Python path / licence Abaqus correctement configurés
# =============================================================

set -e   # arrêt immédiat en cas d'erreur

# Répertoire du script (indépendant du répertoire de travail courant)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Commande Abaqus — modifier si le chemin n'est pas dans le PATH
ABAQUS_CMD="abaqus"

echo "=============================================="
echo "  Pipeline Nakazima — $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Répertoire : $SCRIPT_DIR"
echo "=============================================="

# Lance Abaqus CAE en mode sans IHM
"$ABAQUS_CMD" cae noGUI="$SCRIPT_DIR/build_model.py"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "Build réussi — fichiers dans le sous-répertoire de la simulation."
    echo ""
    echo "Soumettre sur cluster :"
    echo "  sbatch run_cluster.sh"
    echo "  (ou : ./submit.sh  pour suivre le job en direct)"
else
    echo ""
    echo "ERREUR : build_model.py a retourné le code $EXIT_CODE"
    echo "  Vérifier abaqus.rpy et le log ci-dessus."
    exit $EXIT_CODE
fi
