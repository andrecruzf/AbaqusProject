#!/bin/bash
# =============================================================
# submit_all.sh  —  Build all models and submit solver jobs.
#                   Runs ON Euler — do not run locally.
#                   Launched by deploy_all.sh via SSH + tmux.
#
# Args: TEST_TYPE THICKNESS ORIENTATION R_DOME PIP_PUNCH2_ID CUSTOM_WIDTHS [WIDTHS...]
#   PIP_PUNCH2_ID: pass "none" if empty
# =============================================================

set -e

EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

TEST_TYPE=$1
THICKNESS=$2
ORIENTATION=$3
R_DOME=$4
PIP_PUNCH2_ID=$5
[ "$PIP_PUNCH2_ID" = "none" ] && PIP_PUNCH2_ID=""
CUSTOM_WIDTHS=$6
shift 6
WIDTHS=("$@")

# Derived name components
_t=$(python3 -c "print(str(float(${THICKNESS})).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")
if [ "$TEST_TYPE" = "pip" ] && [ -n "$PIP_PUNCH2_ID" ]; then
    _pip_suffix="_p2$(echo "$PIP_PUNCH2_ID" | sed 's/PUNCH_//')"
else
    _pip_suffix=""
fi
FLC_OUTDIR="FLC_${TEST_TYPE}_t${_t}_ang${_ang}"

module load abaqus/2023

echo "=============================================="
echo "  submit_all.sh — build + submit all widths"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Widths      : ${WIDTHS[*]}"
if [ "$TEST_TYPE" = "pip" ]; then
    echo "  Punch2      : ${PIP_PUNCH2_ID:-PUNCH_21 (default)}"
fi
if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]] && [ "$CUSTOM_WIDTHS" = false ]; then
    echo "  FLC output  : ${FLC_OUTDIR}/"
fi
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

JOB_IDS=()
OUTPUT_DIRS=()

for W in "${WIDTHS[@]}"; do
    echo "----------------------------------------------"
    JOB_NAME="${_test_cap}_W${W}_t${_t}_ang${_ang}${_pip_suffix}"
    OUTPUT_SUBDIR="$JOB_NAME"

    echo "  Building ${JOB_NAME} ..."
    cd "${EULER_DIR}"
    TEST_TYPE=${TEST_TYPE} \
    SPECIMEN_WIDTH=${W} \
    BLANK_THICKNESS=${THICKNESS} \
    MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
    PIP_PUNCH2_ID=${PIP_PUNCH2_ID} \
    abaqus cae noGUI=build_model.py

    echo "  Submitting solver job ..."
    JOB_ID=$(cd "${EULER_DIR}" && sbatch \
        --job-name=${JOB_NAME} \
        --export=ALL,JOB_NAME=${JOB_NAME},OUTPUT_SUBDIR=${OUTPUT_SUBDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION},R_DOME=${R_DOME} \
        --parsable run_cluster.sh)

    JOB_IDS+=("$JOB_ID")
    OUTPUT_DIRS+=("$OUTPUT_SUBDIR")
    echo "  ${JOB_NAME} → SLURM job ${JOB_ID}"
    echo ""
done

echo "=============================================="
echo "  All jobs submitted."
echo "  Sim jobs    : ${JOB_IDS[*]}"

if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]] && [ "$CUSTOM_WIDTHS" = false ]; then
    DEPENDENCY="afterok:$(IFS=:; echo "${JOB_IDS[*]}")"
    DIRS_STR="$(IFS=:; echo "${OUTPUT_DIRS[*]}")"

    echo "----------------------------------------------"
    echo "  Submitting FLC aggregation job ..."
    echo "  Dependency  : ${DEPENDENCY}"
    FLC_JOB_ID=$(cd "${EULER_DIR}" && sbatch \
        --dependency=${DEPENDENCY} \
        --job-name=FLC_${TEST_TYPE}_ang${_ang} \
        --export=ALL,OUTPUT_DIRS=${DIRS_STR},FLC_OUTDIR=${FLC_OUTDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
        --parsable run_flc.sh)
    echo "  FLC job     : ${FLC_JOB_ID} (held until all solver jobs complete)"
    echo "  FLC diagram : ${EULER_DIR}/${FLC_OUTDIR}/flc_diagram.png"
else
    echo "  FLC job     : skipped (test=${TEST_TYPE}, custom_widths=${CUSTOM_WIDTHS})"
fi

echo "  $(date '+%Y-%m-%d %H:%M:%S') — done"
echo "=============================================="
