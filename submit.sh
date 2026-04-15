#!/bin/bash
# =============================================================
# submit.sh  —  Submit SLURM job and tail output live
# Usage: ./submit.sh
# =============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Submit and capture job ID
JOB_ID=$(sbatch --parsable run_cluster.sh)
echo "Submitted job $JOB_ID — waiting for output..."

OUT_FILE="nakazima_${JOB_ID}.out"
ERR_FILE="nakazima_${JOB_ID}.err"

# Wait for the output file to appear
while [ ! -f "$OUT_FILE" ]; do
    sleep 1
done

echo "--- stdout ($OUT_FILE) ---"
tail -f "$OUT_FILE" &
TAIL_OUT=$!

echo "--- stderr ($ERR_FILE) ---"
# Wait for err file too, then tail it
while [ ! -f "$ERR_FILE" ]; do sleep 1; done
tail -f "$ERR_FILE" &
TAIL_ERR=$!

# Stop tailing once the job finishes
while squeue -j "$JOB_ID" -h &>/dev/null; do
    sleep 10
done

sleep 2  # let tail flush final output
kill $TAIL_OUT $TAIL_ERR 2>/dev/null
echo ""
echo "Job $JOB_ID finished."
