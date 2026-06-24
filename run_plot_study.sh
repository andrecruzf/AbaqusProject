#!/bin/bash
# =============================================================
# run_plot_study.sh  —  SLURM wrapper for plot_study.py.
#                       Submitted by submit_study.sh with
#                       --export=ALL,STUDY_DIR=<path>
# =============================================================

#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem-per-cpu=4G
#SBATCH --time=00:30:00
#SBATCH --partition=normal.4h

set -e

module load stack/2024-06
module load python/3.11.6

EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

echo "=============================================="
echo "  plot_study.py — sensitivity study analysis"
echo "  Study dir : ${STUDY_DIR}"
echo "  Start     : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

python3 "$EULER_DIR/plot_study.py" "$STUDY_DIR"

echo "  Done      : $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Results   : ${STUDY_DIR}/study_results.pdf"
echo "=============================================="
