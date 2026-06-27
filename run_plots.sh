#!/bin/bash
# =============================================================
# run_plots.sh  —  Unified SLURM plotting job.
#                  Replaces run_flc.sh and run_plot.sh.
#
# Submitted automatically by the deploy/submit scripts, usually with
# --dependency=afterok:<jobid>.  Mode is the first positional argument:
#
#   sbatch run_plots.sh flc       # per-specimen plots + FLC PDF; dirs from $OUTPUT_DIRS
#   sbatch run_plots.sh results   # per-specimen plots + FLC PDF; dirs from $WIDTHS (scratch)
#
# Per-mode env vars (injected via --export):
#   flc     : OUTPUT_DIRS (colon-sep subdir names rel. to PROJ_DIR), FLC_OUTDIR,
#             TEST_TYPE, BLANK_THICKNESS, MATERIAL_ORIENTATION_ANGLE
#   results : WIDTHS, TEST_TYPE, BLANK_THICKNESS, MATERIAL_ORIENTATION_ANGLE
# =============================================================

#SBATCH --job-name=run_plots
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem-per-cpu=4G
#SBATCH --time=00:30:00
#SBATCH --partition=normal.4h

set -e

MODE="${1:-}"
if [[ -z "$MODE" ]]; then
    echo "usage: sbatch run_plots.sh <flc|results>"
    exit 1
fi

module load stack/2024-06
module load python/3.11.6

PROJ_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
python3 -c "import matplotlib" 2>/dev/null || pip install --user matplotlib

# Resolve TEST_TYPE / thickness / orientation from env or config.py (flc, results).
_resolve_params() {
    TEST_TYPE=${TEST_TYPE:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(config.TEST_TYPE)")}
    THICKNESS=${BLANK_THICKNESS:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(config.BLANK_THICKNESS)")}
    ORIENTATION=${MATERIAL_ORIENTATION_ANGLE:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(int(config.MATERIAL_ORIENTATION_ANGLE))")}
    _t=$(python3 -c "print(str(${THICKNESS}).replace('.','p'))")
    _test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
    _ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")
}

echo "=============================================="
echo "  run_plots.sh — mode: ${MODE}"
echo "  Start : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

case "$MODE" in

  flc)
    # Per-specimen plots + FLC aggregation; dirs given explicitly as $OUTPUT_DIRS
    # (submitted after the solver job by deploy.sh / submit_one.sh).
    _resolve_params
    echo "  Test type=${TEST_TYPE}  t=${THICKNESS} mm  ang=${ORIENTATION} deg"
    DIRS=""
    IFS=':' read -ra DIR_NAMES <<< "$OUTPUT_DIRS"
    for D in "${DIR_NAMES[@]}"; do
        FULL="${PROJ_DIR}/${D}"
        if [ -d "$FULL" ]; then DIRS="$DIRS $FULL"; else echo "  WARNING: not found: $FULL — skipping."; fi
    done
    [ -z "$DIRS" ] && { echo "  ERROR: no valid output directories found."; exit 1; }

    echo "--- Per-specimen plots ---"
    python3 "${PROJ_DIR}/plot_results.py" $DIRS
    if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]]; then
        echo "--- FLC aggregation ---"
        mkdir -p "${PROJ_DIR}/${FLC_OUTDIR}"
        FLC_PDF="${PROJ_DIR}/${FLC_OUTDIR}/FLC_${TEST_TYPE}.pdf"
        python3 "${PROJ_DIR}/plot_flc.py" $DIRS --output "$FLC_PDF"
        echo "  FLC: ${FLC_PDF}"
    else
        echo "  FLC aggregation skipped for test type: ${TEST_TYPE}"
    fi
    ;;

  results)
    # Per-specimen plots + FLC aggregation; dirs derived from $WIDTHS on scratch
    # (submitted after a postproc-only rerun by submit_postproc.sh).
    _resolve_params
    WIDTHS=${WIDTHS:-"20 50 80 90 100 120 200"}
    echo "  Test type=${TEST_TYPE}  t=${THICKNESS} mm  ang=${ORIENTATION} deg  widths=${WIDTHS}"
    DIRS=""
    for W in ${WIDTHS}; do
        JOB_NAME="${_test_cap}_W${W}_t${_t}_ang${_ang}"
        ODB_DIR="/cluster/scratch/acruzfaria/${JOB_NAME}"
        if [ -d "$ODB_DIR" ]; then DIRS="$DIRS $ODB_DIR"; else echo "  WARNING: not found: $ODB_DIR — skipping."; fi
    done
    [ -z "$DIRS" ] && { echo "  ERROR: no valid output directories found."; exit 1; }

    python3 "${PROJ_DIR}/plot_results.py" $DIRS
    FLC_OUT="${PROJ_DIR}/FLC_${TEST_TYPE}_t${_t}_ang${_ang}.pdf"
    python3 "${PROJ_DIR}/plot_flc.py" $DIRS --output "$FLC_OUT"
    echo "  FLC: ${FLC_OUT}"
    ;;

  *)
    echo "  ERROR: unknown mode '$MODE' (expected flc|results)"; exit 1 ;;
esac

echo "=============================================="
echo "  Done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
