#!/bin/bash
# =============================================================
# run_movie.sh  —  SLURM batch script: render EQPS animation
#
# Submitted by deploy_movie.sh with:
#   --export=ALL,JOB_NAME=<name>
# =============================================================

#SBATCH --job-name=movie
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem-per-cpu=4G
#SBATCH --time=02:00:00

set -e

module load stack/2024-06
module load abaqus/2023

EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"
SCRATCH_ODB="/cluster/scratch/acruzfaria/${JOB_NAME}/${JOB_NAME}.odb"
DEST_DIR="${EULER_DIR}/${JOB_NAME}"

echo "=============================================="
echo "  run_movie.sh — EQPS animation"
echo "  Job  : $JOB_NAME"
echo "  ODB  : $SCRATCH_ODB"
echo "  Start: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

if [ ! -f "$SCRATCH_ODB" ]; then
    echo "ERROR: ODB not found: $SCRATCH_ODB"
    exit 1
fi

mkdir -p "$DEST_DIR"
cd "$EULER_DIR"
ODB_PATH="$SCRATCH_ODB" xvfb-run -a abaqus cae noGUI="${EULER_DIR}/postproc_movie.py"

echo "  Abaqus done, copying outputs ..."
# Copy Python log (contains EQPS diagnostics from postproc_movie.py)
cp /tmp/postproc_movie_out.txt "$DEST_DIR/postproc_movie_out.txt" 2>/dev/null \
    && echo "  postproc_movie_out.txt -> $DEST_DIR" \
    || echo "  WARNING: log copy failed"
cat "$DEST_DIR/postproc_movie_out.txt" 2>/dev/null || true
cp "/cluster/scratch/acruzfaria/${JOB_NAME}/${JOB_NAME}_movie.webm" "$DEST_DIR/" \
    && echo "  ${JOB_NAME}_movie.webm -> $DEST_DIR" \
    || echo "  WARNING: webm copy failed"

echo "=============================================="
echo "  Done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
