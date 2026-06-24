#!/bin/bash
# =============================================================
# run_plot.sh  —  Generate PNGs from post-processing CSVs.
#
# Submitted automatically by submit_postproc.sh with
# --dependency=afterok:<postproc_job_id>
#
# Reads the same TEST_TYPE / BLANK_THICKNESS / WIDTHS env vars
# as run_postproc.sh so both jobs process the same set of ODBs.
# =============================================================

#SBATCH --job-name=plot_results
#SBATCH --output=plot_results_%j.out
#SBATCH --error=plot_results_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=4G
#SBATCH --time=00:15:00

set -e

module load stack/2024-06
module load python/3.11.6

PROJ_DIR="$SLURM_SUBMIT_DIR"

# ── Ensure matplotlib is available (installs once to ~/.local) ─
python3 -c "import matplotlib" 2>/dev/null || pip install --user matplotlib

# ── Resolve parameters ─────────────────────────────────────────
TEST_TYPE=${TEST_TYPE:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(config.TEST_TYPE)")}
THICKNESS=${BLANK_THICKNESS:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(config.BLANK_THICKNESS)")}
ORIENTATION=${MATERIAL_ORIENTATION_ANGLE:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(int(config.MATERIAL_ORIENTATION_ANGLE))")}

_t=$(python3 -c "print(str(${THICKNESS}).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")

WIDTHS=${WIDTHS:-"20 50 80 90 100 120 200"}

echo "=============================================="
echo "  run_plot.sh"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Widths      : ${WIDTHS}"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

DIRS=""
for W in ${WIDTHS}; do
    JOB_NAME="${_test_cap}_W${W}_t${_t}_ang${_ang}"
    ODB_DIR="/cluster/scratch/acruzfaria/${JOB_NAME}"

    if [ ! -d "$ODB_DIR" ]; then
        echo "  WARNING: directory not found: $ODB_DIR — skipping."
        continue
    fi

    DIRS="$DIRS $ODB_DIR"
done

if [ -z "$DIRS" ]; then
    echo "  ERROR: no valid output directories found."
    exit 1
fi

# Per-specimen diagnostic plots
python3 "${PROJ_DIR}/plot_results.py" $DIRS

# FLC aggregated across all specimens
FLC_OUT="${PROJ_DIR}/FLC_${TEST_TYPE}_t${_t}_ang${_ang}.pdf"
python3 "${PROJ_DIR}/plot_flc.py" $DIRS --output "$FLC_OUT"

echo ""
echo "=============================================="
echo "  Plots done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  FLC: ${FLC_OUT}"
echo "=============================================="
