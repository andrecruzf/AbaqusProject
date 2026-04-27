#!/bin/bash
# =============================================================
# deploy_all.sh  —  Push scripts, build all models, submit solver
#                   jobs, then submit FLC aggregation job.
#
# Usage:
#   ./deploy_all.sh                            # all defaults from config.py
#   ./deploy_all.sh marciniak                  # override test type
#   ./deploy_all.sh marciniak 1.5              # override test type + thickness
#   ./deploy_all.sh marciniak 1.5 45           # + orientation angle (degrees)
#   ./deploy_all.sh marciniak 1.5 45 50 80 100 # + specific widths
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

TEST_TYPE=${1:-$DEFAULT_TEST_TYPE}
THICKNESS=${2:-$DEFAULT_THICKNESS}
ORIENTATION=${3:-$DEFAULT_ORIENTATION}
# MESH_REFINEMENT_FACTOR can be set as an env var before calling this script,
# or it defaults to the value from config.py.
MESH_REFINEMENT_FACTOR=${MESH_REFINEMENT_FACTOR:-$DEFAULT_MR}
shift $(( $# < 3 ? $# : 3 ))
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
FLC_OUTDIR="FLC_${TEST_TYPE}_t${_t}_ang${_ang}"

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
scp "$SCRIPT_DIR/config.py" \
    "$SCRIPT_DIR/build_model.py" \
    "$SCRIPT_DIR/run_cluster.sh" \
    "$SCRIPT_DIR/run_flc.sh" \
    "$SCRIPT_DIR/postproc.py" \
    "$SCRIPT_DIR/postproc_movie.py" \
    "$SCRIPT_DIR/plot_results.py" \
    "$SCRIPT_DIR/plot_flc.py" \
    "$SCRIPT_DIR/VUMAT_explicit.f" \
    "$SCRIPT_DIR/submit_all.sh" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"

# ── Push modules directory ────────────────────────────────────────────────────
scp -r "$SCRIPT_DIR/modules" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"

# ── Push PiP geometry directories ────────────────────────────────────────────
if [ "$TEST_TYPE" = "pip" ]; then
    echo "  Pushing PiP_Punches and PiP_Geometries ..."
    scp -r "$SCRIPT_DIR/PiP_Punches" "$SCRIPT_DIR/PiP_Geometries" \
        "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
fi
echo "  Done."
echo ""

# ── Launch build+submit loop on Euler via tmux ────────────────────────────────
_pip_id_arg="${PIP_PUNCH2_ID:-none}"

echo "  Launching submit_all.sh on Euler in tmux session 'deploy' ..."
ssh "${EULER_USER}@${EULER_HOST}" "
    tmux kill-session -t deploy 2>/dev/null || true
    tmux new-session -d -s deploy \
        'bash ${EULER_DIR}/submit_all.sh ${TEST_TYPE} ${THICKNESS} ${ORIENTATION} ${_pip_id_arg} ${MESH_REFINEMENT_FACTOR} ${CUSTOM_WIDTHS} ${WIDTHS[*]} \
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
