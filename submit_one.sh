#!/bin/bash
# =============================================================
# submit_one.sh  —  Build one model and submit solver job.
#                   Runs ON Euler — do not run locally.
#                   Launched by deploy.sh (single job) or
#                   deploy_study.sh (study loop) via SSH.
#
# Args:
#   $1  TEST_TYPE
#   $2  THICKNESS
#   $3  ORIENTATION
#   $4  SPECIMEN_WIDTH
#   $5  PIP_PUNCH2_ID   (pass "none" if unused)
#   $6  MESH_REFINEMENT_FACTOR  (default 1)
#   $7  MASS_SCALING_DT         (default "none" → use config.py default)
#   $8  STUDY_SUBDIR            (default "" → flat layout under EULER_DIR)
#
# When STUDY_SUBDIR is set (study mode):
#   - job dir goes to EULER_DIR/STUDY_SUBDIR/JOB_NAME/
#   - SLURM logs go to EULER_DIR/STUDY_SUBDIR/logs/
#   - run_flc.sh aggregation is NOT submitted (caller handles it)
#   - last stdout line is "JOB_ID=<slurm_id>" for caller to capture
#
# When STUDY_SUBDIR is empty (normal mode):
#   - job dir stays flat under EULER_DIR/JOB_NAME/
#   - run_flc.sh aggregation job submitted as usual
# =============================================================

set -e

EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

TEST_TYPE=$1
THICKNESS=$2
ORIENTATION=$3
SPECIMEN_WIDTH=$4
PIP_PUNCH2_ID=$5
[ "$PIP_PUNCH2_ID" = "none" ] && PIP_PUNCH2_ID=""
MESH_REFINEMENT_FACTOR=${6:-1}
[ "$MESH_REFINEMENT_FACTOR" = "none" ] && MESH_REFINEMENT_FACTOR="1"
MASS_SCALING_DT=${7:-none}
[ "$MASS_SCALING_DT" = "none" ] && MASS_SCALING_DT=""
STUDY_SUBDIR=${8:-}

# Derived name components
_t=$(python3 -c "print(str(float(${THICKNESS})).replace('.','p'))")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")
_punch_r=${PUNCH_RADIUS:-50}
_punch_d=$(python3 -c "import math; print(int(round(float('${_punch_r}') * 2)))")
if   [ "$TEST_TYPE" = "nakazima"  ]; then _test_cap="Naka${_punch_d}"
elif [ "$TEST_TYPE" = "marciniak" ]; then _test_cap="Marc${_punch_d}"
else _test_cap="Pip"; fi
if [ "$TEST_TYPE" = "pip" ] && [ -n "$PIP_PUNCH2_ID" ]; then
    _pip_suffix="_p2$(echo "$PIP_PUNCH2_ID" | sed 's/PUNCH_//')"
else
    _pip_suffix=""
