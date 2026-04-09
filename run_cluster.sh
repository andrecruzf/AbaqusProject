#!/bin/bash
# =============================================================
# run_cluster.sh  —  ETH Euler SLURM submission
# =============================================================
# Step 1 (login node): generate the .inp
#   abaqus cae noGUI=build_model.py
#
# Step 2 (submit solver job):
#   sbatch run_cluster.sh
# =============================================================

#SBATCH --job-name=nakazima
#SBATCH --output=nakazima_%j.out
#SBATCH --error=nakazima_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --mem-per-cpu=4G
#SBATCH --time=10:00:00

# =============================================================
set -e

module load stack/2024-06
module load abaqus/2023
module load intel-oneapi-compilers/2023.2.0 intel-oneapi-mpi/2021.10.0

NCPUS=${SLURM_CPUS_PER_TASK:-4}

# ── Step 1: Build model (generates .inp and writes last_build.env) ────────────
echo "=============================================="
echo "  Build — $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

cd "$SLURM_SUBMIT_DIR"
abaqus cae noGUI="$SLURM_SUBMIT_DIR/build_model.py"

# Source the env written by job.py to get the correct JOB_NAME / OUTPUT_SUBDIR
# shellcheck source=last_build.env
source "$SLURM_SUBMIT_DIR/last_build.env"

WORK_DIR="$SLURM_SUBMIT_DIR/$OUTPUT_SUBDIR"
VUMAT="$WORK_DIR/VUMAT_explicit.f"

# ── Step 2: Run solver ────────────────────────────────────────────────────────
echo "=============================================="
echo "  Abaqus Explicit — Nakazima"
echo "  Job     : $JOB_NAME"
echo "  CPUs    : $NCPUS"
echo "  WORK_DIR: $WORK_DIR"
echo "  Start   : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

cd "$WORK_DIR"

abaqus job="$JOB_NAME"   \
       user="$VUMAT"      \
       cpus="$NCPUS"      \
       mp_mode=threads    \
       double=explicit    \
       interactive

echo ""
echo "Done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Results: $WORK_DIR/${JOB_NAME}.odb"

# ── Step 3: Extract strain path ───────────────────────────────────────────────
echo "=============================================="
echo "  Post-processing — strain path"
echo "  Start : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

cd "$SLURM_SUBMIT_DIR"
abaqus python postproc.py -- "$WORK_DIR/${JOB_NAME}.odb"

echo "  strain_path.csv written."

# ── Step 4: Render SDV1 animation ────────────────────────────────────────────
echo "=============================================="
echo "  Post-processing — EQPS movie"
echo "  Start : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

ODB_PATH="$WORK_DIR/${JOB_NAME}.odb" xvfb-run -a abaqus cae noGUI="$SLURM_SUBMIT_DIR/postproc_movie.py" || echo "  WARNING: movie step failed, continuing."

echo "  Movie written."
echo "=============================================="
echo "  All done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
