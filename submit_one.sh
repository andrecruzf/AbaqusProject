#!/bin/bash
# =============================================================
# submit_one.sh  —  Build one model and submit solver + plot jobs.
#                   Runs ON Euler — do not run locally.
#                   Launched by deploy.sh via SSH + tmux.
#
# Args: TEST_TYPE THICKNESS ORIENTATION SPECIMEN_WIDTH PIP_PUNCH2_ID
#   PIP_PUNCH2_ID: pass "none" if empty
# =============================================================

set -e

EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

TEST_TYPE=$1
THICKNESS=$2
ORIENTATION=$3
SPECIMEN_WIDTH=$4
PIP_PUNCH2_ID=$5
[ "$PIP_PUNCH2_ID" = "none" ] && PIP_PUNCH2_ID=""

# Derived name components
_t=$(python3 -c "print(str(float(${THICKNESS})).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")
if [ "$TEST_TYPE" = "pip" ] && [ -n "$PIP_PUNCH2_ID" ]; then
    _pip_suffix="_p2$(echo "$PIP_PUNCH2_ID" | sed 's/PUNCH_//')"
else
    _pip_suffix=""
fi

JOB_NAME="${_test_cap}_W${SPECIMEN_WIDTH}_t${_t}_ang${_ang}${_pip_suffix}"

echo "=============================================="
echo "  submit_one.sh — build + submit"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Width       : ${SPECIMEN_WIDTH} mm"
echo "  Job name    : ${JOB_NAME}"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

module load abaqus/2023

cd "${EULER_DIR}"

echo "  Building ${JOB_NAME} ..."
TEST_TYPE=${TEST_TYPE} \
SPECIMEN_WIDTH=${SPECIMEN_WIDTH} \
BLANK_THICKNESS=${THICKNESS} \
MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
PIP_PUNCH2_ID=${PIP_PUNCH2_ID} \
abaqus cae noGUI=build_model.py
echo "  Build done."

echo "  Submitting solver job ..."
JOB_ID=$(source last_build.env && sbatch \
    --job-name=${JOB_NAME} \
    --export=ALL,JOB_NAME=${JOB_NAME},OUTPUT_SUBDIR=${JOB_NAME} \
    --parsable run_cluster.sh)
echo "  Solver job: ${JOB_ID}"

if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]]; then
    FLC_OUTDIR="FLC_${TEST_TYPE}_t${_t}_ang${_ang}"
else
    FLC_OUTDIR=""
fi

echo "  Submitting plot job ..."
PLOT_ID=$(sbatch \
    --dependency=afterok:${JOB_ID} \
    --job-name=plot_${JOB_NAME} \
    --export=ALL,OUTPUT_DIRS=${JOB_NAME},FLC_OUTDIR=${FLC_OUTDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
    --parsable run_flc.sh)

echo "=============================================="
echo "  Solver job : ${JOB_ID}"
echo "  Plot job   : ${PLOT_ID}  (afterok:${JOB_ID})"
echo "  $(date '+%Y-%m-%d %H:%M:%S') — done"
echo "=============================================="
