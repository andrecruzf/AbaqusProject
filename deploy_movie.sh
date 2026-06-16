#!/bin/bash
# =============================================================
# deploy_movie.sh  —  Push postproc_movie.py and submit the
#                     EQPS animation job on Euler.
#
# Usage (from your Mac):
#   ./deploy_movie.sh <JOB_NAME>
#   ./deploy_movie.sh Nakazima_W50_t1p5_ang0
#
# The .webm is written to:
#   /cluster/home/acruzfaria/AbaqusProject/<JOB_NAME>/<JOB_NAME>_movie.webm
# =============================================================

set -e

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 1. Resolve JOB_NAME ───────────────────────────────────────────────────────
JOB_NAME="$1"

if [ -z "$JOB_NAME" ]; then
    echo "Usage: $0 <JOB_NAME>"
    echo ""
    echo "Available jobs on Euler (scratch):"
    ssh "${EULER_USER}@${EULER_HOST}" \
        "ls /cluster/scratch/acruzfaria/ 2>/dev/null | grep -v '^$' | sort" \
        2>/dev/null || echo "  (could not list)"
    exit 1
fi

echo "=============================================="
echo "  deploy_movie.sh — EQPS animation"
echo "  Job : $JOB_NAME"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── 2. Push scripts ───────────────────────────────────────────────────────────
echo "  Pushing postproc_movie.py + run_movie.sh ..."
scp -q \
    "$SCRIPT_DIR/postproc_movie.py" \
    "$SCRIPT_DIR/run_movie.sh" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
echo "  Done."

# ── 3. Submit SLURM job ───────────────────────────────────────────────────────
echo "  Submitting SLURM job ..."
JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" \
    "cd ${EULER_DIR} && sbatch \
     --job-name=movie_${JOB_NAME} \
     --export=ALL,JOB_NAME=${JOB_NAME} \
     --parsable run_movie.sh")

echo "=============================================="
echo "  SLURM job : $JOB_ID"
echo ""
echo "  Watch log:"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'tail -f ${EULER_DIR}/movie_${JOB_NAME}_${JOB_ID}.out'"
echo ""
echo "  Download once done:"
echo "    scp ${EULER_USER}@${EULER_HOST}:${EULER_DIR}/${JOB_NAME}/${JOB_NAME}_movie.webm ."
echo "=============================================="
