#!/bin/bash
# =============================================================
# submit_postproc.sh  —  Submit post-processing + plotting jobs.
#
# Usage (from login node):
#   bash submit_postproc.sh
#   bash submit_postproc.sh --widths "20 50 80"
#   bash submit_postproc.sh --thickness 1.5 --test_type marciniak
#
# Submits two SLURM jobs:
#   1. run_postproc.sh  — abaqus python: extracts CSVs from ODBs
#   2. run_plot.sh      — regular python: generates PNGs from CSVs
#                         depends on job 1 via --dependency=afterok
# =============================================================

WIDTHS=""
THICKNESS=""
TEST_TYPE=""
ORIENTATION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --widths)      WIDTHS="$2";      shift 2 ;;
        --thickness)   THICKNESS="$2";   shift 2 ;;
        --test_type)   TEST_TYPE="$2";   shift 2 ;;
        --orientation) ORIENTATION="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# Build export string for sbatch
EXPORT="ALL"
[ -n "$WIDTHS" ]      && EXPORT="${EXPORT},WIDTHS=${WIDTHS}"
[ -n "$THICKNESS" ]   && EXPORT="${EXPORT},BLANK_THICKNESS=${THICKNESS}"
[ -n "$TEST_TYPE" ]   && EXPORT="${EXPORT},TEST_TYPE=${TEST_TYPE}"
[ -n "$ORIENTATION" ] && EXPORT="${EXPORT},MATERIAL_ORIENTATION_ANGLE=${ORIENTATION}"

# Submit job 1: postproc (abaqus python, writes CSVs)
JOB1=$(sbatch --parsable --export="${EXPORT}" run_postproc.sh)
echo "Submitted postproc job:  ${JOB1}"

# Submit job 2: plotting (regular python, reads CSVs, writes PNGs)
JOB2=$(sbatch --parsable --export="${EXPORT}" --dependency=afterok:${JOB1} run_plot.sh)
echo "Submitted plot job:      ${JOB2}  (afterok:${JOB1})"

echo ""
echo "Monitor with:  squeue -j ${JOB1},${JOB2}"
echo "Logs:          postproc_${JOB1}.out / plot_results_${JOB2}.out"