fi
_mr_suffix=$(python3 -c "
v = float('${MESH_REFINEMENT_FACTOR}')
print('_mr' + ('%.4g' % v).replace('.','p') if abs(v - 1.0) > 1e-6 else '')
")
if [ -n "$MASS_SCALING_DT" ]; then
    _ms_suffix=$(python3 -c "
import math
ms = float('${MASS_SCALING_DT}')
exp = int(math.floor(math.log10(ms)))
mant = int(round(ms / 10**exp))
print('_ms%de%d' % (mant, abs(exp)))
")
else
    _ms_suffix=""
fi

JOB_NAME="${_test_cap}_W${SPECIMEN_WIDTH}_t${_t}_ang${_ang}${_pip_suffix}${_ms_suffix}${_mr_suffix}"

if [ -n "$STUDY_SUBDIR" ]; then
    OUTPUT_BASE="${EULER_DIR}/${STUDY_SUBDIR}"
    OUTPUT_SUBDIR="${STUDY_SUBDIR}/${JOB_NAME}"
    LOG_DIR="${OUTPUT_BASE}/logs"
else
    OUTPUT_BASE="${EULER_DIR}"
    OUTPUT_SUBDIR="${JOB_NAME}"
    LOG_DIR="${EULER_DIR}"
fi

echo "=============================================="
echo "  submit_one.sh — build + submit"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Width       : ${SPECIMEN_WIDTH} mm"
echo "  MR factor   : ${MESH_REFINEMENT_FACTOR}"
if [ -n "$MASS_SCALING_DT" ]; then
    echo "  Mass scaling: ${MASS_SCALING_DT}"
fi
echo "  Job name    : ${JOB_NAME}"
echo "  Output dir  : ${OUTPUT_BASE}/${JOB_NAME}/"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

module load abaqus/2023

cd "${EULER_DIR}"

echo "  Building ${JOB_NAME} ..."
_build_ok=0
for _attempt in 1 2 3; do
    rm -f "${EULER_DIR}/${JOB_NAME}.inp"
    TEST_TYPE=${TEST_TYPE} \
    SPECIMEN_WIDTH=${SPECIMEN_WIDTH} \
    BLANK_THICKNESS=${THICKNESS} \
    MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
    PIP_PUNCH2_ID=${PIP_PUNCH2_ID} \
    MESH_REFINEMENT_FACTOR=${MESH_REFINEMENT_FACTOR} \
    MASS_SCALING_DT=${MASS_SCALING_DT} \
    OUTPUT_BASE_DIR=${EULER_DIR} \
    xvfb-run -a abaqus cae noGUI=build_model.py && { _build_ok=1; break; }
    echo "  WARNING: build attempt ${_attempt} failed — retrying ..."
    rm -rf "${EULER_DIR}/${JOB_NAME}"
done
[ ${_build_ok} -eq 0 ] && { echo "  ERROR: build failed 3 times — aborting."; exit 1; }
echo "  Build done."

# Move job dir into study subdir if needed
if [ -n "$STUDY_SUBDIR" ]; then
    mkdir -p "${OUTPUT_BASE}/logs"
    rm -rf "${OUTPUT_BASE}/${JOB_NAME}"
    mv "${EULER_DIR}/${JOB_NAME}" "${OUTPUT_BASE}/"
fi

echo "  Rendering mesh screenshot ..."
OUTPUT_DIR="${EULER_DIR}/${OUTPUT_SUBDIR}" \
JOB_NAME="${JOB_NAME}" \
xvfb-run -a abaqus cae noGUI="${EULER_DIR}/screenshot_mesh.py" \
    || echo "  WARNING: mesh screenshot failed (continuing)."
cp /tmp/screenshot_mesh_out.txt "${EULER_DIR}/${OUTPUT_SUBDIR}/${JOB_NAME}_mesh_log.txt" 2>/dev/null || true

echo "  Submitting solver job ..."
_log_out="${LOG_DIR}/${JOB_NAME}_%j.out"
_log_err="${LOG_DIR}/${JOB_NAME}_%j.err"
JOB_ID=$(sbatch \
    --job-name="${JOB_NAME}" \
    --output="${_log_out}" \
    --error="${_log_err}" \
    --export=ALL,JOB_NAME="${JOB_NAME}",OUTPUT_SUBDIR="${OUTPUT_SUBDIR}",TEST_TYPE="${TEST_TYPE}",BLANK_THICKNESS="${THICKNESS}",MATERIAL_ORIENTATION_ANGLE="${ORIENTATION}",MESH_REFINEMENT_FACTOR="${MESH_REFINEMENT_FACTOR}",MASS_SCALING_DT="${MASS_SCALING_DT}" \
    --parsable run_cluster.sh)

echo "=============================================="
echo "  Solver job  : ${JOB_ID}"
echo "  Log         : ${_log_out/\%j/${JOB_ID}}"
echo "  $(date '+%Y-%m-%d %H:%M:%S') — done"
echo "=============================================="

if [ -z "$STUDY_SUBDIR" ]; then
    # Normal mode: submit FLC aggregation job
    if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]]; then
        FLC_OUTDIR="FLC_${TEST_TYPE}_t${_t}_ang${_ang}"
    else
        FLC_OUTDIR=""
    fi
    PLOT_ID=$(sbatch \
        --dependency=afterok:${JOB_ID} \
        --job-name=plot_${JOB_NAME} \
        --export=ALL,OUTPUT_DIRS=${JOB_NAME},FLC_OUTDIR=${FLC_OUTDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
        --parsable run_flc.sh)
    echo "  Plot job    : ${PLOT_ID}  (afterok:${JOB_ID})"
fi

# In study mode, emit parseable ID on last line for deploy_study.sh to capture
[ -n "$STUDY_SUBDIR" ] && echo "JOB_ID=${JOB_ID}"
