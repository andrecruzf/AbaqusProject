#!/bin/bash
# =============================================================
# deploy.sh  —  Push config.py to Euler and submit the job
# Run this from your local Mac:
#   ./deploy.sh
# =============================================================

set -e

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================================="
echo "  deploy.sh — push + submit"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── 1. Push config.py ─────────────────────────────────────────
echo "  Pushing config.py ..."
scp "$SCRIPT_DIR/config.py" "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
echo "  Done."

# ── 2. Submit job on Euler ────────────────────────────────────
echo "  Submitting job ..."
JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" "cd ${EULER_DIR} && sbatch --parsable run_cluster.sh")
echo "=============================================="
echo "  Job submitted: $JOB_ID"
echo "  Monitor with:"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'squeue -j ${JOB_ID}'"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'tail -f ${EULER_DIR}/nakazima_${JOB_ID}.out'"
echo "=============================================="
