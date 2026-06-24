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
PUNCH_SPEED=${PUNCH_SPEED:-5.0}
PUNCH_DISPLACEMENT=${PUNCH_DISPLACEMENT:-35.0}
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
FLC_OUTDIR="FLC_${TEST_TYPE}_t${_t}_ang${_ang}${_ts_suffix}${_pd_suffix}${_bm_suffix}"
GLOBAL_DIR="${EULER_DIR}/${FLC_OUTDIR}"

module load abaqus/2023

echo "=============================================="
echo "  submit_all.sh — build + submit all widths"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Widths      : ${WIDTHS[*]}"
echo "  Mesh factor : ${MESH_REFINEMENT_FACTOR}"
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
    JOB_NAME="${_test_cap}_W${W}_t${_t}_ang${_ang}${_pip_suffix}${_ms_suffix}${_mr_suffix}${_ts_suffix}${_ps_suffix}${_pd_suffix}${_bm_suffix}"
    OUTPUT_SUBDIR="${FLC_OUTDIR}/${JOB_NAME}"

    echo "  Building ${JOB_NAME} ..."
    cd "${EULER_DIR}"
    _build_ok=0
    for _attempt in 1 2 3; do
        rm -f "${EULER_DIR}/${JOB_NAME}.inp"
        TEST_TYPE=${TEST_TYPE} \
        SPECIMEN_WIDTH=${W} \
        BLANK_THICKNESS=${THICKNESS} \
        MATERIAL_ORIENTATION_ANGLE=${ORIENTATION} \
        PIP_PUNCH2_ID=${PIP_PUNCH2_ID} \
        MESH_REFINEMENT_FACTOR=${MESH_REFINEMENT_FACTOR} \
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
        OUTPUT_BASE_DIR=${EULER_DIR} \
        xvfb-run -a abaqus cae noGUI=build_model.py && { _build_ok=1; break; }
        echo "  WARNING: build attempt ${_attempt} failed — retrying ..."
        rm -rf "${EULER_DIR}/${JOB_NAME}"
    done
    if [ ${_build_ok} -eq 0 ]; then
        echo "  ERROR: build failed 3 times for ${JOB_NAME} — skipping."
        continue
    fi

    # build_model creates OUTPUT_DIR relative to CWD; move it into the global dir
    rm -rf "${GLOBAL_DIR}/${JOB_NAME}"
    mv "${EULER_DIR}/${JOB_NAME}" "${GLOBAL_DIR}/"
    echo "  Rendering mesh screenshot ..."
    OUTPUT_DIR="${EULER_DIR}/${OUTPUT_SUBDIR}" \
    JOB_NAME="${JOB_NAME}" \
    xvfb-run -a abaqus cae noGUI="${EULER_DIR}/screenshot_mesh.py" \
        || echo "  WARNING: mesh screenshot failed (continuing)."
    cp /tmp/screenshot_mesh_out.txt "${EULER_DIR}/${OUTPUT_SUBDIR}/${JOB_NAME}_mesh_log.txt" 2>/dev/null || true

    if [ ! -f "${GLOBAL_DIR}/${JOB_NAME}/${JOB_NAME}.inp" ]; then
        echo "  ERROR: expected input deck not found:"
        echo "         ${GLOBAL_DIR}/${JOB_NAME}/${JOB_NAME}.inp"
        echo "  Skipping solver submission for ${JOB_NAME}."
        continue
    fi

    echo "  Submitting solver job ..."
    JOB_ID=$(cd "${EULER_DIR}" && sbatch \
        --job-name=${JOB_NAME} \
        --output=${GLOBAL_DIR}/logs/${JOB_NAME}_%j.out \
        --error=${GLOBAL_DIR}/logs/${JOB_NAME}_%j.err \
        --cpus-per-task="${SLURM_CPUS_PER_TASK}" \
        --mem-per-cpu="${SLURM_MEM_PER_CPU_GB}G" \
        --time="${SLURM_TIME_LIMIT}" \
        --export=ALL,JOB_NAME=${JOB_NAME},OUTPUT_SUBDIR=${OUTPUT_SUBDIR},TEST_TYPE=${TEST_TYPE},BLANK_THICKNESS=${THICKNESS},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION},MESH_REFINEMENT_FACTOR=${MESH_REFINEMENT_FACTOR},MASS_SCALING_DT=${MASS_SCALING_DT},PUNCH_SPEED=${PUNCH_SPEED},PUNCH_DISPLACEMENT=${PUNCH_DISPLACEMENT},N_THICKNESS_SEEDS=${N_THICKNESS_SEEDS},NUM_CPUS=${NUM_CPUS},ABAQUS_MEMORY_PERCENT=${ABAQUS_MEMORY_PERCENT},SLURM_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK},SLURM_MEM_PER_CPU_GB=${SLURM_MEM_PER_CPU_GB},SLURM_TIME_LIMIT=${SLURM_TIME_LIMIT},ENABLE_SYMMETRIES=${ENABLE_SYMMETRIES},BM_MESH_USE_MANUAL=${BM_MESH_USE_MANUAL},BM_MESH_TAG=${BM_MESH_TAG} \
        --parsable run_cluster.sh)

    JOB_IDS+=("$JOB_ID")
    OUTPUT_DIRS+=("$OUTPUT_SUBDIR")
    echo "  ${JOB_NAME} → SLURM job ${JOB_ID}"
    echo ""
done

echo "=============================================="
echo "  All jobs submitted."
echo "  Sim jobs    : ${JOB_IDS[*]}"
echo "  FLC job     : skipped (handled in Streamlit Results → Direct FLC)"

echo "  $(date '+%Y-%m-%d %H:%M:%S') — done"
echo "=============================================="
