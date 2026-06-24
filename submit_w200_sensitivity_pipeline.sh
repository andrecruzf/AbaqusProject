#!/bin/bash
# =============================================================
# submit_w200_sensitivity_pipeline.sh
# Runs ON Euler. Builds and submits the W200 mass-scaling x mesh grid
# through submit_one.sh, then queues plot_study aggregation.
# =============================================================

set -e

EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

TEST_TYPE="${TEST_TYPE:-nakazima}"
THICKNESS="${THICKNESS:-1.5}"
ORIENTATION="${ORIENTATION:-0}"
WIDTH="${WIDTH:-200}"
PUNCH_SPEED="${PUNCH_SPEED:-1.0}"
MR_VALUES=(${MR_VALUES:-4 2 1})
MS_VALUES=(${MS_VALUES:-1e-3 1e-4 1e-5})

_t=$(python3 -c "print(str(float('${THICKNESS}')).replace('.','p'))")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")
_ps=$(python3 -c "v=float('${PUNCH_SPEED}'); print('_ps'+('%.4g'%v).replace('.','p') if abs(v-5.0)>1e-6 else '')")
STUDY_SUBDIR="${STUDY_SUBDIR:-study_ms_mr_W${WIDTH}_t${_t}_ang${_ang}${_ps}_40hz_baseline}"
STUDY_DIR="${EULER_DIR}/${STUDY_SUBDIR}"

mkdir -p "${STUDY_DIR}/logs"

echo "=============================================="
echo "  W200 sensitivity pipeline"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Width       : W${WIDTH}"
echo "  Punch speed : ${PUNCH_SPEED} mm/s"
echo "  MR values   : ${MR_VALUES[*]}"
echo "  MS values   : ${MS_VALUES[*]}"
echo "  Study dir   : ${STUDY_SUBDIR}/"
echo "  Start       : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

JOB_IDS=()

for MS in "${MS_VALUES[@]}"; do
    for MR in "${MR_VALUES[@]}"; do
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
        JOB_NAME="Naka100_W${WIDTH}_t${_t}_ang${_ang}${_ms_suffix}${_mr_suffix}${_ps}"

        if [ -d "${STUDY_DIR}/${JOB_NAME}" ]; then
            echo "----------------------------------------------"
            echo "  SKIP existing ${JOB_NAME}"
            continue
        fi

        echo "----------------------------------------------"
        echo "  MS=${MS}  MR=${MR}  -> submit_one.sh"
        LOG="${STUDY_DIR}/logs/submit_ms${MS}_mr${MR}.log"

        set +e
        PUNCH_SPEED="${PUNCH_SPEED}" bash "${EULER_DIR}/submit_one.sh" \
            "${TEST_TYPE}" "${THICKNESS}" "${ORIENTATION}" "${WIDTH}" \
            none "${MR}" "${MS}" "${STUDY_SUBDIR}" \
            > "${LOG}" 2>&1
        rc=$?
        set -e

        if [ "${rc}" -ne 0 ]; then
            echo "  ERROR: submit_one.sh failed for MS=${MS} MR=${MR}; see ${LOG}"
            tail -40 "${LOG}" || true
            continue
        fi

        JOB_ID=$(grep '^JOB_ID=' "${LOG}" | tail -1 | cut -d= -f2)

        if [ -z "${JOB_ID}" ]; then
            echo "  ERROR: no JOB_ID returned for MS=${MS} MR=${MR}; see ${LOG}"
            continue
        fi

        JOB_IDS+=("${JOB_ID}")
        echo "  Submitted ${JOB_ID}"
    done
done

echo "=============================================="
echo "  Submitted ${#JOB_IDS[@]} solver jobs"
echo "  Job IDs: ${JOB_IDS[*]}"

if [ "${#JOB_IDS[@]}" -eq 0 ]; then
    echo "  ERROR: no solver jobs submitted; not queuing aggregation."
    exit 1
fi

DEPENDENCY="afterok:$(IFS=:; echo "${JOB_IDS[*]}")"
PLOT_JOB_ID=$(cd "${EULER_DIR}" && sbatch \
    --dependency="${DEPENDENCY}" \
    --job-name="plot_study_W${WIDTH}" \
    --output="${STUDY_DIR}/logs/plot_study_%j.out" \
    --error="${STUDY_DIR}/logs/plot_study_%j.err" \
    --export=ALL,STUDY_DIR="${STUDY_DIR}" \
    --parsable run_plot_study.sh)

echo "  Plot job: ${PLOT_JOB_ID} (${DEPENDENCY})"
echo "  Results : ${STUDY_DIR}/study_results.pdf"
echo "  Done    : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
