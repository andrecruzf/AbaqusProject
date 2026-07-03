#!/bin/bash
# =============================================================
# deploy.sh  —  Push config.py, build model on login node, submit solver job
# Run this from your local Mac:
#   ./deploy.sh
# =============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_config_value() {
    python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(${1})"
}

DEFAULT_EULER_USER=$(_config_value "getattr(config, 'EULER_USER', 'acruzfaria')")
DEFAULT_EULER_HOST=$(_config_value "getattr(config, 'EULER_HOST', 'euler.ethz.ch')")
DEFAULT_EULER_DIR=$(_config_value "getattr(config, 'EULER_DIR', '/cluster/home/%s/AbaqusProject' % getattr(config, 'EULER_USER', ''))")
DEFAULT_EULER_SCRATCH_ROOT=$(_config_value "getattr(config, 'EULER_SCRATCH_ROOT', '/cluster/scratch/%s' % getattr(config, 'EULER_USER', ''))")

EULER_USER="${EULER_USER:-$DEFAULT_EULER_USER}"
EULER_HOST="${EULER_HOST:-$DEFAULT_EULER_HOST}"
EULER_DIR="${EULER_DIR:-$DEFAULT_EULER_DIR}"
EULER_SCRATCH_ROOT="${EULER_SCRATCH_ROOT:-$DEFAULT_EULER_SCRATCH_ROOT}"
SSH_AUTH_MODE="${SSH_AUTH_MODE:-normal}"
SSH_CONTROL_PATH="${SSH_CONTROL_PATH:-}"

SSH_CMD=(ssh -o ConnectTimeout=15 -o LogLevel=ERROR)
if [ "$SSH_AUTH_MODE" = "key_only" ]; then
    SSH_CMD+=(-o BatchMode=yes)
elif [ -n "$SSH_CONTROL_PATH" ]; then
    SSH_CMD+=(
        -o BatchMode=yes
        -o ControlMaster=no
        -S "$SSH_CONTROL_PATH"
    )
else
    SSH_CMD+=(
        -o BatchMode=no
        -o PubkeyAuthentication=no
        -o PreferredAuthentications=keyboard-interactive,password
        -o KbdInteractiveAuthentication=yes
        -o PasswordAuthentication=yes
        -o ControlMaster=no
        -S none
    )
fi
RSYNC_SSH_CMD="${SSH_CMD[*]}"

echo "=============================================="
echo "  deploy.sh — push + build + submit"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── 1. Read parameters (positional args > config.py defaults) ───
DEFAULT_TEST_TYPE=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.TEST_TYPE)")
DEFAULT_THICKNESS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.BLANK_THICKNESS)")
DEFAULT_ORIENTATION=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(int(config.MATERIAL_ORIENTATION_ANGLE))")
DEFAULT_WIDTH=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.SPECIMEN_WIDTH)")
PIP_PUNCH2_ID=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'PIP_PUNCH2_ID', '') or '')")
DEFAULT_MR=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.MESH_REFINEMENT_FACTOR)")
DEFAULT_MS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.MASS_SCALING_DT)")
DEFAULT_PS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.PUNCH_SPEED)")
DEFAULT_PD=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.PUNCH_DISPLACEMENT)")
DEFAULT_VP=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.PUNCH_VELOCITY_PROFILE)")
DEFAULT_PR=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.PUNCH_RADIUS)")
DEFAULT_MB=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'MESH_BACKEND', 'bm'))")
DEFAULT_TS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'N_THICKNESS_SEEDS', 10))")
DEFAULT_NUM_CPUS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'NUM_CPUS', 24))")
DEFAULT_ABAQUS_MEM=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'ABAQUS_MEMORY_PERCENT', 90))")
DEFAULT_SLURM_MEM=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'SLURM_MEM_PER_CPU_GB', 4.0))")
DEFAULT_SLURM_TIME=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'SLURM_TIME_LIMIT', '48:00:00'))")
DEFAULT_STUDY_SUBDIR=""

TEST_TYPE=${1:-$DEFAULT_TEST_TYPE}
THICKNESS=${2:-$DEFAULT_THICKNESS}
ORIENTATION=${3:-$DEFAULT_ORIENTATION}
SPECIMEN_WIDTH=${4:-$DEFAULT_WIDTH}
PIP_PUNCH2_ID=${5:-$PIP_PUNCH2_ID}
MESH_REFINEMENT_FACTOR=${6:-$DEFAULT_MR}
MASS_SCALING_DT=${7:-$DEFAULT_MS}
PUNCH_SPEED=${8:-$DEFAULT_PS}
PUNCH_RADIUS=${9:-$DEFAULT_PR}
STUDY_SUBDIR=${10:-$DEFAULT_STUDY_SUBDIR}
PUNCH_DISPLACEMENT=${PUNCH_DISPLACEMENT:-$DEFAULT_PD}
PUNCH_VELOCITY_PROFILE=${PUNCH_VELOCITY_PROFILE:-$DEFAULT_VP}
FR_PUNCH=${FR_PUNCH:-0.0}
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

