#!/bin/bash
# =============================================================
# deploy_mass_scaling.sh  —  Run one geometry with multiple mass-scaling
#                            values to study mass-scaling sensitivity.
#
# Usage:
#   ./deploy_mass_scaling.sh <width> <test_type> <thickness> <orientation> <dt1> [dt2 ...]
#
# Wall time is taken from run_cluster.sh unchanged for all DT values.
# Finer DT finishes earlier; coarser DT uses less of the allocation — both fine.
#
# Example:
#   ./deploy_mass_scaling.sh 100 nakazima 1.85 0 1e-5 2e-5 5e-5 1e-4
# =============================================================

set -e

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$#" -lt 5 ]; then
    echo "Usage: $0 <width> <test_type> <thickness> <orientation> <dt1> [dt2 ...]"
    echo "Example: $0 100 nakazima 1.85 0 1e-5 2e-5 5e-5 1e-4"
    exit 1
fi

WIDTH=$1;       shift
TEST_TYPE=$1;   shift
THICKNESS=$1;   shift
ORIENTATION=$1; shift
DT_VALUES=("$@")

_t=$(python3 -c "print(str(float(${THICKNESS})).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")

echo "=============================================="
echo "  deploy_mass_scaling.sh"
echo "  Geometry  : ${_test_cap} W${WIDTH} t=${THICKNESS} mm ang=${ORIENTATION} deg"
echo "  DT values : ${DT_VALUES[*]}"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── Push scripts once ─────────────────────────────────────────
echo "  Pushing scripts ..."
scp "$SCRIPT_DIR/config.py" \
    "$SCRIPT_DIR/build_model.py" \
    "$SCRIPT_DIR/run_cluster.sh" \
    "$SCRIPT_DIR/run_flc.sh" \
    "$SCRIPT_DIR/run_mass_scaling_plot.sh" \
    "$SCRIPT_DIR/postproc.py" \
    "$SCRIPT_DIR/postproc_movie.py" \
    "$SCRIPT_DIR/plot_results.py" \
    "$SCRIPT_DIR/plot_flc.py" \
    "$SCRIPT_DIR/plot_mass_scaling.py" \
    "$SCRIPT_DIR/VUMAT_explicit.f" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
scp -r "$SCRIPT_DIR/modules" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
echo "  Done."
echo ""

# ── Pre-clean all stale lock files for this geometry ──────────
echo "  Cleaning stale lock files ..."
ssh "${EULER_USER}@${EULER_HOST}" \
    "find /cluster/scratch/${EULER_USER} -name '*.lck' -path '*${_test_cap}_W${WIDTH}_t${_t}_ang${_ang}*' -delete 2>/dev/null; echo '  done'"

# ── Build + submit one job per DT value ───────────────────────
JOB_IDS=()
JOB_NAMES=()
SOLVER_IDS=()   # solver IDs only — used for the final aggregation dependency

for DT in "${DT_VALUES[@]}"; do

    MS_LABEL=$(python3 -c "
import math
v    = float('${DT}')
exp  = int(math.floor(math.log10(v)))
mant = int(round(v / 10**exp))
print('_ms%de%d' % (mant, abs(exp)))
")
    JOB_NAME="${_test_cap}_W${WIDTH}_t${_t}_ang${_ang}${MS_LABEL}"

    echo "----------------------------------------------"
    echo "  DT = ${DT} s  →  ${JOB_NAME}"

    echo "  Building model ..."
    # MASS_SCALING_DT is injected into the .inp by job.py; config.py keeps a
    # fixed default so job names stay clean — we name the output ourselves.
    ssh "${EULER_USER}@${EULER_HOST}" \
        "cd ${EULER_DIR} && module load abaqus/2023 && \
         TEST_TYPE=${TEST_TYPE} \
         SPECIMEN_WIDTH=${WIDTH} \
         BLANK_THICKNESS=${THICKNESS} \
         MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
         MASS_SCALING_DT=${DT} \
         abaqus cae noGUI=build_model.py"

    # Remove stale lock file if present (left by cancelled/failed previous runs)
    ssh "${EULER_USER}@${EULER_HOST}" \
        "rm -f /cluster/scratch/${EULER_USER}/${JOB_NAME}/${JOB_NAME}.lck" 2>/dev/null || true

    echo "  Submitting solver ..."
    # JOB_NAME and OUTPUT_SUBDIR are passed explicitly with the _ms suffix so
    # each DT value produces its own output directory, independent of config.py.
    JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" \
        "cd ${EULER_DIR} && sbatch \
         --job-name=${JOB_NAME} \
         --export=ALL,JOB_NAME=${JOB_NAME},OUTPUT_SUBDIR=${JOB_NAME} \
         --parsable run_cluster.sh")

    echo "  Submitting plot job (afterok:${JOB_ID}) ..."
    PLOT_ID=$(ssh "${EULER_USER}@${EULER_HOST}" \
        "cd ${EULER_DIR} && sbatch \
         --dependency=afterok:${JOB_ID} \
         --job-name=plot_${JOB_NAME} \
         --export=ALL,OUTPUT_DIRS=${JOB_NAME},FLC_OUTDIR=,TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
         --parsable run_flc.sh")

    JOB_IDS+=("${JOB_ID}:${PLOT_ID}")
    JOB_NAMES+=("$JOB_NAME")
    SOLVER_IDS+=("${JOB_ID}")
    echo "  Solver: ${JOB_ID}   Plot: ${PLOT_ID}"
    echo ""
done

# ── Final mass-scaling comparison plot (depends on ALL solvers) ───────────────
DEPENDENCY_STR=$(IFS=':'; echo "afterok:${SOLVER_IDS[*]}")
ALL_DIRS=$(IFS=' '; echo "${EULER_DIR}/${JOB_NAMES[*]// / ${EULER_DIR}/}")
MS_PDF="${EULER_DIR}/mass_scaling_${_test_cap}_W${WIDTH}_t${_t}_ang${_ang}.pdf"

echo "  Submitting mass-scaling comparison plot (after all solvers) ..."
AGG_ID=$(ssh "${EULER_USER}@${EULER_HOST}" \
    "cd ${EULER_DIR} && sbatch \
     --dependency=${DEPENDENCY_STR} \
     --job-name=ms_compare_${_test_cap}_W${WIDTH} \
     --export=ALL,MS_DIRS='${ALL_DIRS}',MS_PDF='${MS_PDF}' \
     --parsable run_mass_scaling_plot.sh")
echo "  Comparison plot job: ${AGG_ID}"
echo ""

echo "=============================================="
echo "  All jobs submitted:"
for i in "${!JOB_NAMES[@]}"; do
    IFS=':' read -r SID PID <<< "${JOB_IDS[$i]}"
    printf "  %-45s  solver %-10s  plot %s\n" "${JOB_NAMES[$i]}" "$SID" "$PID"
done
printf "  %-45s  comparison %s\n" "(all DT values)" "$AGG_ID"
echo ""
echo "  Output: ${MS_PDF}"
echo ""
echo "  Monitor:"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'squeue --me'"
echo "=============================================="
