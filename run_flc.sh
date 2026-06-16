#!/bin/bash
# =============================================================
# run_flc.sh  —  Per-specimen diagnostic plots + FLC aggregation.
#
# Submitted automatically by deploy_all.sh with
#   --dependency=afterok:<all_sim_job_ids>
# Do NOT submit this script manually.
#
# Required env vars (injected via --export in deploy_all.sh):
#   OUTPUT_DIRS   : colon-separated output subdir names (relative to EULER_DIR)
#   FLC_OUTDIR    : subdir name for the aggregated FLC PDF
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
module load python/3.11.6

python3 -c "import matplotlib" 2>/dev/null || pip install --user matplotlib

PROJ_DIR="$SLURM_SUBMIT_DIR"

echo "=============================================="
echo "  run_flc.sh — plots + FLC aggregation"
echo "  Test type   : $TEST_TYPE"
echo "  Thickness   : $BLANK_THICKNESS mm"
echo "  Orientation : $MATERIAL_ORIENTATION_ANGLE deg"
echo "  Start       : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# Convert colon-separated OUTPUT_DIRS to space-separated full paths
DIRS=""
IFS=':' read -ra DIR_NAMES <<< "$OUTPUT_DIRS"
for D in "${DIR_NAMES[@]}"; do
    FULL="${PROJ_DIR}/${D}"
    if [ -d "$FULL" ]; then
        DIRS="$DIRS $FULL"
    else
        echo "  WARNING: directory not found: $FULL — skipping."
    fi
done

if [ -z "$DIRS" ]; then
    echo "  ERROR: no valid output directories found."
    exit 1
fi

# ── Per-specimen diagnostic plots ─────────────────────────────
echo ""
echo "--- Per-specimen plots ---"
python3 "${PROJ_DIR}/plot_results.py" $DIRS

# ── Aggregated FLC (nakazima / marciniak only) ────────────────
if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]]; then
    echo ""
    echo "--- FLC aggregation ---"
    mkdir -p "${PROJ_DIR}/${FLC_OUTDIR}"
    FLC_PDF="${PROJ_DIR}/${FLC_OUTDIR}/FLC_${TEST_TYPE}.pdf"
    python3 "${PROJ_DIR}/plot_flc.py" $DIRS --output "$FLC_PDF"
    echo "  FLC: ${FLC_PDF}"
else
    echo "  FLC aggregation skipped for test type: ${TEST_TYPE}"
fi

echo ""
echo "=============================================="
echo "  Done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
