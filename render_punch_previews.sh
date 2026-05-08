#!/bin/bash
# =============================================================
# render_punch_previews.sh  —  Render PNG previews for all punches.
# Run ON Euler (from AbaqusProject/):
#   bash render_punch_previews.sh
# =============================================================
set -e
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"
module load abaqus/2023

cd "${EULER_DIR}"
for cae in "${EULER_DIR}/PiP_Punches"/PUNCH_*.cae; do
    punch_id=$(basename "$cae" .cae)
    out_stl="${EULER_DIR}/PiP_Punches/${punch_id}.stl"
    if [ -f "$out_stl" ]; then
        echo "  Skipping ${punch_id} (already exported)"
        continue
    fi
    echo "  Rendering ${punch_id} ..."
    PUNCH_CAE="$cae" PUNCH_DIR="${EULER_DIR}/PiP_Punches" \
    xvfb-run -a abaqus cae noGUI="${EULER_DIR}/screenshot_punches.py" \
        || echo "  WARNING: render failed for ${punch_id}"
done
echo "Done. PNGs are in ${EULER_DIR}/PiP_Punches/"
