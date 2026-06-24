#!/bin/bash
# =============================================================
# collect_results.sh  —  Download results from Euler and plot FLC
#
# Usage:
#   ./collect_results.sh                             # all defaults from config.py
#   ./collect_results.sh nakazima 1.5               # test type + thickness
#   ./collect_results.sh nakazima 1.5 45            # + orientation angle
#   ./collect_results.sh nakazima 1.5 45 50 80 100  # + specific widths
#   ./collect_results.sh nakazima 1.5 0 --no-movies # skip movie download
# =============================================================

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DEFAULT_TEST_TYPE=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.TEST_TYPE)")
DEFAULT_THICKNESS=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(config.BLANK_THICKNESS)")
DEFAULT_ORIENTATION=$(python3 -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import config; print(int(config.MATERIAL_ORIENTATION_ANGLE))")

TEST_TYPE=${1:-$DEFAULT_TEST_TYPE}
THICKNESS=${2:-$DEFAULT_THICKNESS}
ORIENTATION=${3:-$DEFAULT_ORIENTATION}
shift $(( $# < 3 ? $# : 3 ))

DOWNLOAD_MOVIES=true
CUSTOM_WIDTHS=false
WIDTHS=()
for arg in "$@"; do
    if [ "$arg" = "--no-movies" ]; then
        DOWNLOAD_MOVIES=false
    else
        WIDTHS+=("$arg")
    fi
done
if [ ${#WIDTHS[@]} -eq 0 ]; then
    WIDTHS=(20 50 80 90 100 120 200)
else
    CUSTOM_WIDTHS=true
fi

_t=$(python3 -c "print(str(${THICKNESS}).replace('.','p'))")
_test_cap=$(python3 -c "print('${TEST_TYPE}'.capitalize())")
_ang=$(python3 -c "print(str(int(float('${ORIENTATION}'))))")

echo "=============================================="
echo "  collect_results.sh"
echo "  Test type   : ${TEST_TYPE}"
echo "  Thickness   : ${THICKNESS} mm"
echo "  Orientation : ${ORIENTATION} deg"
echo "  Widths      : ${WIDTHS[*]}"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

LOCAL_DIRS=""
for W in "${WIDTHS[@]}"; do
    JOB="${_test_cap}_W${W}_t${_t}_ang${_ang}"
    LOCAL_DIR="$SCRIPT_DIR/$JOB"
    REMOTE_DIR="${EULER_DIR}/${JOB}"

    echo ""
    echo "  ── ${JOB} ──"

    mkdir -p "$LOCAL_DIR"

    # CSVs needed for plotting
    for f in strain_path.csv forming_limits.csv energy_data.csv punch_fd.csv cov_data.csv; do
        if scp "${EULER_USER}@${EULER_HOST}:${REMOTE_DIR}/${f}" "$LOCAL_DIR/" 2>/dev/null; then
            echo "    ${f} ✓"
        else
            echo "    ${f} — not found (skipping)"
        fi
    done

    # movie
    if [ "$DOWNLOAD_MOVIES" = true ]; then
        if scp "${EULER_USER}@${EULER_HOST}:${REMOTE_DIR}/${JOB}_movie.webm" "$LOCAL_DIR/" 2>/dev/null; then
            echo "    ${JOB}_movie.webm ✓"
        else
            echo "    movie — not found (skipping)"
        fi
    fi

    LOCAL_DIRS="$LOCAL_DIRS $LOCAL_DIR"
done

echo ""
echo "=============================================="
if [[ "$TEST_TYPE" == "nakazima" || "$TEST_TYPE" == "marciniak" ]] && [ "$CUSTOM_WIDTHS" = false ]; then
    FLC_PDF="$SCRIPT_DIR/FLC_${TEST_TYPE}_t${_t}_ang${_ang}.pdf"
    echo "  Plotting FLC → ${FLC_PDF} ..."
    cd "$SCRIPT_DIR"
    python3 plot_flc.py $LOCAL_DIRS --output "$FLC_PDF"
    echo "  Done."
else
    echo "  Skipping FLC plot (test=${TEST_TYPE}, custom_widths=${CUSTOM_WIDTHS})"
fi
echo "=============================================="
