#!/bin/bash
#SBATCH -n 20
#SBATCH --mem-per-cpu=4000
#SBATCH --time=24:00:00

# -----------------------------
# Copy input files to local scratch
# cp $SCRATCH
# rsync -aq ./ ${SCRATCH}
# rsync -aq ./VUMAT_explicit.for ${SCRATCH}
# rsync -aq ./umat/ ${SCRATCH}

# -----------------------------
# Move into the scratch directory
# cd $SCRATCH

# -----------------------------
# Load necessary modules
module purge
module load stack/2024-06
module load intel-oneapi-compilers/2023.2.0
module load abaqus

# -----------------------------
# Run Abaqus with user subroutine
abaqus job=nakazima user=VUMAT_explicit.f double cpus=20

# -----------------------------
# Copy output files back to home
# rsync -av ./Job-test.odb $HOME/abaqus/results
# rsync -av ./Job-test.dat $HOME/abaqus/results
# rsync -av ./Job-test.msg $HOME/abaqus/results
# rsync -av ./Job-test.sta $HOME/abaqus/results

