# Nakazima / Marciniak / PiP FLC Pipeline

Automated pipeline for running Forming Limit Curve (FLC) simulations on the
ETH Euler HPC cluster. Covers model building (Abaqus CAE), solver execution
(Abaqus/Explicit + VUMAT), post-processing (strain path extraction, necking
detection, FLC aggregation), diagnostic plotting, and EQPS animation export.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [ETH Euler access setup](#eth-euler-access-setup)
3. [First-time cluster setup](#first-time-cluster-setup)
4. [Local repository setup](#local-repository-setup)
5. [Configuring a run](#configuring-a-run)
6. [Running the pipeline](#running-the-pipeline)
7. [Rendering EQPS animations](#rendering-eqps-animations----deploy_moviesh)
8. [Monitoring jobs](#monitoring-jobs)
9. [Retrieving results](#retrieving-results)
10. [Re-running post-processing only](#re-running-post-processing-only)
11. [Project structure](#project-structure)
12. [Output files reference](#output-files-reference)

---

## Prerequisites

**Local machine (Mac/Linux)**

| Tool | Version | Notes |
|------|---------|-------|
| Python 3 | ≥ 3.8 | only used to read `config.py` values in deploy scripts |
| OpenSSH | any | `ssh`, `scp` |
| ETH VPN | — | required when off campus |

No Python packages need to be installed locally — the deploy scripts only
call `python3 -c "import config; ..."` to read scalar values.

**ETH Euler (provided by IT)**

- Abaqus 2023 (`module load abaqus/2023`)
- Python 3.11 (`module load stack/2024-06 python/3.11.6`)
- Intel compilers + MPI for VUMAT compilation
- `matplotlib` (auto-installed to `~/.local` on first plot job run)

---

## ETH Euler access setup

### 1. ETH network ID

You need an ETH account with Euler access. Request access at
`https://scicomp.ethz.ch/wiki/Euler` (login with ETH credentials, request
HPC access via the form).

### 2. SSH key authentication (strongly recommended)

Password-based login is slow and will break non-interactive `scp`/`ssh` in
the deploy scripts. Set up key-based auth once:

```bash
# Generate a key if you don't already have one
ssh-keygen -t ed25519 -C "your_eth_email@ethz.ch"

# Copy your public key to Euler
ssh-copy-id YOUR_ETH_USERNAME@euler.ethz.ch
```

Test that it works without a password prompt:

```bash
ssh YOUR_ETH_USERNAME@euler.ethz.ch 'echo OK'
```

### 3. SSH config shortcut (optional but convenient)

Add to `~/.ssh/config`:

```
Host euler
    HostName euler.ethz.ch
    User YOUR_ETH_USERNAME
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
```

After this you can type `ssh euler` instead of the full address.

### 4. VPN

When off campus, connect to the ETH VPN before running any deploy script.
Download the Cisco AnyConnect client from `https://sslvpn.ethz.ch` and
connect to `sslvpn.ethz.ch`.

---

## First-time cluster setup

Run once after getting Euler access. SSH in and create the project directory:

```bash
ssh YOUR_ETH_USERNAME@euler.ethz.ch

# Create the project home directory (adjust path if desired)
mkdir -p /cluster/home/$USER/AbaqusProject

# Verify Abaqus is available
module load abaqus/2023
abaqus information=release
```

No further cluster-side setup is needed — the deploy scripts push all source
files automatically on every run.

---

## Local repository setup

### 1. Clone / copy the repository

```bash
git clone <repo-url> AbaqusProject
cd AbaqusProject
```

Or copy the project folder to your machine if you received it as an archive.

### 2. Edit deploy variables

Open `deploy.sh` (single run) and `deploy_all.sh` (full FLC sweep) and update
the three variables at the top:

```bash
EULER_USER="your_eth_username"          # ← change this
EULER_HOST="euler.ethz.ch"              # leave as-is
EULER_DIR="/cluster/home/your_eth_username/AbaqusProject"  # ← change this
```

The same three variables appear in both files — edit both.

---

## Configuring a run

All simulation parameters live in **`config.py`**. Edit only this file;
everything else reads from it.

### Key parameters

```python
TEST_TYPE   = 'nakazima'    # 'nakazima' | 'marciniak' | 'pip'
SPECIMEN_WIDTH = 50         # mm — selects geometry W50 (one run at a time)
BLANK_THICKNESS = 1.5       # mm
MATERIAL_ORIENTATION_ANGLE = 0.0   # degrees from rolling direction
MESH_REFINEMENT_FACTOR = 1  # 1 = base mesh; 2 = 2× finer in dome zone; etc.
```

`MESH_REFINEMENT_FACTOR` scales element size inside the dome zone. Factor 2
gives 4× more elements in the dome (quadratic refinement). Refined jobs get
an `_mr{N}` suffix in their name, e.g. `Nakazima_W50_t2p0_ang0_mr2`.

For a **PiP** run you also need:

```python
PIP_PUNCH2_ID = 'PUNCH_21'  # inner punch variant — see PiP_Punches/ directory
```

### Available specimen widths

| Width | Stress state |
|-------|-------------|
| W20   | Uniaxial tension |
| W50   | — |
| W80   | Plane strain |
| W90, W100, W120 | — |
| W200  | Equi-biaxial |

### Geometry files

Geometry `.cae` files must be present in the correct subdirectory:

| Test type | Directory |
|-----------|-----------|
| `nakazima` / `marciniak` | `Naka_Marciniak_Geometries/` |
| `pip` | `PiP_Geometries/` + `PiP_Punches/<PIP_PUNCH2_ID>.cae` |

---

## Running the pipeline

### Single specimen — `deploy.sh`

Builds one model, submits the solver job, and automatically submits a
dependent plot job that runs after the solver finishes.

```bash
./deploy.sh
```

What it does:
1. Reads `config.py` for all parameters
2. Pushes all source files to Euler via `scp`
3. Runs `abaqus cae noGUI=build_model.py` on the login node → produces `.inp`
4. Submits solver job via `sbatch run_cluster.sh` → returns `JOB_ID`
5. Submits plot job via `sbatch run_flc.sh --dependency=afterok:JOB_ID`

### Full FLC sweep — `deploy_all.sh`

Pushes all source files to Euler, then launches `submit_all.sh` in a
**tmux session** (`deploy`) on the login node. The local terminal is freed
immediately — all building and job submission happens remotely.

```bash
# Use defaults from config.py
./deploy_all.sh

# Override test type, thickness, orientation
./deploy_all.sh nakazima 1.5 0

# Override + specific widths only
./deploy_all.sh nakazima 1.5 0 50 80 200
```

Arguments (all optional, positional):

| Position | Parameter | Default |
|----------|-----------|---------|
| 1 | test type | `config.TEST_TYPE` |
| 2 | thickness (mm) | `config.BLANK_THICKNESS` |
| 3 | orientation (deg) | `config.MATERIAL_ORIENTATION_ANGLE` |
| 4+ | widths | 20 50 80 90 100 120 200 |

`submit_all.sh` runs on Euler and:
1. Loads the `abaqus/2023` module
2. For each width: builds the model with `abaqus cae noGUI=build_model.py`, submits the solver job via `sbatch`
3. After all solver jobs are queued: submits the FLC aggregation job with `afterok` dependency on all solver IDs

All output is captured to `$EULER_DIR/submit_all.log`.

---

## Rendering EQPS animations — `deploy_movie.sh`

Generates a `.webm` animation of the EQPS (equivalent plastic strain) field
from a completed ODB. Can be run any time after the solver finishes.

```bash
# Syntax
./deploy_movie.sh <JOB_NAME>

# Example
./deploy_movie.sh Nakazima_W50_t2p0_ang0_mr2
```

What it does:
1. Pushes `postproc_movie.py` and `run_movie.sh` to Euler
2. Submits a SLURM job that runs Abaqus CAE (headless via `xvfb-run`) to render the animation
3. Copies the resulting `.webm` to `$EULER_DIR/<JOB_NAME>/`

Download once done:

```bash
scp acruzfaria@euler.ethz.ch:/cluster/home/acruzfaria/AbaqusProject/<JOB_NAME>/<JOB_NAME>_movie.webm .
```

The animation uses a fixed EQPS colour scale (max = fracture strain of deleted
elements) and a stable camera calibrated to the specimen footprint, so the view
does not drift as the punch descends.

---

## Monitoring jobs

```bash
# Check your queue
ssh YOUR_ETH_USERNAME@euler.ethz.ch 'squeue --me'

# Watch specific jobs (IDs printed by deploy script)
ssh YOUR_ETH_USERNAME@euler.ethz.ch 'squeue -j 12345,12346'

# Attach to the running deploy_all tmux session (live output)
ssh YOUR_ETH_USERNAME@euler.ethz.ch
tmux attach -t deploy

# Tail the submission log without keeping SSH open
ssh YOUR_ETH_USERNAME@euler.ethz.ch 'tail -f /cluster/home/$USER/AbaqusProject/submit_all.log'

# Tail a solver log (job must be running)
ssh YOUR_ETH_USERNAME@euler.ethz.ch 'tail -f /cluster/home/$USER/AbaqusProject/Nakazima_W50_t1p5_ang0_12345.out'
```

Typical wall times on 24 CPUs:

| Test | Width | Approximate time |
|------|-------|-----------------|
| Nakazima | W20–W80 | 1–4 h |
| Nakazima | W200 | 6–12 h |
| PiP | any | 4–16 h |

---

## Retrieving results

Results are copied automatically from scratch to home at the end of each
solver job (`run_cluster.sh` Step 5). Each run produces a subdirectory:

```
AbaqusProject/
  Nakazima_W50_t1p5_ang0/
    strain_path.csv
    forming_limits.csv
    energy_data.csv
    cov_data.csv
    punch_fd.csv
    Nakazima_W50_t1p5_ang0_movie.webm
    postproc_plots.pdf          ← generated by plot job
```

To pull results to your local machine use **`collect_results.sh`**, which
downloads all CSVs and (optionally) movies for a full width sweep, then
generates the FLC PDF locally:

```bash
# All defaults from config.py
./collect_results.sh

# Override parameters
./collect_results.sh nakazima 1.5 0

# Skip movie download
./collect_results.sh nakazima 1.5 0 --no-movies

# Specific widths only
./collect_results.sh nakazima 1.5 0 50 80 200
```

Or pull manually:

```bash
# Single run
scp -r YOUR_ETH_USERNAME@euler.ethz.ch:/cluster/home/YOUR_ETH_USERNAME/AbaqusProject/Nakazima_W50_t1p5_ang0 .

# FLC PDF (full sweep)
scp YOUR_ETH_USERNAME@euler.ethz.ch:/cluster/home/YOUR_ETH_USERNAME/AbaqusProject/FLC_nakazima_t1p5_ang0/FLC_nakazima.pdf .
```

The ODB files stay in `/cluster/scratch/$USER/<job_name>/` and are
auto-deleted by Euler after 2 weeks. Retrieve them manually if needed before
that window closes.

---

## Re-running post-processing only

If you want to re-plot without re-solving (e.g. after updating `plot_results.py`):

```bash
# Interactive single specimen (login node, immediate)
./postproc_single.sh 50 nakazima 1.5 0
#                    ^W ^type    ^t  ^angle

# Batch re-post-process via SLURM queue
./submit_postproc.sh --widths "50 80 200" --test_type nakazima --thickness 1.5 --orientation 0
```

`submit_postproc.sh` submits a postproc job followed by a dependent plot job,
without re-running the solver.

---

## Project structure

```
AbaqusProject/
├── config.py                  ← all parameters — edit this
├── build_model.py             ← Abaqus CAE script, builds .inp
├── VUMAT_explicit.f           ← user material subroutine
│
├── modules/                   ← Python modules imported by build_model.py
│   ├── parts.py               ← specimen + tooling geometry
│   ├── assembly.py            ← part instances + constraints
│   ├── material.py            ← VUMAT material definition
│   ├── contact.py             ← contact pairs
│   ├── boundary.py            ← BCs and loads
│   ├── step.py                ← Abaqus/Explicit step settings
│   └── job.py                 ← output requests (INP injection), job export
│
├── postproc.py                ← Abaqus Python: extracts CSVs from ODB
├── postproc_movie.py          ← Abaqus Python: renders EQPS animation
├── plot_results.py            ← Python+matplotlib: per-specimen PDF
├── plot_flc.py                ← Python+matplotlib: FLC aggregation PDF
│
├── deploy.sh                  ← single-specimen deploy (push + build + submit)
├── deploy_all.sh              ← full-width FLC sweep deploy (launches submit_all.sh via tmux)
├── deploy_movie.sh            ← push postproc_movie.py and submit animation job
├── submit_all.sh              ← runs ON Euler: builds models + submits all solver jobs
├── submit_one.sh              ← runs ON Euler: build + submit for a single specimen
├── run_cluster.sh             ← SLURM: solver + postproc + movie (run on cluster)
├── run_flc.sh                 ← SLURM: plot jobs (afterok solver)
├── run_movie.sh               ← SLURM: EQPS animation (submitted by deploy_movie.sh)
├── run_postproc.sh            ← SLURM: re-run postproc on existing ODBs
├── run_plot.sh                ← SLURM: re-run plots from existing CSVs
├── submit_postproc.sh         ← re-run post-processing without re-solving
├── postproc_single.sh         ← interactive postproc on login node
├── collect_results.sh         ← download results from Euler + plot FLC locally
│
├── Naka_Marciniak_Geometries/ ← specimen .cae files for Nakazima/Marciniak
├── PiP_Geometries/            ← specimen .cae files for PiP
├── PiP_Punches/               ← inner punch .cae files (PUNCH_XX.cae)
│
└── Unused/                    ← archived scripts no longer in the active pipeline
    ├── deploy_mass_scaling.sh ← mass-scaling sensitivity sweep (superseded)
    ├── plot_mass_scaling.py   ← mass-scaling comparison PDF (superseded)
    └── run_cluster_mpi.sh     ← MPI solver variant (replaced by threads)
```

---

## Output files reference

| File | Description |
|------|-------------|
| `strain_path.csv` | Time history at critical dome element: `time_s`, `eps1_major`, `eps2_minor`, `EQPS`, `D`, `fracture_type`, `d_dome_max` |
| `forming_limits.csv` | Limit strains per method: `method` (`fracture`/`volk_hora`/`sdv6`/`min_stoughton`/`pham_sigvant`/`din_iso`), `eps1_major`, `eps2_minor`, `EQPS`, `D`, `time_s` |
| `energy_data.csv` | Energy balance per frame: `step_name`, `total_time_s`, `ALLKE`, `ALLIE`, `is_step_boundary` |
| `punch_fd.csv` | Punch force–displacement history: `total_time_s`, `U3_mm`, `RF3_N` |
| `cov_data.csv` | Pham-Sigvant CoV time history: `time_s`, `cov`, `eps1_dot_mean` — used for necking onset detection |
| `postproc_plots.pdf` | Per-specimen diagnostic plots (8 pages) |
| `FLC_<type>.pdf` | Aggregated FLC across all widths |
| `<job>_movie.webm` | EQPS field animation (rendered by `deploy_movie.sh` / `run_cluster.sh`) |

### Diagnostic plot pages (`postproc_plots.pdf`)

| Page | Content |
|------|---------|
| 1 | Strain path in FLD space (ε₁ vs ε₂) with fracture/necking limit markers |
| 2 | Volk-Hora: thinning rate ε̇_thin + stable/unstable linear fits (extended to intersection) |
| 3 | Merklein: smoothed ε̈₁ with maximum = necking onset |
| 4 | Strain ratio β = ε₂/ε₁ — instantaneous (red dashed) and cumulative (blue) |
| 5 | Punch force–displacement with necking/fracture markers *(if punch_fd.csv present)* |
| 6 | EQPS history with vertical lines at necking/fracture |
| 7 | Dome-zone max damage vs time *(only if SDV6 data present)* |
| 8 | ALLKE/ALLIE energy ratio — quasi-static validity check *(if energy_data.csv present)* |

### FLC PDF pages

| Page | Content |
|------|---------|
| 1 | FLC — fracture limit strains |
| 2 | FLC — Volk-Hora necking strains |
| 3 | FLC — SDV6 damage necking strains |
| 4 | All methods overlaid with strain path backgrounds |
| 5–6 | PEPS FLC — EQPS at necking vs β = ε₂/ε₁ (path-independence check) |
