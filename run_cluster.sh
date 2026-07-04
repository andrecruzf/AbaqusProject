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
#SBATCH --time=48:00:00
#SBATCH --partition=normal.48h

# =============================================================
set -e

module load stack/2024-06
module load python/3.11.6
PYTHON3=$(which python3)   # capture before intel deactivates the module
module load abaqus/2023
module load intel-oneapi-compilers/2023.2.0 intel-oneapi-mpi/2021.10.0

NCPUS=${SLURM_CPUS_PER_TASK:-4}

# ── Step 1: Load env written by build step on login node ─────────────────────
cd "$SLURM_SUBMIT_DIR"

# Accept JOB_NAME / OUTPUT_SUBDIR from SLURM --export or last_build.env
if [ -z "$JOB_NAME" ] || [ -z "$OUTPUT_SUBDIR" ]; then
    if [ -f "$SLURM_SUBMIT_DIR/last_build.env" ]; then
        source "$SLURM_SUBMIT_DIR/last_build.env"
    else
        echo "ERROR: JOB_NAME/OUTPUT_SUBDIR not set and last_build.env is missing."
        exit 1
    fi
fi

WORK_DIR="$SLURM_SUBMIT_DIR/$OUTPUT_SUBDIR"
if [ -z "${EULER_SCRATCH_ROOT:-}" ]; then
    EULER_SCRATCH_ROOT=$("$PYTHON3" -c "import os, sys; sys.path.insert(0, '$SLURM_SUBMIT_DIR'); import config; print(getattr(config, 'EULER_SCRATCH_ROOT', '/cluster/scratch/' + os.environ.get('USER', '')))" 2>/dev/null || printf "/cluster/scratch/%s" "${USER:-$LOGNAME}")
fi
SCRATCH_DIR="${EULER_SCRATCH_ROOT%/}/$OUTPUT_SUBDIR"
VUMAT="$WORK_DIR/VUMAT_explicit.f"

if [ ! -d "$WORK_DIR" ]; then
    echo "ERROR: work directory not found: $WORK_DIR"
    exit 1
fi
if [ ! -f "$WORK_DIR/${JOB_NAME}.inp" ]; then
    echo "ERROR: input deck missing: $WORK_DIR/${JOB_NAME}.inp"
    echo "       Contents of work dir:"
    ls -la "$WORK_DIR"
    exit 1
fi
if [ ! -f "$VUMAT" ]; then
    echo "ERROR: VUMAT missing: $VUMAT"
    exit 1
fi

# ── Step 2: Run solver in scratch ─────────────────────────────────────────────
# Solver output (ODB, dat, fil, ...) goes to scratch to avoid filling home (50 GB limit).
# Scratch is auto-deleted after 2 weeks — results are extracted before that in steps 3-4.
mkdir -p "$SCRATCH_DIR"
rm -f "$SCRATCH_DIR/${JOB_NAME}.lck"
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

echo "  strain_path.csv, forming_limits.csv, energy_data.csv extracted."

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
copy_result_file() {
    local f="$1"
    local src="$SCRATCH_DIR/$f"
    local dst="$WORK_DIR/$f"
    local tmp="${dst}.tmp.$$"

    if [ ! -e "$src" ]; then
        echo "  WARNING: $f missing in scratch"
        return 0
    fi
    if [ ! -s "$src" ]; then
        echo "  WARNING: $f is empty in scratch"
        return 0
    fi

    rm -f "$tmp"
    if cp "$src" "$tmp" && mv "$tmp" "$dst"; then
        echo "  $f copied"
    else
        local rc=$?
        rm -f "$tmp"
        echo "  WARNING: failed to copy $f from scratch to home (rc=$rc; check disk quota/free space)"
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
    cov_data.csv
    "${JOB_NAME}_movie.webm"
    "${JOB_NAME}_cut.webm"
)
for f in "${CORE_OUTPUTS[@]}"; do
    copy_result_file "$f"
done

# ── Step 6: Per-specimen diagnostic plots ────────────────────────────────────
echo "=============================================="
echo "  Per-specimen plots"
echo "  Start : $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
"$PYTHON3" "$SLURM_SUBMIT_DIR/plot_results.py" "$WORK_DIR" 2>&1 \
    && echo "  Plots written to $WORK_DIR/" \
    || echo "  WARNING: plot_results.py failed (see traceback above)."

# Large optional diagnostic: keep this last so a quota hit does not block
# small CSVs needed by the app and plots.
echo "=============================================="
echo "  Copying optional large CSV ..."
echo "=============================================="
copy_result_file strain_dome.csv

echo "=============================================="
echo "  All done: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  ODB in scratch (auto-deleted in 2 weeks): $SCRATCH_DIR/${JOB_NAME}.odb"
echo "  Results in home: $WORK_DIR/"
echo "=============================================="
