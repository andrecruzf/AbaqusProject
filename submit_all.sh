#!/bin/bash
# =============================================================
# submit_all.sh  —  Build all models and submit solver jobs.
#                   Runs ON Euler — do not run locally.
#                   Launched by deploy_all.sh via SSH + tmux.
#
# Args: TEST_TYPE THICKNESS ORIENTATION PIP_PUNCH2_ID CUSTOM_WIDTHS [WIDTHS...]
#   PIP_PUNCH2_ID: pass "none" if empty
# =============================================================

set -e

EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

TEST_TYPE=$1
# normalize to lowercase
TEST_TYPE="${TEST_TYPE,,}"
THICKNESS=$2
ORIENTATION=$3
PIP_PUNCH2_ID=$4
[ "$PIP_PUNCH2_ID" = "none" ] && PIP_PUNCH2_ID=""
MESH_REFINEMENT_FACTOR=${5:-1}
[ "$MESH_REFINEMENT_FACTOR" = "none" ] && MESH_REFINEMENT_FACTOR="1"
CUSTOM_WIDTHS=$6
shift 6
WIDTHS=("$@")

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
FLC_OUTDIR="FLC_${TEST_TYPE}_t${_t}_ang${_ang}"
GLOBAL_DIR="${EULER_DIR}/${FLC_OUTDIR}"

module load abaqus/2023

echo "=============================================="
echo "  submit_all.sh — build + submit all widths"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Widths      : ${WIDTHS[*]}"
echo "  Mesh factor : ${MESH_REFINEMENT_FACTOR}"
if [ -n "$MASS_SCALING_DT" ]; then
    echo "  Mass scaling: ${MASS_SCALING_DT}"
fi
if [ "$TEST_TYPE" = "pip" ]; then
    echo "  Punch2      : ${PIP_PUNCH2_ID:-PUNCH_21 (default)}"
fi
if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]] && [ "$CUSTOM_WIDTHS" = false ]; then
    echo "  Global dir  : ${GLOBAL_DIR}/"
fi
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── Create global directory structure ────────────────────────
mkdir -p "${GLOBAL_DIR}/logs"

JOB_IDS=()
OUTPUT_DIRS=()

for W in "${WIDTHS[@]}"; do
    echo "----------------------------------------------"
    JOB_NAME="${_test_cap}_W${W}_t${_t}_ang${_ang}${_pip_suffix}${_ms_suffix}${_mr_suffix}"
    OUTPUT_SUBDIR="${FLC_OUTDIR}/${JOB_NAME}"

    echo "  Building ${JOB_NAME} ..."
    cd "${EULER_DIR}"
    TEST_TYPE=${TEST_TYPE} \
    SPECIMEN_WIDTH=${W} \
    BLANK_THICKNESS=${THICKNESS} \
    MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
    PIP_PUNCH2_ID=${PIP_PUNCH2_ID} \
    MESH_REFINEMENT_FACTOR=${MESH_REFINEMENT_FACTOR} \
    OUTPUT_BASE_DIR=${EULER_DIR} \
    xvfb-run -a abaqus cae noGUI=build_model.py

    # build_model creates OUTPUT_DIR relative to CWD; move it into the global dir
    rm -rf "${GLOBAL_DIR}/${JOB_NAME}"
    mv "${EULER_DIR}/${JOB_NAME}" "${GLOBAL_DIR}/"

    echo "  Rendering mesh screenshot ..."
    OUTPUT_DIR="${EULER_DIR}/${OUTPUT_SUBDIR}" \
    JOB_NAME="${JOB_NAME}" \
    xvfb-run -a abaqus cae noGUI="${EULER_DIR}/screenshot_mesh.py" \
        || echo "  WARNING: mesh screenshot failed (continuing)."
    cp /tmp/screenshot_mesh_out.txt "${EULER_DIR}/${OUTPUT_SUBDIR}/${JOB_NAME}_mesh_log.txt" 2>/dev/null || true

    echo "  Submitting solver job ..."
    JOB_ID=$(cd "${EULER_DIR}" && sbatch \
        --job-name=${JOB_NAME} \
        --output=${GLOBAL_DIR}/logs/${JOB_NAME}_%j.out \
        --error=${GLOBAL_DIR}/logs/${JOB_NAME}_%j.err \
        --export=ALL,JOB_NAME=${JOB_NAME},OUTPUT_SUBDIR=${OUTPUT_SUBDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION},MESH_REFINEMENT_FACTOR=${MESH_REFINEMENT_FACTOR} \
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
        --output=${GLOBAL_DIR}/logs/FLC_${TEST_TYPE}_ang${_ang}_%j.out \
        --error=${GLOBAL_DIR}/logs/FLC_${TEST_TYPE}_ang${_ang}_%j.err \
        --export=ALL,OUTPUT_DIRS=${DIRS_STR},FLC_OUTDIR=${FLC_OUTDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
        --parsable run_flc.sh)
    echo "  FLC job     : ${FLC_JOB_ID} (held until all solver jobs complete)"
    echo "  FLC diagram : ${GLOBAL_DIR}/FLC_${TEST_TYPE}.pdf"
else
    echo "  FLC job     : skipped (test=${TEST_TYPE}, custom_widths=${CUSTOM_WIDTHS})"
fi

echo "  $(date '+%Y-%m-%d %H:%M:%S') — done"
echo "=============================================="
