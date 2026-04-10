#!/bin/bash
# =============================================================
# deploy_all.sh  —  Push config.py, build all models sequentially
#                   on the login node, then submit solver jobs.
#
# Usage:
#   ./deploy_all.sh                        # all widths, default thickness
#   ./deploy_all.sh 1.5                    # all widths, thickness=1.5
#   ./deploy_all.sh 1.5 50 80 100          # specific widths
# =============================================================

set -e

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TEST_TYPE=${1:-nakazima}
THICKNESS=${2:-1.5}
shift 2 || true
WIDTHS=("${@}")
if [ ${#WIDTHS[@]} -eq 0 ]; then
    WIDTHS=(20 50 80 100 120 200)
fi

echo "=============================================="
echo "  deploy_all.sh — build + submit all widths"
echo "  Test type : ${TEST_TYPE}"
echo "  Thickness : ${THICKNESS} mm"
echo "  Widths    : ${WIDTHS[*]}"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# Push scripts once
echo "  Pushing config.py, run_cluster.sh, postproc.py, postproc_movie.py ..."
scp "$SCRIPT_DIR/config.py" \
    "$SCRIPT_DIR/run_cluster.sh" \
    "$SCRIPT_DIR/postproc.py" \
    "$SCRIPT_DIR/postproc_movie.py" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
echo "  Done."
echo ""

# Build each model sequentially on the login node, then submit solver job
for W in "${WIDTHS[@]}"; do
    echo "----------------------------------------------"
    echo "  Building W${W}_t${THICKNESS} on login node ..."
    ssh "${EULER_USER}@${EULER_HOST}" "cd ${EULER_DIR} && module load abaqus/2023 && TEST_TYPE=${TEST_TYPE} SPECIMEN_WIDTH=${W} BLANK_THICKNESS=${THICKNESS} abaqus cae noGUI=build_model.py"

    echo "  Submitting solver job ..."
    _t=$(python3 -c "print(str(${THICKNESS}).replace('.','p'))")
    _test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
    JOB_NAME="${_test_cap}_W${W}_t${_t}"
    OUTPUT_SUBDIR="$JOB_NAME"
    JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" "cd ${EULER_DIR} && sbatch --job-name=${JOB_NAME} --export=ALL,JOB_NAME=${JOB_NAME},OUTPUT_SUBDIR=${OUTPUT_SUBDIR} --parsable run_cluster.sh")
    echo "  W${W}_t${THICKNESS} → job ${JOB_ID}"
    echo ""
done

echo "=============================================="
echo "  All jobs submitted."
echo "  Monitor: ssh ${EULER_USER}@${EULER_HOST} 'squeue --me'"
echo "=============================================="
