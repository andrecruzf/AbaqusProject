#!/bin/bash
# =============================================================
# deploy_study.sh  —  Mass scaling × mesh refinement study.
#                     Runs locally; calls submit_one.sh on Euler
#                     once per (MR, MS) combination.
#
# Usage:
#   ./deploy_study.sh [thickness] [orientation]
#   ./deploy_study.sh 1.75 0
#
# Grid (edit here to change):
#   MR_VALUES  — MESH_REFINEMENT_FACTOR values
#   MS_VALUES  — MASS_SCALING_DT values
#   WIDTH      — specimen width (W200 = most sensitive)
# =============================================================

set -e

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TEST_TYPE="nakazima"
THICKNESS=${1:-$(python3 -c "import sys; sys.path.insert(0,'${SCRIPT_DIR}'); import config; print(config.BLANK_THICKNESS)")}
ORIENTATION=${2:-$(python3 -c "import sys; sys.path.insert(0,'${SCRIPT_DIR}'); import config; print(int(config.MATERIAL_ORIENTATION_ANGLE))")}
WIDTH=200

# Study grid
MR_VALUES=(1 2 4 8)
MS_VALUES=(1e-7 1e-6 1e-5 1e-4)

_t=$(python3 -c "print(str(float(${THICKNESS})).replace('.','p'))")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")
STUDY_SUBDIR="study_ms_mr_W${WIDTH}_t${_t}_ang${_ang}"
STUDY_DIR="${EULER_DIR}/${STUDY_SUBDIR}"

echo "=============================================="
echo "  deploy_study.sh — mass scaling × mesh study"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Width       : W${WIDTH}"
echo "  MR values   : ${MR_VALUES[*]}"
echo "  MS values   : ${MS_VALUES[*]}"
echo "  Study dir   : ${STUDY_SUBDIR}/"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# ── Push all scripts once ─────────────────────────────────────
echo "  Pushing scripts to Euler ..."
scp -q "$SCRIPT_DIR/config.py" \
    "$SCRIPT_DIR/build_model.py" \
    "$SCRIPT_DIR/screenshot_mesh.py" \
    "$SCRIPT_DIR/run_cluster.sh" \
    "$SCRIPT_DIR/postproc.py" \
    "$SCRIPT_DIR/postproc_movie.py" \
    "$SCRIPT_DIR/plot_results.py" \
    "$SCRIPT_DIR/plot_study.py" \
    "$SCRIPT_DIR/run_plot_study.sh" \
    "$SCRIPT_DIR/VUMAT_explicit.f" \
    "$SCRIPT_DIR/submit_one.sh" \
    "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
scp -q -r "$SCRIPT_DIR/modules" "${EULER_USER}@${EULER_HOST}:${EULER_DIR}/"
echo "  Done."

ssh "${EULER_USER}@${EULER_HOST}" "mkdir -p ${STUDY_DIR}/logs"

# ── Loop over (MR, MS) grid — sequential blocking SSH calls ──
JOB_IDS=()

for MS in "${MS_VALUES[@]}"; do
    for MR in "${MR_VALUES[@]}"; do
        echo "----------------------------------------------"
        echo "  MS=${MS}  MR=${MR}  →  building on Euler ..."
        LOG="${STUDY_DIR}/logs/submit_ms${MS}_mr${MR}.log"

        JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" \
            "bash ${EULER_DIR}/submit_one.sh \
                ${TEST_TYPE} ${THICKNESS} ${ORIENTATION} ${WIDTH} \
                none ${MR} ${MS} ${STUDY_SUBDIR} \
             2>&1 | tee ${LOG} | grep '^JOB_ID=' | cut -d= -f2")

        if [ -z "$JOB_ID" ]; then
            echo "  ERROR: no job ID returned for MS=${MS} MR=${MR} — check ${LOG}"
            continue
        fi

        JOB_IDS+=("${JOB_ID}")
        echo "  Submitted SLURM job ${JOB_ID}"
    done
done

echo "=============================================="
echo "  All ${#JOB_IDS[@]} jobs submitted."
echo "  Job IDs: ${JOB_IDS[*]}"

if [ ${#JOB_IDS[@]} -eq 0 ]; then
    echo "  ERROR: no jobs submitted — aborting aggregation."
    exit 1
fi

# ── Submit plot_study aggregation once all solver jobs complete ─
DEPENDENCY="afterok:$(IFS=:; echo "${JOB_IDS[*]}")"

echo "----------------------------------------------"
echo "  Submitting plot_study aggregation job ..."
PLOT_JOB_ID=$(ssh "${EULER_USER}@${EULER_HOST}" "cd ${EULER_DIR} && sbatch \
    --dependency='${DEPENDENCY}' \
    --job-name='plot_study_W${WIDTH}' \
    --output='${STUDY_DIR}/logs/plot_study_%j.out' \
    --error='${STUDY_DIR}/logs/plot_study_%j.err' \
    --export=ALL,STUDY_DIR='${STUDY_DIR}' \
    --parsable run_plot_study.sh")

echo "  Plot job  : ${PLOT_JOB_ID}  (held until all solver jobs complete)"
echo "  Results   : ${STUDY_DIR}/study_results.pdf"
echo "  $(date '+%Y-%m-%d %H:%M:%S') — done"
echo "=============================================="
