#!/bin/bash
# =============================================================
# run_flc.sh  —  SLURM aggregation job: strain paths → FLC diagram
#
# Submitted automatically by deploy_all.sh with
#   --dependency=afterok:<all_sim_job_ids>
# Do NOT submit this script manually.
#
# Required env vars (injected via --export in deploy_all.sh):
#   OUTPUT_DIRS                : colon-separated output subdir names
#   FLC_OUTDIR                 : directory to save flc_diagram.png
#   TEST_TYPE, BLANK_THICKNESS, MATERIAL_ORIENTATION_ANGLE
# =============================================================

#SBATCH --job-name=FLC_plot
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=4G
#SBATCH --time=00:15:00

set -e

module load stack/2024-06
module load python

cd "$SLURM_SUBMIT_DIR"

echo "=============================================="
echo "  run_flc.sh — FLC aggregation"
echo "  Test type   : $TEST_TYPE"
echo "  Thickness   : $BLANK_THICKNESS mm"
echo "  Orientation : $MATERIAL_ORIENTATION_ANGLE deg"
echo "  Output dirs : $OUTPUT_DIRS"
echo "  FLC out     : $FLC_OUTDIR"
echo "  Start       : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

EULER_DIR="$SLURM_SUBMIT_DIR" python3 flc_plot.py

echo "  Done: $(date '+%Y-%m-%d %H:%M:%S')"
