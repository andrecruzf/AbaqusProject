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

# ── 1. Push scripts ───────────────────────────────────────────
echo "  Pushing config.py, run_cluster.sh, postproc.py, postproc_movie.py ..."
scp "$SCRIPT_DIR/config.py" \
    "$SCRIPT_DIR/run_cluster.sh" \
    "$SCRIPT_DIR/postproc.py" \
    "$SCRIPT_DIR/postproc_movie.py" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
echo "  Done."

# ── 2. Build model on login node ──────────────────────────────
echo "  Building model on login node ..."
ssh "${EULER_USER}@${EULER_HOST}" "cd ${EULER_DIR} && module load abaqus/2023 && abaqus cae noGUI=build_model.py"
echo "  Build done."

# ── 3. Submit solver job ──────────────────────────────────────
echo "  Submitting solver job ..."
JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" "cd ${EULER_DIR} && source last_build.env && sbatch --export=ALL,JOB_NAME=\$JOB_NAME,OUTPUT_SUBDIR=\$OUTPUT_SUBDIR --parsable run_cluster.sh")
echo "=============================================="
echo "  Job submitted: $JOB_ID"
echo "  Monitor with:"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'squeue -j ${JOB_ID}'"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'tail -f ${EULER_DIR}/nakazima_${JOB_ID}.out'"
echo "=============================================="
