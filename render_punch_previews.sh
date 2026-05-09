#!/bin/bash
# =============================================================
# render_punch_previews.sh  —  Export STEP/IGES/STL + PNG for all punches.
# Run ON Euler (from AbaqusProject/):
#   bash render_punch_previews.sh          # skip punches already done
#   bash render_punch_previews.sh --force  # re-export all
# =============================================================
set -e
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"
FORCE=0
[[ "${1}" == "--force" ]] && FORCE=1
module load abaqus/2023

cd "${EULER_DIR}"
for cae in "${EULER_DIR}/PiP_Punches"/PUNCH_*.cae; do
    punch_id=$(basename "$cae" .cae)
    out_step="${EULER_DIR}/PiP_Punches/${punch_id}.step"
    out_igs="${EULER_DIR}/PiP_Punches/${punch_id}.igs"

    if [ "$FORCE" -eq 0 ] && { [ -f "$out_step" ] || [ -f "$out_igs" ]; }; then
        echo "  Skipping ${punch_id} (already exported)"
        continue
    fi

    echo "  Exporting ${punch_id} ..."
    PUNCH_CAE="$cae" PUNCH_DIR="${EULER_DIR}/PiP_Punches" \
    xvfb-run -a abaqus cae noGUI="${EULER_DIR}/screenshot_punches.py" \
        || echo "  WARNING: export failed for ${punch_id}"
done
echo "Done. Files are in ${EULER_DIR}/PiP_Punches/"
