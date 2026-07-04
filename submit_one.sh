#!/bin/bash
# =============================================================
# submit_one.sh  —  Build one model and submit solver job.
#                   Runs ON Euler — do not run locally.
#                   Launched by deploy.sh or manually via SSH.
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
# When STUDY_SUBDIR is set (grouped-output mode):
#   - job dir goes to EULER_DIR/STUDY_SUBDIR/JOB_NAME/
#   - SLURM logs go to EULER_DIR/STUDY_SUBDIR/logs/
#   - run_plots.sh flc aggregation is NOT submitted
#   - last stdout line is "JOB_ID=<slurm_id>" for caller to capture
#
# When STUDY_SUBDIR is empty (normal mode):
#   - job dir stays flat under EULER_DIR/JOB_NAME/
#   - run_plots.sh flc aggregation job submitted as usual
# =============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_CFG_EULER_DIR=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'EULER_DIR', '${SCRIPT_DIR}'))" 2>/dev/null || printf "%s" "$SCRIPT_DIR")
_CFG_EULER_SCRATCH_ROOT=$(python3 -c "import os, sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'EULER_SCRATCH_ROOT', '/cluster/scratch/' + os.environ.get('USER', '')))" 2>/dev/null || printf "/cluster/scratch/%s" "${USER:-$LOGNAME}")
EULER_DIR="${EULER_DIR:-$_CFG_EULER_DIR}"
EULER_SCRATCH_ROOT="${EULER_SCRATCH_ROOT:-$_CFG_EULER_SCRATCH_ROOT}"

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
PUNCH_SPEED=${PUNCH_SPEED:-5.0}
PUNCH_DISPLACEMENT=${PUNCH_DISPLACEMENT:-35.0}
PUNCH_VELOCITY_PROFILE=${PUNCH_VELOCITY_PROFILE:-smoothstep}
MESH_IMPORTED_FIXED_RADIUS=${MESH_IMPORTED_FIXED_RADIUS:-50}
MESH_IMPORTED_GROWTH_POWER=${MESH_IMPORTED_GROWTH_POWER:-1}
MESH_SEED_MODE=${MESH_SEED_MODE:-bm}
MESH_BACKEND=${MESH_BACKEND:-bm}
N_THICKNESS_SEEDS=${N_THICKNESS_SEEDS:-10}
NUM_CPUS=${NUM_CPUS:-24}
ABAQUS_MEMORY_PERCENT=${ABAQUS_MEMORY_PERCENT:-90}
SLURM_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK:-$NUM_CPUS}
SLURM_MEM_PER_CPU_GB=${SLURM_MEM_PER_CPU_GB:-4.0}
SLURM_TIME_LIMIT=${SLURM_TIME_LIMIT:-48:00:00}
ENABLE_SYMMETRIES=${ENABLE_SYMMETRIES:-1}
BM_MESH_USE_MANUAL=${BM_MESH_USE_MANUAL:-0}
BM_MESH_TAG=${BM_MESH_TAG:-}
BM_MIRROR=${BM_MIRROR:-0}
BM_P_INNER_X=${BM_P_INNER_X:-}
BM_P_INNER_R=${BM_P_INNER_R:-}
BM_P_CIRCLE_R=${BM_P_CIRCLE_R:-}
BM_P_XZPLANE_1=${BM_P_XZPLANE_1:-}
BM_W200_SECTION1_Y=${BM_W200_SECTION1_Y:-}
BM_W200_SECTION2_R=${BM_W200_SECTION2_R:-}
BM_W200_SECTION3_R=${BM_W200_SECTION3_R:-}
BM_MESH_SECTION1_X=${BM_MESH_SECTION1_X:-}
BM_MESH_SECTION1_Y=${BM_MESH_SECTION1_Y:-}
BM_MESH_SECTION2_X=${BM_MESH_SECTION2_X:-}
BM_MESH_SECTION2_Y=${BM_MESH_SECTION2_Y:-}
BM_MESH_SECTION3_Y=${BM_MESH_SECTION3_Y:-}
BM_MESH_SECTION3_1_Y=${BM_MESH_SECTION3_1_Y:-}
BM_MESH_SECTION4_Y=${BM_MESH_SECTION4_Y:-}
BM_MESH_W200_SECTION1=${BM_MESH_W200_SECTION1:-}
BM_MESH_W200_SECTION2=${BM_MESH_W200_SECTION2:-}
BM_MESH_W200_SECTION3=${BM_MESH_W200_SECTION3:-}
BM_MESH_W200_SECTION4=${BM_MESH_W200_SECTION4:-}

