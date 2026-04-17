#!/bin/bash
# =============================================================
# run_postproc.sh  —  Run postproc.py on a set of ODBs via SLURM.
#
# Usage (from login node):
#   sbatch run_postproc.sh                          # all default widths
#   sbatch --export=ALL,WIDTHS="20 50 80" run_postproc.sh
#   sbatch --export=ALL,TEST_TYPE=marciniak,BLANK_THICKNESS=1.5 run_postproc.sh
#
# Reads TEST_TYPE, BLANK_THICKNESS, MATERIAL_ORIENTATION_ANGLE from env
# (set via --export) or falls back to the values in config.py.
# =============================================================

#SBATCH --job-name=postproc
#SBATCH --output=postproc_%j.out
#SBATCH --error=postproc_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=8G
#SBATCH --time=01:00:00

set -e

module load stack/2024-06
module load abaqus/2023

PROJ_DIR="$SLURM_SUBMIT_DIR"

# ── Resolve parameters (env override or config.py defaults) ───
TEST_TYPE=${TEST_TYPE:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(config.TEST_TYPE)")}
THICKNESS=${BLANK_THICKNESS:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(config.BLANK_THICKNESS)")}
ORIENTATION=${MATERIAL_ORIENTATION_ANGLE:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(int(config.MATERIAL_ORIENTATION_ANGLE))")}
R_DOME=${R_DOME:-$(python3 -c "import sys; sys.path.insert(0,'$PROJ_DIR'); import config; print(config.R_DOME)")}

_t=$(python3 -c "print(str(${THICKNESS}).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")

WIDTHS=${WIDTHS:-"20 50 80 90 100 120 200"}

echo "=============================================="
echo "  run_postproc.sh"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  R_DOME      : ${R_DOME} mm"
echo "  Widths      : ${WIDTHS}"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

for W in ${WIDTHS}; do
    JOB_NAME="${_test_cap}_W${W}_t${_t}_ang${_ang}"
    ODB="/cluster/scratch/acruzfaria/${JOB_NAME}/${JOB_NAME}.odb"

    echo ""
    echo "--- ${JOB_NAME} ---"

    if [ ! -f "$ODB" ]; then
        echo "  WARNING: ODB not found: $ODB — skipping."
        continue
    fi

    R_DOME=${R_DOME} abaqus python "${PROJ_DIR}/postproc.py" -- "$ODB"

    # Copy all CSVs back to project output dir for archiving
    OUT_DIR="${PROJ_DIR}/${JOB_NAME}"
    SCRATCH_DIR="/cluster/scratch/acruzfaria/${JOB_NAME}"
    if [ -d "$OUT_DIR" ]; then
        for f in strain_path.csv forming_limits.csv energy_data.csv; do
            [ -f "${SCRATCH_DIR}/${f}" ] \
                && cp "${SCRATCH_DIR}/${f}" "$OUT_DIR/" \
                && echo "  ${f} -> ${OUT_DIR}/" \
                || echo "  WARNING: ${f} not found in scratch"
        done
    fi
done

echo ""
echo "=============================================="
echo "  All done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
