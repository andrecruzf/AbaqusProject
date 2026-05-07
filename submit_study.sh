#!/bin/bash
# =============================================================
# submit_study.sh  —  Mass scaling × mesh refinement sensitivity.
#                     Runs ON Euler — launched by deploy_study.sh.
#
# Args: TEST_TYPE THICKNESS ORIENTATION WIDTH "MR1 MR2 ..." "MS1 MS2 ..."
# =============================================================

set -e

EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"


TEST_TYPE=$1
TEST_TYPE="${TEST_TYPE,,}"
THICKNESS=$2
ORIENTATION=$3
WIDTH=$4
IFS=' ' read -ra MR_VALUES <<< "$5"
IFS=' ' read -ra MS_VALUES <<< "$6"

_t=$(python3 -c "print(str(float(${THICKNESS})).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")

STUDY_DIR="${EULER_DIR}/study_ms_mr_W${WIDTH}_t${_t}_ang${_ang}"
mkdir -p "${STUDY_DIR}/logs"

module load abaqus/2023

echo "=============================================="
echo "  submit_study.sh — MS × MR sensitivity study"
echo "  Test type : ${TEST_TYPE}"
echo "  Thickness : ${THICKNESS} mm"
echo "  Width     : W${WIDTH}"
echo "  MR values : ${MR_VALUES[*]}"
echo "  MS values : ${MS_VALUES[*]}"
echo "  Study dir : ${STUDY_DIR}/"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

JOB_IDS=()
OUTPUT_DIRS=()

for MR in "${MR_VALUES[@]}"; do
    for MS in "${MS_VALUES[@]}"; do
        echo "----------------------------------------------"

        # Compute suffixes — must match config.py logic exactly
        _ms_suffix=$(python3 -c "
import math
ms = float('${MS}')
exp = int(math.floor(math.log10(ms)))
mant = int(round(ms / 10**exp))
print('_ms%de%d' % (mant, abs(exp)))
")
        _mr_suffix=$(python3 -c "
v = float('${MR}')
print('_mr' + ('%.4g' % v).replace('.','p') if abs(v - 1.0) > 1e-6 else '')
")

        JOB_NAME="${_test_cap}_W${WIDTH}_t${_t}_ang${_ang}${_ms_suffix}${_mr_suffix}"
        OUTPUT_SUBDIR="study_ms_mr_W${WIDTH}_t${_t}_ang${_ang}/${JOB_NAME}"

        echo "  Building ${JOB_NAME} ..."
        cd "${EULER_DIR}"
        _build_ok=0
        for _attempt in 1 2 3; do
            rm -f "${EULER_DIR}/${JOB_NAME}.inp"
            TEST_TYPE=${TEST_TYPE} \
            SPECIMEN_WIDTH=${WIDTH} \
            BLANK_THICKNESS=${THICKNESS} \
            MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
            MESH_REFINEMENT_FACTOR=${MR} \
            MASS_SCALING_DT=${MS} \
            OUTPUT_BASE_DIR=${EULER_DIR} \
            xvfb-run -a abaqus cae noGUI=build_model.py && { _build_ok=1; break; }
            echo "  WARNING: build attempt ${_attempt} failed — retrying ..."
            rm -rf "${EULER_DIR}/${JOB_NAME}"
        done
        if [ ${_build_ok} -eq 0 ]; then
            echo "  ERROR: build failed 3 times for ${JOB_NAME} — skipping."
            continue
        fi

        # build_model creates OUTPUT_DIR relative to CWD; move into study dir
        rm -rf "${STUDY_DIR}/${JOB_NAME}"
        mv "${EULER_DIR}/${JOB_NAME}" "${STUDY_DIR}/"

        echo "  Rendering mesh screenshot ..."
        OUTPUT_DIR="${EULER_DIR}/${OUTPUT_SUBDIR}" \
        JOB_NAME="${JOB_NAME}" \
        xvfb-run -a abaqus cae noGUI="${EULER_DIR}/screenshot_mesh.py" \
            || echo "  WARNING: mesh screenshot failed (continuing)."
        cp /tmp/screenshot_mesh_out.txt \
           "${EULER_DIR}/${OUTPUT_SUBDIR}/${JOB_NAME}_mesh_log.txt" 2>/dev/null || true

        echo "  Submitting solver job ..."
        JOB_ID=$(cd "${EULER_DIR}" && sbatch \
            --job-name="${JOB_NAME}" \
            --output="${STUDY_DIR}/logs/${JOB_NAME}_%j.out" \
            --error="${STUDY_DIR}/logs/${JOB_NAME}_%j.err" \
            --export=ALL,JOB_NAME=${JOB_NAME},OUTPUT_SUBDIR=${OUTPUT_SUBDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION},MESH_REFINEMENT_FACTOR=${MR},MASS_SCALING_DT=${MS} \
            --parsable run_cluster.sh)

        JOB_IDS+=("${JOB_ID}")
        OUTPUT_DIRS+=("${OUTPUT_SUBDIR}")
        echo "  ${JOB_NAME} → SLURM job ${JOB_ID}"
        echo ""
    done
done

echo "=============================================="
echo "  All ${#JOB_IDS[@]} jobs submitted."
echo "  Job IDs: ${JOB_IDS[*]}"

# Submit plot aggregation job once all solver jobs complete
DEPENDENCY="afterok:$(IFS=:; echo "${JOB_IDS[*]}")"

echo "----------------------------------------------"
echo "  Submitting plot_study aggregation job ..."
PLOT_JOB_ID=$(cd "${EULER_DIR}" && sbatch \
    --dependency="${DEPENDENCY}" \
    --job-name="plot_study_W${WIDTH}" \
    --output="${STUDY_DIR}/logs/plot_study_%j.out" \
    --error="${STUDY_DIR}/logs/plot_study_%j.err" \
    --export=ALL,STUDY_DIR="${STUDY_DIR}" \
    --parsable run_plot_study.sh)
echo "  Plot job  : ${PLOT_JOB_ID} (held until all solver jobs complete)"
echo "  Results   : ${STUDY_DIR}/study_results.pdf"
echo "  $(date '+%Y-%m-%d %H:%M:%S') — done"
echo "=============================================="
