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
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --mem-per-cpu=4G
#SBATCH --time=24:00:00

# =============================================================
set -e

module load stack/2024-06
module load abaqus/2023
module load intel-oneapi-compilers/2023.2.0 intel-oneapi-mpi/2021.10.0

NCPUS=${SLURM_CPUS_PER_TASK:-4}

# ── Step 1: Load env written by build step on login node ─────────────────────
cd "$SLURM_SUBMIT_DIR"

# Accept JOB_NAME / OUTPUT_SUBDIR from SLURM --export or last_build.env
if [ -z "$JOB_NAME" ] || [ -z "$OUTPUT_SUBDIR" ]; then
    source "$SLURM_SUBMIT_DIR/last_build.env"
fi

WORK_DIR="$SLURM_SUBMIT_DIR/$OUTPUT_SUBDIR"
SCRATCH_DIR="/cluster/scratch/acruzfaria/$OUTPUT_SUBDIR"
VUMAT="$WORK_DIR/VUMAT_explicit.f"

# ── Step 2: Run solver in scratch ─────────────────────────────────────────────
# Solver output (ODB, dat, fil, ...) goes to scratch to avoid filling home (50 GB limit).
# Scratch is auto-deleted after 2 weeks — results are extracted before that in steps 3-4.
mkdir -p "$SCRATCH_DIR"
cp "$WORK_DIR/${JOB_NAME}.inp" "$SCRATCH_DIR/"
cp "$VUMAT" "$SCRATCH_DIR/"

echo "=============================================="
echo "  Abaqus Explicit — Nakazima"
echo "  Job      : $JOB_NAME"
echo "  CPUs     : $NCPUS"
echo "  HOME_DIR : $WORK_DIR"
echo "  SCRATCH  : $SCRATCH_DIR"
echo "  Start    : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

cd "$SCRATCH_DIR"

abaqus job="$JOB_NAME"                    \
       user="VUMAT_explicit.f"            \
       cpus="$NCPUS"                      \
       mp_mode=threads                    \
       double=explicit                    \
       interactive

echo ""
echo "Done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Results: $SCRATCH_DIR/${JOB_NAME}.odb"

# ── Step 3: Extract strain path ───────────────────────────────────────────────
echo "=============================================="
echo "  Post-processing — strain path"
echo "  Start : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

cd "$SLURM_SUBMIT_DIR"
abaqus python postproc.py -- "$SCRATCH_DIR/${JOB_NAME}.odb"

echo "  elout.csv + global.csv written."

# ── Step 4: Render SDV1 animation ────────────────────────────────────────────
echo "=============================================="
echo "  Post-processing — EQPS movie"
echo "  Start : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

ODB_PATH="$SCRATCH_DIR/${JOB_NAME}.odb" xvfb-run -a abaqus cae noGUI="$SLURM_SUBMIT_DIR/postproc_movie.py" || echo "  WARNING: movie step failed, continuing."

echo "  Movie written."

# ── Step 5: Copy results from scratch back to home ────────────────────────────
echo "=============================================="
echo "  Copying results to home ..."
echo "=============================================="
for f in elout.csv global.csv strain_path.csv forming_limits.csv energy_data.csv punch_fd.csv; do
    cp "$SCRATCH_DIR/$f" "$WORK_DIR/" 2>/dev/null \
        && echo "  $f ✓" \
        || echo "  WARNING: $f not found in scratch"
done
cp "$SCRATCH_DIR/${JOB_NAME}_movie.webm" "$WORK_DIR/" 2>/dev/null \
    && echo "  ${JOB_NAME}_movie.webm ✓" \
    || echo "  WARNING: movie not found in scratch (ffmpeg may have failed)"

echo "=============================================="
echo "  All done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  ODB in scratch (auto-deleted in 2 weeks): $SCRATCH_DIR/${JOB_NAME}.odb"
echo "  Results in home: $WORK_DIR/"
echo "=============================================="