# ── Push scripts once ─────────────────────────────────────────────────────────
echo "  Pushing scripts to Euler ..."
rsync -az --checksum -e "$RSYNC_SSH_CMD" \
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
    "$SCRIPT_DIR/static_postproc_plots.py" \
    "$SCRIPT_DIR/Nakazima_BM.py" \
    "$SCRIPT_DIR/VUMAT_explicit.f" \
    "$SCRIPT_DIR/submit_one.sh" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
echo "  Done."

# ── Push modules directory ────────────────────────────────────────────────────
echo "  Pushing modules ..."
rsync -az --checksum -e "$RSYNC_SSH_CMD" "$SCRIPT_DIR/modules/" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/modules/"
echo "  Done."
echo ""

# ── Push PiP geometry directories ────────────────────────────────────────────
if [ "$TEST_TYPE" = "pip" ]; then
    echo "  Pushing PiP_Punches and PiP_Geometries ..."
    rsync -az --checksum -e "$RSYNC_SSH_CMD" "$SCRIPT_DIR/PiP_Punches/" \
        "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/PiP_Punches/"
    rsync -az --checksum -e "$RSYNC_SSH_CMD" "$SCRIPT_DIR/PiP_Geometries/" \
        "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/PiP_Geometries/"
fi
echo "  Done."
echo ""

# ── Launch build+submit on Euler via tmux ─────────────────────
_pip_id_arg="${PIP_PUNCH2_ID:-none}"
_study_subdir_arg="${STUDY_SUBDIR:-}"
_bm_env="EULER_DIR=${EULER_DIR} EULER_SCRATCH_ROOT=${EULER_SCRATCH_ROOT} NUM_CPUS=${NUM_CPUS} ABAQUS_MEMORY_PERCENT=${ABAQUS_MEMORY_PERCENT} SLURM_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK} SLURM_MEM_PER_CPU_GB=${SLURM_MEM_PER_CPU_GB} SLURM_TIME_LIMIT=${SLURM_TIME_LIMIT} ENABLE_SYMMETRIES=${ENABLE_SYMMETRIES} PUNCH_DISPLACEMENT=${PUNCH_DISPLACEMENT} BM_MESH_USE_MANUAL=${BM_MESH_USE_MANUAL} BM_MESH_TAG=${BM_MESH_TAG} BM_MIRROR=${BM_MIRROR} BM_P_INNER_X=${BM_P_INNER_X} BM_P_INNER_R=${BM_P_INNER_R} BM_P_CIRCLE_R=${BM_P_CIRCLE_R} BM_P_XZPLANE_1=${BM_P_XZPLANE_1} BM_W200_SECTION1_Y=${BM_W200_SECTION1_Y} BM_W200_SECTION2_R=${BM_W200_SECTION2_R} BM_W200_SECTION3_R=${BM_W200_SECTION3_R} BM_MESH_SECTION1_X=${BM_MESH_SECTION1_X} BM_MESH_SECTION1_Y=${BM_MESH_SECTION1_Y} BM_MESH_SECTION2_X=${BM_MESH_SECTION2_X} BM_MESH_SECTION2_Y=${BM_MESH_SECTION2_Y} BM_MESH_SECTION3_Y=${BM_MESH_SECTION3_Y} BM_MESH_SECTION3_1_Y=${BM_MESH_SECTION3_1_Y} BM_MESH_SECTION4_Y=${BM_MESH_SECTION4_Y} BM_MESH_W200_SECTION1=${BM_MESH_W200_SECTION1} BM_MESH_W200_SECTION2=${BM_MESH_W200_SECTION2} BM_MESH_W200_SECTION3=${BM_MESH_W200_SECTION3} BM_MESH_W200_SECTION4=${BM_MESH_W200_SECTION4}"

echo "  Launching submit_one.sh on Euler in tmux session 'deploy' ..."
"${SSH_CMD[@]}" "${EULER_USER}@${EULER_HOST}" "
    tmux kill-session -t deploy 2>/dev/null || true
    tmux new-session -d -s deploy \
        'PUNCH_RADIUS=${PUNCH_RADIUS} PUNCH_SPEED=${PUNCH_SPEED} PUNCH_DISPLACEMENT=${PUNCH_DISPLACEMENT} PUNCH_VELOCITY_PROFILE=${PUNCH_VELOCITY_PROFILE} FR_PUNCH=${FR_PUNCH} MESH_BACKEND=${MESH_BACKEND} N_THICKNESS_SEEDS=${N_THICKNESS_SEEDS} ${_bm_env} bash ${EULER_DIR}/submit_one.sh ${TEST_TYPE} ${THICKNESS} ${ORIENTATION} ${SPECIMEN_WIDTH} ${_pip_id_arg} ${MESH_REFINEMENT_FACTOR} ${MASS_SCALING_DT} ${_study_subdir_arg} \
         > ${EULER_DIR}/submit_one.log 2>&1'
"

echo "=============================================="
echo "  Scripts pushed. Build running on Euler."
echo ""
echo "  Attach to watch live:"
echo "    ssh ${EULER_USER}@${EULER_HOST}"
echo "    tmux attach -t deploy"
echo ""
echo "  Or tail the log:"
echo "    ssh ${EULER_USER}@${EULER_HOST} 'tail -f ${EULER_DIR}/submit_one.log'"
echo "=============================================="
