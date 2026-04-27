#!/bin/bash
# =============================================================
# submit_one_mpi.sh — MPI Version
# =============================================================

set -e

EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

TEST_TYPE=$1
THICKNESS=$2
ORIENTATION=$3
SPECIMEN_WIDTH=$4
PIP_PUNCH2_ID=$5
[ "$PIP_PUNCH2_ID" = "none" ] && PIP_PUNCH2_ID=""

# Keep your original Python naming logic
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
echo "  submit_one_mpi.sh — build + MPI submit"
echo "  Job name    : ${JOB_NAME}"
echo "=============================================="

module load stack/2024-06
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

echo "  Submitting MPI solver job ..."
# CRITICAL CHANGE: We export JOB_NAME and use run_cluster_mpi.sh
JOB_ID=$(sbatch \
    --job-name=${JOB_NAME} \
    --export=ALL,JOB_NAME=${JOB_NAME},OUTPUT_SUBDIR=${JOB_NAME} \
    --parsable run_cluster_mpi.sh)
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
echo "  MPI Solver job : ${JOB_ID}"
echo "  Plot job       : ${PLOT_ID}"
echo "=============================================="