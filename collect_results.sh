#!/bin/bash
# =============================================================
# collect_results.sh  —  Download results from Euler and plot FLC
#
# Usage:
#   ./collect_results.sh                   # all widths, default thickness
#   ./collect_results.sh 1.5               # all widths, thickness=1.5
#   ./collect_results.sh 1.5 50 80 100     # specific widths
#   ./collect_results.sh 1.5 --no-movies   # skip movie download
# =============================================================

EULER_USER="acruzfaria"
EULER_HOST="euler.ethz.ch"
EULER_DIR="/cluster/home/acruzfaria/AbaqusProject"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

THICKNESS=${1:-1.5}
shift || true

DOWNLOAD_MOVIES=true
WIDTHS=()
for arg in "$@"; do
    if [ "$arg" = "--no-movies" ]; then
        DOWNLOAD_MOVIES=false
    else
        WIDTHS+=("$arg")
    fi
done
if [ ${#WIDTHS[@]} -eq 0 ]; then
    WIDTHS=(20 50 80 100 120 200)
fi

_t=$(python3 -c "print(str(${THICKNESS}).replace('.','p'))")

echo "=============================================="
echo "  collect_results.sh"
echo "  Thickness : ${THICKNESS} mm"
echo "  Widths    : ${WIDTHS[*]}"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

for W in "${WIDTHS[@]}"; do
    JOB="Nakazima_W${W}_t${_t}"
    LOCAL_DIR="$SCRIPT_DIR/$JOB"
    REMOTE_DIR="${EULER_DIR}/${JOB}"

    echo ""
    echo "  ── ${JOB} ──"

    mkdir -p "$LOCAL_DIR"

    # strain path CSV
    if scp "${EULER_USER}@${EULER_HOST}:${REMOTE_DIR}/strain_path.csv" "$LOCAL_DIR/" 2>/dev/null; then
        echo "    strain_path.csv ✓"
    else
        echo "    strain_path.csv — not found (job not done?)"
    fi

    # movie
    if [ "$DOWNLOAD_MOVIES" = true ]; then
        if scp "${EULER_USER}@${EULER_HOST}:${REMOTE_DIR}/${JOB}_movie.webm" "$LOCAL_DIR/" 2>/dev/null; then
            echo "    ${JOB}_movie.webm ✓"
        else
            echo "    movie — not found (skipping)"
        fi
    fi
done

echo ""
echo "=============================================="
echo "  Plotting FLC ..."
echo "=============================================="
cd "$SCRIPT_DIR"
python3 plot_flc.py
echo "  Done → flc_plot.png"
echo "=============================================="
