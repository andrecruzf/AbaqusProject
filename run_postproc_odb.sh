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
        for f in elout.csv global.csv strain_path.csv strain_cluster.csv strain_neighborhood.csv strain_dome.csv strain_cluster_faces.csv specimen_outline.csv forming_limits.csv energy_data.csv punch_fd.csv cov_data.csv postproc_plots.pdf "${JOB_NAME}_movie.webm" "${JOB_NAME}_cut.webm"; do
            [ -s "${SCRATCH_DIR}/${f}" ] \
                && cp "${SCRATCH_DIR}/${f}" "$OUT_DIR/" \
                && echo "  ${f} -> ${OUT_DIR}/" \
                || echo "  WARNING: ${f} not found or empty in scratch"
        done
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
