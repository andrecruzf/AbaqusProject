#!/bin/bash
# =============================================================
# deploy_all.sh  —  Push scripts, build all models, submit solver
#                   jobs, then submit FLC aggregation job.
#
# Usage:
#   ./deploy_all.sh                            # all defaults from config.py
#   ./deploy_all.sh marciniak                  # override test type
#   ./deploy_all.sh marciniak 1.5              # override test type + thickness
#   ./deploy_all.sh marciniak 1.5 45           # + orientation angle (degrees)
#   ./deploy_all.sh marciniak 1.5 45 50 80 100 # + specific widths
#
# All defaults are read from config.py — edit only config.py to change them.
# =============================================================

set -e

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Read defaults from config.py ──────────────────────────────────────────────
DEFAULT_TEST_TYPE=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.TEST_TYPE)")
DEFAULT_THICKNESS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.BLANK_THICKNESS)")
DEFAULT_ORIENTATION=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(int(config.MATERIAL_ORIENTATION_ANGLE))")
DEFAULT_R_DOME=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.R_DOME)")

TEST_TYPE=${1:-$DEFAULT_TEST_TYPE}
THICKNESS=${2:-$DEFAULT_THICKNESS}
ORIENTATION=${3:-$DEFAULT_ORIENTATION}
shift 3 || true
WIDTHS=("${@}")
if [ ${#WIDTHS[@]} -eq 0 ]; then
    WIDTHS=(20 50 80 90 100 120 200)
fi

# Derived name components (computed once, used in loop and FLC job)
_t=$(python3 -c "print(str(${THICKNESS}).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")
FLC_OUTDIR="FLC_${TEST_TYPE}_t${_t}_ang${_ang}"

echo "=============================================="
echo "  deploy_all.sh — build + submit all widths"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Widths      : ${WIDTHS[*]}"
echo "  FLC output  : ${FLC_OUTDIR}/"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── Push scripts once ─────────────────────────────────────────────────────────
echo "  Pushing scripts to Euler ..."
scp "$SCRIPT_DIR/config.py" \
    "$SCRIPT_DIR/run_cluster.sh" \
    "$SCRIPT_DIR/run_flc.sh" \
    "$SCRIPT_DIR/postproc.py" \
    "$SCRIPT_DIR/postproc_movie.py" \
    "$SCRIPT_DIR/flc_plot.py" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
echo "  Done."
echo ""

# ── Build each model + submit solver job ──────────────────────────────────────
JOB_IDS=()
OUTPUT_DIRS=()

for W in "${WIDTHS[@]}"; do
    echo "----------------------------------------------"
    JOB_NAME="${_test_cap}_W${W}_t${_t}_ang${_ang}"
    OUTPUT_SUBDIR="$JOB_NAME"

    echo "  Building ${JOB_NAME} on login node ..."
    ssh "${EULER_USER}@${EULER_HOST}" \
        "cd ${EULER_DIR} && module load abaqus/2023 && \
         TEST_TYPE=${TEST_TYPE} \
         SPECIMEN_WIDTH=${W} \
         BLANK_THICKNESS=${THICKNESS} \
         MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
         abaqus cae noGUI=build_model.py"

    echo "  Submitting solver job ..."
    JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" \
        "cd ${EULER_DIR} && sbatch \
         --job-name=${JOB_NAME} \
         --export=ALL,JOB_NAME=${JOB_NAME},OUTPUT_SUBDIR=${OUTPUT_SUBDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION},R_DOME=${DEFAULT_R_DOME} \
         --parsable run_cluster.sh")

    JOB_IDS+=("$JOB_ID")
    OUTPUT_DIRS+=("$OUTPUT_SUBDIR")
    echo "  ${JOB_NAME} → SLURM job ${JOB_ID}"
    echo ""
done

# ── Submit FLC aggregation job (runs after all solver jobs succeed) ────────────
DEPENDENCY="afterok:$(IFS=:; echo "${JOB_IDS[*]}")"
DIRS_STR="$(IFS=:; echo "${OUTPUT_DIRS[*]}")"

echo "----------------------------------------------"
echo "  Submitting FLC aggregation job ..."
echo "  Dependency  : ${DEPENDENCY}"
FLC_JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" \
    "cd ${EULER_DIR} && sbatch \
     --dependency=${DEPENDENCY} \
     --job-name=FLC_${TEST_TYPE}_ang${_ang} \
     --export=ALL,OUTPUT_DIRS=${DIRS_STR},FLC_OUTDIR=${FLC_OUTDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
     --parsable run_flc.sh")
echo "  FLC job → SLURM job ${FLC_JOB_ID} (held until all solver jobs complete)"
echo ""

echo "=============================================="
echo "  All jobs submitted."
echo "  Sim jobs    : ${JOB_IDS[*]}"
echo "  FLC job     : ${FLC_JOB_ID}"
echo "  FLC diagram : ${EULER_DIR}/${FLC_OUTDIR}/flc_diagram.png"
echo "  Monitor     : ssh ${EULER_USER}@${EULER_HOST} 'squeue --me'"
echo "=============================================="
