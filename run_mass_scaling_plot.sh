#!/bin/bash
# =============================================================
# run_mass_scaling_plot.sh  —  Aggregate mass-scaling comparison PDF.
#
# Submitted automatically by deploy_mass_scaling.sh after all
# solver jobs complete.  Do NOT submit this script manually.
#
# Required env vars (injected via --export):
#   MS_DIRS   : space-separated absolute paths to output directories
#   MS_PDF    : absolute path for the output PDF
# =============================================================

#SBATCH --job-name=ms_compare
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=4G
#SBATCH --time=00:10:00

set -e

module load stack/2024-06
module load python/3.11.6

python3 -c "import matplotlib" 2>/dev/null || pip install --user matplotlib

PROJ_DIR="$SLURM_SUBMIT_DIR"

echo "=============================================="
echo "  run_mass_scaling_plot.sh"
echo "  Dirs : $MS_DIRS"
echo "  PDF  : $MS_PDF"
echo "  Start: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

python3 "${PROJ_DIR}/plot_mass_scaling.py" $MS_DIRS --output "$MS_PDF"

echo "  Done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
