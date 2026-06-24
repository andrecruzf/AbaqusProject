#!/bin/bash
# =============================================================
# run_postproc_odb.sh  —  Run postproc + plot for any ODB path via SLURM.
#
# Usage (on Euler login node):
#   sbatch run_postproc_odb.sh <ODB_PATH>
#
# Example:
#   sbatch run_postproc_odb.sh \
#     /cluster/scratch/acruzfaria/FLC_nakazima_t1p25_ang0/Naka100_W200_t1p25_ang0_ms1e6_mr2/Naka100_W200_t1p25_ang0_ms1e6_mr2.odb
# =============================================================

#SBATCH --job-name=postproc_odb
#SBATCH --output=postproc_odb_%j.out
#SBATCH --error=postproc_odb_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=8G
#SBATCH --time=01:30:00
#SBATCH --partition=normal.4h

set -e

ODB="$1"
if [ -z "$ODB" ]; then
    echo "Usage: sbatch run_postproc_odb.sh <ODB_PATH>"
    exit 1
fi
if [ ! -f "$ODB" ]; then
    echo "ERROR: ODB not found: $ODB"
    exit 1
fi

# Remove a stale Abaqus lock file: if a sim was killed the leftover .lck makes
# Abaqus open the ODB in a degraded mode (only a few frames read -> garbage
# strains).  No sim should be writing this ODB at post-processing time.
if [ -f "${ODB%.odb}.lck" ]; then
    echo "  removing stale lock ${ODB%.odb}.lck"
    rm -f "${ODB%.odb}.lck"
fi

PROJ_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
SCRATCH_DIR="$(dirname "$ODB")"
JOB_NAME="$(basename "$ODB" .odb)"

echo "=============================================="
echo "  run_postproc_odb.sh"
echo "  ODB       : $ODB"
echo "  Output dir: $SCRATCH_DIR"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

module load stack/2024-06
module load abaqus/2023

echo "--- Step 1: extracting CSVs ---"
# Necking-zone selection is now fully geometric (crack line -> 3 mm band ->
# Engin alpha-threshold); no anchor-mode env var needed.
abaqus python "${PROJ_DIR}/postproc.py" -- "$ODB"

echo "--- Step 2: rendering EQPS movie ---"
ODB_PATH="$ODB" xvfb-run -a abaqus cae noGUI="${PROJ_DIR}/postproc_movie.py" \
    || echo "WARNING: movie step failed, continuing."

echo "--- Step 3: generating plots ---"
module load python/3.11.6
python3 -c "import matplotlib" 2>/dev/null || pip install --user matplotlib
python3 "${PROJ_DIR}/plot_results.py" "$SCRATCH_DIR"

if [[ "$SCRATCH_DIR" == /cluster/scratch/acruzfaria/* ]]; then
    REL_DIR="${SCRATCH_DIR#/cluster/scratch/acruzfaria/}"
    OUT_DIR="${PROJ_DIR}/${REL_DIR}"
    if [ -d "$OUT_DIR" ]; then
        echo "--- Step 4: copying outputs back to home ---"
        copy_result_file() {
            local f="$1"
            local src="${SCRATCH_DIR}/${f}"
            local dst="${OUT_DIR}/${f}"
            local tmp="${dst}.tmp.$$"

            if [ ! -e "$src" ]; then
                echo "  WARNING: ${f} missing in scratch"
                return 0
            fi
            if [ ! -s "$src" ]; then
                echo "  WARNING: ${f} is empty in scratch"
                return 0
            fi

            rm -f "$tmp"
            if cp "$src" "$tmp" && mv "$tmp" "$dst"; then
                echo "  ${f} -> ${OUT_DIR}/"
            else
                local rc=$?
                rm -f "$tmp"
                echo "  WARNING: failed to copy ${f} from scratch to home (rc=$rc; check disk quota/free space)"
            fi
        }

        CORE_OUTPUTS=(
            elout.csv
            global.csv
            strain_path.csv
            strain_cluster.csv
            strain_neighborhood.csv
            strain_cluster_faces.csv
            specimen_outline.csv
            forming_limits.csv
            energy_data.csv
            punch_fd.csv
            postproc_plots.pdf
            "${JOB_NAME}_movie.webm"
            "${JOB_NAME}_cut.webm"
        )
        for f in "${CORE_OUTPUTS[@]}"; do
            copy_result_file "$f"
        done
        if [[ "${POSTPROC_WRITE_DOME_HISTORY:-0}" == "1" ]]; then
            copy_result_file strain_dome.csv
        fi

        cp /tmp/postproc_movie_out.txt "$OUT_DIR/" 2>/dev/null \
            && echo "  postproc_movie_out.txt -> ${OUT_DIR}/" \
            || echo "  WARNING: postproc_movie_out.txt not found"
    else
        echo "WARNING: home output dir not found, leaving outputs in scratch: $OUT_DIR"
    fi
fi

echo "=============================================="
echo "  Done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Outputs in: $SCRATCH_DIR"
echo "=============================================="