# Derived name components
_t=$(python3 -c "print(str(float(${THICKNESS})).replace('.','p'))")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")
_punch_r=${PUNCH_RADIUS:-50}
# Guard against a 0/blank punch radius (degenerate punch); keep in sync with config.py
_punch_r=$(python3 -c "r=float('${_punch_r}' or 50); print(r if r>0 else 50)")
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
_ts_suffix=$(python3 -c "
v = int(float('${N_THICKNESS_SEEDS}'))
print('_nt%d' % v if v != 10 else '')
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
_ps_suffix=$(python3 -c "
v = float('${PUNCH_SPEED}')
print('_ps' + ('%.4g' % v).replace('.','p') if '${TEST_TYPE}' != 'pip' and abs(v - 5.0) > 1e-6 else '')
")
_pd_suffix=$(python3 -c "
v = float('${PUNCH_DISPLACEMENT}')
print('_pd' + ('%.4g' % v).replace('.','p') if '${TEST_TYPE}' != 'pip' and abs(v - 35.0) > 1e-6 else '')
")
_bm_suffix=$(python3 -c "
manual = '${BM_MESH_USE_MANUAL}'.lower() in ('1', 'true', 'yes', 'on')
tag = ''.join(ch for ch in '${BM_MESH_TAG}' if ch.isalnum())[:24]
print('_bm' + (tag or 'man') if manual else '')
")
# Velocity-profile suffix — must match config.py so the build, the output dir,
# and the solve/postproc all agree on the ODB name (constant-velocity runs only).
if [ "$(printf '%s' "${PUNCH_VELOCITY_PROFILE}" | tr '[:upper:]' '[:lower:]')" = "constant" ]; then
    _vp_suffix="_vconst"
else
    _vp_suffix=""
fi
_fr_suffix=$(python3 -c "
v = float('${FR_PUNCH:-0.0}')
print('_fr' + ('%.4g' % v).replace('.','p') if abs(v) > 1e-9 else '')
")

JOB_NAME="${_test_cap}_W${SPECIMEN_WIDTH}_t${_t}_ang${_ang}${_pip_suffix}${_ms_suffix}${_mr_suffix}${_ts_suffix}${_ps_suffix}${_pd_suffix}${_bm_suffix}${_vp_suffix}${_fr_suffix}"

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
echo "  Mesh backend: ${MESH_BACKEND}"
echo "  Symmetries  : ${ENABLE_SYMMETRIES}"
echo "  Solver CPUs : ${NUM_CPUS}"
echo "  Abaqus mem% : ${ABAQUS_MEMORY_PERCENT}"
echo "  SLURM time  : ${SLURM_TIME_LIMIT}"
if [ "${BM_MESH_USE_MANUAL}" = "1" ]; then
    echo "  BM manual   : on ${BM_MESH_TAG:+(${BM_MESH_TAG})}"
fi
if [ -n "$MASS_SCALING_DT" ]; then
    echo "  Mass scaling: ${MASS_SCALING_DT}"
fi
if [ "$TEST_TYPE" != "pip" ]; then
    echo "  Punch speed : ${PUNCH_SPEED} mm/s"
    echo "  Punch travel: ${PUNCH_DISPLACEMENT} mm"
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
    MESH_IMPORTED_FIXED_RADIUS=${MESH_IMPORTED_FIXED_RADIUS} \
    MESH_IMPORTED_GROWTH_POWER=${MESH_IMPORTED_GROWTH_POWER} \
    MESH_SEED_MODE=${MESH_SEED_MODE} \
    MESH_BACKEND=${MESH_BACKEND} \
    N_THICKNESS_SEEDS=${N_THICKNESS_SEEDS} \
    NUM_CPUS=${NUM_CPUS} \
    ABAQUS_MEMORY_PERCENT=${ABAQUS_MEMORY_PERCENT} \
    SLURM_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK} \
    SLURM_MEM_PER_CPU_GB=${SLURM_MEM_PER_CPU_GB} \
    SLURM_TIME_LIMIT=${SLURM_TIME_LIMIT} \
    ENABLE_SYMMETRIES=${ENABLE_SYMMETRIES} \
    BM_MESH_USE_MANUAL=${BM_MESH_USE_MANUAL} \
    BM_MESH_TAG=${BM_MESH_TAG} \
    BM_MIRROR=${BM_MIRROR} \
    BM_P_INNER_X=${BM_P_INNER_X} \
    BM_P_INNER_R=${BM_P_INNER_R} \
    BM_P_CIRCLE_R=${BM_P_CIRCLE_R} \
    BM_P_XZPLANE_1=${BM_P_XZPLANE_1} \
    BM_W200_SECTION1_Y=${BM_W200_SECTION1_Y} \
    BM_W200_SECTION2_R=${BM_W200_SECTION2_R} \
    BM_W200_SECTION3_R=${BM_W200_SECTION3_R} \
    BM_MESH_SECTION1_X=${BM_MESH_SECTION1_X} \
    BM_MESH_SECTION1_Y=${BM_MESH_SECTION1_Y} \
    BM_MESH_SECTION2_X=${BM_MESH_SECTION2_X} \
    BM_MESH_SECTION2_Y=${BM_MESH_SECTION2_Y} \
    BM_MESH_SECTION3_Y=${BM_MESH_SECTION3_Y} \
    BM_MESH_SECTION3_1_Y=${BM_MESH_SECTION3_1_Y} \
    BM_MESH_SECTION4_Y=${BM_MESH_SECTION4_Y} \
    BM_MESH_W200_SECTION1=${BM_MESH_W200_SECTION1} \
    BM_MESH_W200_SECTION2=${BM_MESH_W200_SECTION2} \
    BM_MESH_W200_SECTION3=${BM_MESH_W200_SECTION3} \
    BM_MESH_W200_SECTION4=${BM_MESH_W200_SECTION4} \
    MASS_SCALING_DT=${MASS_SCALING_DT} \
    PUNCH_SPEED=${PUNCH_SPEED} \
    PUNCH_DISPLACEMENT=${PUNCH_DISPLACEMENT} \
    PUNCH_VELOCITY_PROFILE=${PUNCH_VELOCITY_PROFILE} \
    OUTPUT_BASE_DIR=${EULER_DIR} \
    xvfb-run -a abaqus cae noGUI=build_model.py && { _build_ok=1; break; }
    echo "  WARNING: build attempt ${_attempt} failed — retrying ..."
    rm -rf "${EULER_DIR}/${JOB_NAME}"
done
[ ${_build_ok} -eq 0 ] && { echo "  ERROR: build failed 3 times — aborting."; exit 1; }
echo "  Build done."

# Move job dir into grouped output subdir if needed.
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

if [ ! -f "${EULER_DIR}/${OUTPUT_SUBDIR}/${JOB_NAME}.inp" ]; then
    echo "  ERROR: expected input deck not found:"
    echo "         ${EULER_DIR}/${OUTPUT_SUBDIR}/${JOB_NAME}.inp"
    echo "  Aborting before solver submission."
    exit 1
fi

echo "  Submitting solver job ..."
_log_out="${LOG_DIR}/${JOB_NAME}_%j.out"
_log_err="${LOG_DIR}/${JOB_NAME}_%j.err"
JOB_ID=$(sbatch \
    --job-name="${JOB_NAME}" \
    --output="${_log_out}" \
    --error="${_log_err}" \
    --cpus-per-task="${SLURM_CPUS_PER_TASK}" \
    --mem-per-cpu="${SLURM_MEM_PER_CPU_GB}G" \
    --time="${SLURM_TIME_LIMIT}" \
    --export=ALL,JOB_NAME="${JOB_NAME}",OUTPUT_SUBDIR="${OUTPUT_SUBDIR}",EULER_SCRATCH_ROOT="${EULER_SCRATCH_ROOT}",TEST_TYPE="${TEST_TYPE}",BLANK_THICKNESS="${THICKNESS}",MATERIAL_ORIENTATION_ANGLE="${ORIENTATION}",MESH_REFINEMENT_FACTOR="${MESH_REFINEMENT_FACTOR}",MASS_SCALING_DT="${MASS_SCALING_DT}",PUNCH_SPEED="${PUNCH_SPEED}",PUNCH_DISPLACEMENT="${PUNCH_DISPLACEMENT}",PUNCH_VELOCITY_PROFILE="${PUNCH_VELOCITY_PROFILE}",N_THICKNESS_SEEDS="${N_THICKNESS_SEEDS}",NUM_CPUS="${NUM_CPUS}",ABAQUS_MEMORY_PERCENT="${ABAQUS_MEMORY_PERCENT}",SLURM_CPUS_PER_TASK="${SLURM_CPUS_PER_TASK}",SLURM_MEM_PER_CPU_GB="${SLURM_MEM_PER_CPU_GB}",SLURM_TIME_LIMIT="${SLURM_TIME_LIMIT}",ENABLE_SYMMETRIES="${ENABLE_SYMMETRIES}",BM_MESH_USE_MANUAL="${BM_MESH_USE_MANUAL}",BM_MESH_TAG="${BM_MESH_TAG}" \
    --parsable run_cluster.sh)

echo "=============================================="
echo "  Solver job  : ${JOB_ID}"
echo "  Log         : ${_log_out/\%j/${JOB_ID}}"
echo "  $(date '+%Y-%m-%d %H:%M:%S') — done"
echo "=============================================="

if [ -z "$STUDY_SUBDIR" ]; then
    # Normal mode: submit FLC aggregation job
    if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]]; then
        FLC_OUTDIR="FLC_${TEST_TYPE}_t${_t}_ang${_ang}${_ts_suffix}${_pd_suffix}${_bm_suffix}"
    else
        FLC_OUTDIR=""
    fi
    PLOT_ID=$(sbatch \
        --dependency=afterok:${JOB_ID} \
        --job-name=plot_${JOB_NAME} \
        --export=ALL,OUTPUT_DIRS=${JOB_NAME},FLC_OUTDIR=${FLC_OUTDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
        --parsable run_plots.sh flc)
    echo "  Plot job    : ${PLOT_ID}  (afterok:${JOB_ID})"
fi

# In grouped-output mode, emit parseable ID on last line for callers to capture.
[ -n "$STUDY_SUBDIR" ] && echo "JOB_ID=${JOB_ID}"
