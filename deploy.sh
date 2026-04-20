#!/bin/bash
# =============================================================
# deploy.sh  —  Push config.py, build model on login node, submit solver job
# Run this from your local Mac:
#   ./deploy.sh
# =============================================================

set -e

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================================="
echo "  deploy.sh — push + build + submit"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── 1. Read parameters (positional args > env > config.py defaults) ───
DEFAULT_TEST_TYPE=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.TEST_TYPE)")
DEFAULT_THICKNESS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.BLANK_THICKNESS)")
DEFAULT_ORIENTATION=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(int(config.MATERIAL_ORIENTATION_ANGLE))")
DEFAULT_WIDTH=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.SPECIMEN_WIDTH)")
PIP_PUNCH2_ID=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(getattr(config, 'PIP_PUNCH2_ID', '') or '')")

TEST_TYPE=${1:-$DEFAULT_TEST_TYPE}
THICKNESS=${2:-$DEFAULT_THICKNESS}
ORIENTATION=${3:-$DEFAULT_ORIENTATION}
SPECIMEN_WIDTH=${4:-$DEFAULT_WIDTH}

echo "  Pushing scripts and modules ..."
scp "$SCRIPT_DIR/config.py" \
    "$SCRIPT_DIR/build_model.py" \
    "$SCRIPT_DIR/run_cluster.sh" \
    "$SCRIPT_DIR/postproc.py" \
    "$SCRIPT_DIR/postproc_movie.py" \
    "$SCRIPT_DIR/plot_results.py" \
    "$SCRIPT_DIR/plot_flc.py" \
    "$SCRIPT_DIR/run_flc.sh" \
    "$SCRIPT_DIR/VUMAT_explicit.f" \
    "$SCRIPT_DIR/submit_one.sh" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
scp -r "$SCRIPT_DIR/modules" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"

# ── Push PiP geometry directories ─────────────────────────────
if [ "$TEST_TYPE" = "pip" ]; then
    echo "  Pushing PiP_Punches and PiP_Geometries ..."
    scp -r "$SCRIPT_DIR/PiP_Punches" "$SCRIPT_DIR/PiP_Geometries" \
        "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
fi
echo "  Done."
echo ""

# ── Launch build+submit on Euler via tmux ─────────────────────
_pip_id_arg="${PIP_PUNCH2_ID:-none}"

echo "  Launching submit_one.sh on Euler in tmux session 'deploy' ..."
ssh "${EULER_USER}@${EULER_HOST}" "
    tmux kill-session -t deploy 2>/dev/null || true
    tmux new-session -d -s deploy \
        'bash ${EULER_DIR}/submit_one.sh ${TEST_TYPE} ${THICKNESS} ${ORIENTATION} ${SPECIMEN_WIDTH} ${_pip_id_arg} \
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
