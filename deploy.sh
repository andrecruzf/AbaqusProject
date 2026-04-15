#!/bin/bash
# =============================================================
# deploy.sh  —  Push config.py, build model on login node, submit solver job
# Run this from your local Mac:
#   ./deploy.sh
# =============================================================

set -e

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================================="
echo "  deploy.sh — push + build + submit"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── 1. Read parameters (env override or config.py defaults) ───
TEST_TYPE=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.TEST_TYPE)")
THICKNESS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.BLANK_THICKNESS)")
ORIENTATION=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(int(config.MATERIAL_ORIENTATION_ANGLE))")
SPECIMEN_WIDTH=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.SPECIMEN_WIDTH)")
PIP_PUNCH2_ID=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'PIP_PUNCH2_ID', '') or '')")
PIP_PUNCH_CAE=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'PIP_PUNCH_CAE', '') or '')")

echo "  Pushing scripts and modules ..."
scp "$SCRIPT_DIR/config.py" \
    "$SCRIPT_DIR/build_model.py" \
    "$SCRIPT_DIR/run_cluster.sh" \
    "$SCRIPT_DIR/postproc.py" \
    "$SCRIPT_DIR/postproc_movie.py" \
    "$SCRIPT_DIR/VUMAT_explicit.f" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
scp -r "$SCRIPT_DIR/modules" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"

# ── Push inner punch CAE if PiP with file-based punch ─────────
if [ "$TEST_TYPE" = "pip" ] && [ -n "$PIP_PUNCH2_ID" ]; then
    if [ -f "$SCRIPT_DIR/$PIP_PUNCH_CAE" ]; then
        echo "  Pushing inner punch CAE: ${PIP_PUNCH_CAE} ..."
        scp "$SCRIPT_DIR/$PIP_PUNCH_CAE" "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/${PIP_PUNCH_CAE}"
    else
        echo "  WARNING: punch CAE not found locally: $SCRIPT_DIR/$PIP_PUNCH_CAE"
    fi
fi
echo "  Done."

# ── 2. Build model on login node ──────────────────────────────
echo "  Building model on login node ..."
ssh "${EULER_USER}@${EULER_HOST}" "cd ${EULER_DIR} && module load abaqus/2023 && \
    TEST_TYPE=${TEST_TYPE} \
    SPECIMEN_WIDTH=${SPECIMEN_WIDTH} \
    BLANK_THICKNESS=${THICKNESS} \
    MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
    PIP_PUNCH2_ID=${PIP_PUNCH2_ID} \
    abaqus cae noGUI=build_model.py"
echo "  Build done."

# ── 3. Submit solver job ──────────────────────────────────────
echo "  Submitting solver job ..."
JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" "cd ${EULER_DIR} && source last_build.env && sbatch --job-name=\$JOB_NAME --export=ALL,JOB_NAME=\$JOB_NAME,OUTPUT_SUBDIR=\$OUTPUT_SUBDIR --parsable run_cluster.sh")
echo "=============================================="
echo "  Job submitted: $JOB_ID"
echo "  Monitor with:"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'squeue -j ${JOB_ID}'"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'tail -f ${EULER_DIR}/nakazima_${JOB_ID}.out'"
echo "=============================================="
