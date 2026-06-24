#!/bin/bash
# =============================================================
# deploy_all.sh  —  Push scripts, build all models, submit solver
#                   jobs, then submit FLC aggregation job.
#
# Usage:
#   ./deploy_all.sh                                                # all defaults from config.py
#   ./deploy_all.sh nakazima 1.5 0 none 3 1e-5 5.0 50              # explicit app-style args
#   ./deploy_all.sh nakazima 1.5 0 none 3 1e-5 5.0 50 20 50 100    # + specific widths
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
PIP_PUNCH2_ID=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'PIP_PUNCH2_ID', '') or '')")
DEFAULT_MR=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.MESH_REFINEMENT_FACTOR)")
DEFAULT_MS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.MASS_SCALING_DT)")
DEFAULT_PS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.PUNCH_SPEED)")
DEFAULT_PD=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.PUNCH_DISPLACEMENT)")
DEFAULT_PR=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.PUNCH_RADIUS)")
DEFAULT_MB=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'MESH_BACKEND', 'bm'))")
DEFAULT_TS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'N_THICKNESS_SEEDS', 10))")
DEFAULT_NUM_CPUS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'NUM_CPUS', 24))")
DEFAULT_ABAQUS_MEM=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'ABAQUS_MEMORY_PERCENT', 90))")
DEFAULT_SLURM_MEM=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'SLURM_MEM_PER_CPU_GB', 4.0))")
DEFAULT_SLURM_TIME=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'SLURM_TIME_LIMIT', '48:00:00'))")

TEST_TYPE=$(echo "${1:-$DEFAULT_TEST_TYPE}" | tr '[:upper:]' '[:lower:]')
THICKNESS=${2:-$DEFAULT_THICKNESS}
ORIENTATION=${3:-$DEFAULT_ORIENTATION}
PIP_PUNCH2_ID=${4:-$PIP_PUNCH2_ID}
MESH_REFINEMENT_FACTOR=${5:-$DEFAULT_MR}
MASS_SCALING_DT=${6:-$DEFAULT_MS}
PUNCH_SPEED=${7:-$DEFAULT_PS}
PUNCH_RADIUS=${8:-$DEFAULT_PR}
PUNCH_DISPLACEMENT=${PUNCH_DISPLACEMENT:-$DEFAULT_PD}
MESH_BACKEND=${MESH_BACKEND:-$DEFAULT_MB}
N_THICKNESS_SEEDS=${N_THICKNESS_SEEDS:-$DEFAULT_TS}
NUM_CPUS=${NUM_CPUS:-$DEFAULT_NUM_CPUS}
ABAQUS_MEMORY_PERCENT=${ABAQUS_MEMORY_PERCENT:-$DEFAULT_ABAQUS_MEM}
SLURM_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK:-$NUM_CPUS}
SLURM_MEM_PER_CPU_GB=${SLURM_MEM_PER_CPU_GB:-$DEFAULT_SLURM_MEM}
SLURM_TIME_LIMIT=${SLURM_TIME_LIMIT:-$DEFAULT_SLURM_TIME}
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

[ "$PIP_PUNCH2_ID" = "none" ] && PIP_PUNCH2_ID=""
[ "$PUNCH_RADIUS" = "none" ] && PUNCH_RADIUS="$DEFAULT_PR"

