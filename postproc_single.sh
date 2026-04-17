#!/bin/bash
# =============================================================
# postproc_single.sh  —  Run postproc + plot for ONE ODB.
#
# Usage (interactive, on cluster login node or from login shell):
#   bash postproc_single.sh <WIDTH>
#   bash postproc_single.sh 50
#   bash postproc_single.sh 50 marciniak 1.5 0
#
# Arguments:
#   $1  WIDTH              specimen width in mm (required)
#   $2  TEST_TYPE          nakazima|marciniak  (default: from config.py)
#   $3  BLANK_THICKNESS    e.g. 1.0            (default: from config.py)
#   $4  ORIENTATION        angle in degrees    (default: from config.py)
#
# Runs everything inline (no SLURM), outputs go to scratch.
# Plots are generated in the scratch dir and also copied to
# $PROJ_DIR/<JOB_NAME>/ if that directory exists.
# =============================================================

set -e

PROJ_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$1" ]; then
    echo "Usage: bash postproc_single.sh <WIDTH> [TEST_TYPE] [THICKNESS] [ORIENTATION]"
    exit 1
fi

W="$1"

# ── Resolve parameters ─────────────────────────────────────────
_cfg() { python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print($1)"; }

TEST_TYPE=${2:-$(_cfg config.TEST_TYPE)}
THICKNESS=${3:-$(_cfg config.BLANK_THICKNESS)}
ORIENTATION=${4:-$(_cfg "int(config.MATERIAL_ORIENTATION_ANGLE)")}
R_DOME=${R_DOME:-$(_cfg config.R_DOME)}

_t=$(python3 -c "print(str(${THICKNESS}).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")

JOB_NAME="${_test_cap}_W${W}_t${_t}_ang${_ang}"
ODB="/cluster/scratch/acruzfaria/${JOB_NAME}/${JOB_NAME}.odb"
SCRATCH_DIR="/cluster/scratch/acruzfaria/${JOB_NAME}"

echo "=============================================="
echo "  postproc_single.sh"
echo "  Job         : ${JOB_NAME}"
echo "  ODB         : ${ODB}"
echo "  R_DOME      : ${R_DOME} mm"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

if [ ! -f "$ODB" ]; then
    echo "ERROR: ODB not found: $ODB"
    exit 1
fi

# ── Load modules ───────────────────────────────────────────────
module load stack/2024-06
module load abaqus/2023

# ── Step 1: extract CSVs ───────────────────────────────────────
echo ""
echo "--- Step 1: extracting CSVs ---"
R_DOME=${R_DOME} abaqus python "${PROJ_DIR}/postproc.py" -- "$ODB"

# ── Step 2: generate plots ─────────────────────────────────────
echo ""
echo "--- Step 2: generating plots ---"
module load python/3.11.6
python3 -c "import matplotlib" 2>/dev/null || pip install --user matplotlib
python3 "${PROJ_DIR}/plot_results.py" "$SCRATCH_DIR"

# ── Copy all outputs back to project dir ──────────────────────
OUT_DIR="${PROJ_DIR}/${JOB_NAME}"
if [ -d "$OUT_DIR" ]; then
    echo ""
    echo "--- Copying outputs to ${OUT_DIR}/ ---"
    for f in strain_path.csv forming_limits.csv energy_data.csv postproc_plots.pdf; do
        [ -f "${SCRATCH_DIR}/${f}" ] \
            && cp "${SCRATCH_DIR}/${f}" "$OUT_DIR/" \
            && echo "  ${f} -> ${OUT_DIR}/" \
            || echo "  (${f} not found, skipped)"
    done
fi

echo ""
echo "=============================================="
echo "  Done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Plots: ${SCRATCH_DIR}/postproc_plots.pdf"
echo "=============================================="