shift $(( $# < 8 ? $# : 8 ))
CUSTOM_WIDTHS=false
WIDTHS=("${@}")
if [ ${#WIDTHS[@]} -eq 0 ]; then
    WIDTHS=(20 50 80 90 100 120 200)
else
    CUSTOM_WIDTHS=true
fi

# Derived name components (computed once, used in loop and FLC job)
_t=$(python3 -c "print(str(float(${THICKNESS})).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")
if [ "$TEST_TYPE" = "pip" ] && [ -n "$PIP_PUNCH2_ID" ]; then
    _pip_suffix="_p2$(echo "$PIP_PUNCH2_ID" | sed 's/PUNCH_//')"
else
    _pip_suffix=""
fi
_ts_suffix=$(python3 -c "
v = int(float('${N_THICKNESS_SEEDS}'))
print('_nt%d' % v if v != 10 else '')
")
_bm_suffix=$(python3 -c "
manual = '${BM_MESH_USE_MANUAL}'.lower() in ('1', 'true', 'yes', 'on')
tag = ''.join(ch for ch in '${BM_MESH_TAG}' if ch.isalnum())[:24]
print('_bm' + (tag or 'man') if manual else '')
")
FLC_OUTDIR="FLC_${TEST_TYPE}_t${_t}_ang${_ang}${_ts_suffix}${_bm_suffix}"

echo "=============================================="
echo "  deploy_all.sh — build + submit all widths"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Widths      : ${WIDTHS[*]}"
echo "  Mesh factor : ${MESH_REFINEMENT_FACTOR}"
if [ "$TEST_TYPE" = "pip" ]; then
    echo "  Punch2      : ${PIP_PUNCH2_ID:-PUNCH_21 (default)}"
fi
if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]] && [ "$CUSTOM_WIDTHS" = false ]; then
    echo "  FLC output  : ${FLC_OUTDIR}/"
fi
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── Push scripts once ─────────────────────────────────────────────────────────
echo "  Pushing scripts to Euler ..."
rsync -az --checksum \
    "$SCRIPT_DIR/config.py" \
    "$SCRIPT_DIR/build_model.py" \
    "$SCRIPT_DIR/build_mesh_only.py" \
    "$SCRIPT_DIR/screenshot_mesh.py" \
    "$SCRIPT_DIR/run_cluster.sh" \
    "$SCRIPT_DIR/run_plots.sh" \
    "$SCRIPT_DIR/postproc.py" \
    "$SCRIPT_DIR/postproc_movie.py" \
    "$SCRIPT_DIR/plot_results.py" \
    "$SCRIPT_DIR/plot_flc.py" \
    "$SCRIPT_DIR/Nakazima_BM.py" \
    "$SCRIPT_DIR/VUMAT_explicit.f" \
    "$SCRIPT_DIR/submit_all.sh" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"

# ── Push modules directory ────────────────────────────────────────────────────
rsync -az --checksum "$SCRIPT_DIR/modules/" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/modules/"

# ── Push PiP geometry directories ────────────────────────────────────────────
if [ "$TEST_TYPE" = "pip" ]; then
    echo "  Pushing PiP_Punches and PiP_Geometries ..."
    rsync -az --checksum "$SCRIPT_DIR/PiP_Punches/" \
        "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/PiP_Punches/"
    rsync -az --checksum "$SCRIPT_DIR/PiP_Geometries/" \
        "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/PiP_Geometries/"
fi
echo "  Done."
echo ""

# ── Launch build+submit loop on Euler via tmux ────────────────────────────────
_pip_id_arg="${PIP_PUNCH2_ID:-none}"
_bm_env="NUM_CPUS=${NUM_CPUS} ABAQUS_MEMORY_PERCENT=${ABAQUS_MEMORY_PERCENT} SLURM_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK} SLURM_MEM_PER_CPU_GB=${SLURM_MEM_PER_CPU_GB} SLURM_TIME_LIMIT=${SLURM_TIME_LIMIT} ENABLE_SYMMETRIES=${ENABLE_SYMMETRIES} PUNCH_DISPLACEMENT=${PUNCH_DISPLACEMENT} BM_MESH_USE_MANUAL=${BM_MESH_USE_MANUAL} BM_MESH_TAG=${BM_MESH_TAG} BM_MIRROR=${BM_MIRROR} BM_P_INNER_X=${BM_P_INNER_X} BM_P_INNER_R=${BM_P_INNER_R} BM_P_CIRCLE_R=${BM_P_CIRCLE_R} BM_P_XZPLANE_1=${BM_P_XZPLANE_1} BM_W200_SECTION1_Y=${BM_W200_SECTION1_Y} BM_W200_SECTION2_R=${BM_W200_SECTION2_R} BM_W200_SECTION3_R=${BM_W200_SECTION3_R} BM_MESH_SECTION1_X=${BM_MESH_SECTION1_X} BM_MESH_SECTION1_Y=${BM_MESH_SECTION1_Y} BM_MESH_SECTION2_X=${BM_MESH_SECTION2_X} BM_MESH_SECTION2_Y=${BM_MESH_SECTION2_Y} BM_MESH_SECTION3_Y=${BM_MESH_SECTION3_Y} BM_MESH_SECTION3_1_Y=${BM_MESH_SECTION3_1_Y} BM_MESH_SECTION4_Y=${BM_MESH_SECTION4_Y} BM_MESH_W200_SECTION1=${BM_MESH_W200_SECTION1} BM_MESH_W200_SECTION2=${BM_MESH_W200_SECTION2} BM_MESH_W200_SECTION3=${BM_MESH_W200_SECTION3} BM_MESH_W200_SECTION4=${BM_MESH_W200_SECTION4}"

echo "  Launching submit_all.sh on Euler in tmux session 'deploy' ..."
ssh "${EULER_USER}@${EULER_HOST}" "
    tmux kill-session -t deploy 2>/dev/null || true
    tmux new-session -d -s deploy \
        'PUNCH_RADIUS=${PUNCH_RADIUS} MASS_SCALING_DT=${MASS_SCALING_DT} PUNCH_SPEED=${PUNCH_SPEED} MESH_BACKEND=${MESH_BACKEND} N_THICKNESS_SEEDS=${N_THICKNESS_SEEDS} ${_bm_env} bash ${EULER_DIR}/submit_all.sh ${TEST_TYPE} ${THICKNESS} ${ORIENTATION} ${_pip_id_arg} ${MESH_REFINEMENT_FACTOR} ${CUSTOM_WIDTHS} ${WIDTHS[*]} \
         > ${EULER_DIR}/submit_all.log 2>&1'
"

echo "=============================================="
echo "  Scripts pushed. Submission running on Euler."
echo ""
echo "  Attach to watch live:"
echo "    ssh ${EULER_USER}@${EULER_HOST}"
echo "    tmux attach -t deploy"
echo ""
echo "  Or tail the log (no SSH needed to keep open):"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'tail -f ${EULER_DIR}/submit_all.log'"
echo "=============================================="
