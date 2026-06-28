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
| OpenSSH | any | `ssh`, `rsync` |
| rsync | any | used by all deploy scripts instead of `scp` — skips unchanged files |
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

Password-based login is slow and will break non-interactive `rsync`/`ssh` in
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

**Disk quota:** The Euler home directory has a ~43 GB soft quota (47 GB hard
limit). The pipeline automatically deletes `.inp` files after each solver job
is submitted (they are regenerable and each file is 150–190 MB). Monitor
usage with `quota -s` when logged in.

---

## Local repository setup

### 1. Clone / copy the repository

```bash
git clone <repo-url> AbaqusProject
cd AbaqusProject
```

Or copy the project folder to your machine if you received it as an archive.

### 2. Edit deploy variables

Open `deploy.sh` and update the three variables at the top:

```bash
EULER_USER="your_eth_username"          # ← change this
EULER_HOST="euler.ethz.ch"              # leave as-is
EULER_DIR="/cluster/home/your_eth_username/AbaqusProject"  # ← change this
```

Use the same values in any local helper script that connects to Euler.

---

## Configuring a run

All simulation parameters live in **`config.py`**. Edit only this file;
everything else reads from it. Every parameter can also be overridden via an
environment variable of the same name, which is how the deploy scripts pass
per-run values.

### Key parameters

```python
TEST_TYPE   = 'nakazima'    # 'nakazima' | 'marciniak' | 'pip'
SPECIMEN_WIDTH = 50         # mm — selects geometry W50 (one run at a time)
BLANK_THICKNESS = 1.5       # mm
MATERIAL_ORIENTATION_ANGLE = 0.0   # degrees from rolling direction

MESH_REFINEMENT_FACTOR = 2.0  # 1.0 = baseline; 2.0 = 2× finer (recommended)
MESH_BACKEND = 'bm'           # 'bm' = Nakazima_BM.py builder; 'current' = CAE import
MESH_SEED_MODE = 'zones'      # 'zones' | 'imported' | 'outer_reseed' | ...

MASS_SCALING_DT = 1e-5        # s — target stable dt; lower = more accurate but slower
PUNCH_SPEED = 5.0             # mm/s
```

`MESH_REFINEMENT_FACTOR` scales element size in the dome zone (quadratic
refinement: factor 2 gives ~4× more elements). Refined jobs get an `_mr{N}`
suffix, e.g. `Naka100_W50_t2p0_ang0_ms1e5_mr2`.

`MESH_BACKEND = 'bm'` uses `Nakazima_BM.py` to build the specimen mesh
parametrically instead of importing a pre-meshed `.cae` geometry file.

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
# Use all defaults from config.py
./deploy.sh

# Override individual parameters (all positional, all optional)
./deploy.sh nakazima 1.5 0 90 none 2 1e-5 5.0
#           type     t  ang W  pip mr ms    ps
```

Positional arguments (all optional — fall back to `config.py` defaults):

| Position | Parameter | Default |
|----------|-----------|---------|
| 1 | test type | `config.TEST_TYPE` |
| 2 | thickness (mm) | `config.BLANK_THICKNESS` |
| 3 | orientation (deg) | `config.MATERIAL_ORIENTATION_ANGLE` |
| 4 | specimen width (mm) | `config.SPECIMEN_WIDTH` |
| 5 | PIP punch2 ID (`none` if unused) | `config.PIP_PUNCH2_ID` |
| 6 | mesh refinement factor | `config.MESH_REFINEMENT_FACTOR` |
| 7 | mass scaling dt (s) | `config.MASS_SCALING_DT` |
| 8 | punch speed (mm/s) | `config.PUNCH_SPEED` |
| 9 | punch radius (mm) | `config.PUNCH_RADIUS` |
| 10 | output subdir (optional grouping) | `""` |

What it does:
1. Reads `config.py` for all parameters
2. Pushes all source files to Euler via `rsync --checksum` (only changed files transferred)
3. Runs `abaqus cae noGUI=build_model.py` on the login node → produces `.inp`
4. Renders mesh screenshots via `screenshot_mesh.py` → `<JOB>_mesh.png` / `<JOB>_mesh_top.png`
5. Submits solver job via `sbatch run_cluster.sh` → returns `JOB_ID`
6. Submits plot job via `sbatch run_plots.sh flc --dependency=afterok:JOB_ID`
7. Deletes the `.inp` file (150–190 MB, regenerable) after submission

## Rendering EQPS animations — `deploy_movie.sh`

Generates a `.webm` animation of the EQPS (equivalent plastic strain) field
from a completed ODB. Can be run any time after the solver finishes.

```bash
# Syntax
./deploy_movie.sh <JOB_NAME>

# Example
./deploy_movie.sh Naka100_W50_t2p0_ang0_ms1e5_mr2
```

What it does:
1. Pushes `postproc_movie.py` and `run_movie.sh` to Euler
2. Submits a SLURM job that runs Abaqus CAE (headless via `xvfb-run`) to render two animations
3. Copies the resulting `.webm` files to `$EULER_DIR/<JOB_NAME>/`

Download once done:

```bash
# Full isometric view
scp acruzfaria@euler.ethz.ch:/cluster/home/acruzfaria/AbaqusProject/<JOB_NAME>/<JOB_NAME>_movie.webm .
# Y=0 half-model cut view (punch visible through translucent tooling)
scp acruzfaria@euler.ethz.ch:/cluster/home/acruzfaria/AbaqusProject/<JOB_NAME>/<JOB_NAME>_cut.webm .
```

Two animations are produced:
- **`_movie.webm`** — isometric full view with translucent tooling and EQPS contours on the specimen
- **`_cut.webm`** — front view of the Y=0 symmetry half-model; punch and blank holder shown translucent so the interior strain field is visible

---

## Monitoring jobs

### Streamlit app — `app.py`

The primary monitoring interface. Run locally:

```bash
streamlit run app.py
```

| Tab | Contents |
|-----|----------|
| **Submit Job** | Build and submit single or full-width jobs from a GUI form; 3-D punch preview for PiP runs |
| **Job Status** | Live SLURM queue table with colour-coded states; progress bars (% complete + ETA) for all running Abaqus solver jobs, read from the `.sta` file in scratch |
| **Results** | Browse synced results: **Single Job** (synced full/cut video pair + 4 interactive Plotly tabs); **Full FLC** (interactive FLC chart + per-width job inspector); **Compare FLC** (multi-set overlay with export) |
| **AI Assistant** | Claude-powered assistant for model and results questions |

All charts in the Results tab are rendered as interactive Plotly figures. Progress is
fetched silently every 60 s; click **🔄** to force-refresh immediately.

### Command-line

```bash
# Check your queue
ssh YOUR_ETH_USERNAME@euler.ethz.ch 'squeue --me'

# Check progress from a running .sta file (Abaqus status)
ssh YOUR_ETH_USERNAME@euler.ethz.ch \
  'tail -1 /cluster/scratch/$USER/<JOB_NAME>/<JOB_NAME>.sta'
```

Typical wall times on 24 CPUs (`MS=1e-5, MR=2, PS=5 mm/s`):

| Test | Width | Approximate time |
|------|-------|-----------------|
| Nakazima | W20–W80 | 4–8 h |
| Nakazima | W100–W120 | 6–10 h |
| Nakazima | W200 | 8–14 h |
| PiP | any | 4–16 h |

With `MS=1e-6` (10× more accurate, 10× more increments) multiply by ~10.
With `MR=4` (4× finer mesh) multiply by ~4 additionally.

---

## Retrieving results

Results are copied automatically from scratch to home at the end of each
solver job (`run_cluster.sh` Step 5). Each run produces a subdirectory:

```
AbaqusProject/
  Naka100_W50_t1p5_ang0_ms1e5_mr2/
    strain_path.csv
    forming_limits.csv
    energy_data.csv
    cov_data.csv
    punch_fd.csv
    Naka100_W50_t1p5_ang0_ms1e5_mr2_mesh.png     ← ISO mesh view (generated at build time)
    Naka100_W50_t1p5_ang0_ms1e5_mr2_mesh_top.png ← face-on mesh view
    Naka100_W50_t1p5_ang0_ms1e5_mr2_movie.webm
    postproc_plots.pdf          ← generated by plot job
```

To pull results to your local machine use **`collect_results.sh`**, which
downloads all CSVs and (optionally) movies for a full width sweep:

```bash
# All defaults from config.py
./collect_results.sh

# Override parameters
./collect_results.sh nakazima 1.5 0

# Skip movie download (faster)
./collect_results.sh nakazima 1.5 0 --no-movies

# Specific widths only
./collect_results.sh nakazima 1.5 0 50 80 200
```

Or pull manually with rsync (faster than scp for multiple files):

```bash
# Single run directory
rsync -az YOUR_ETH_USERNAME@euler.ethz.ch:/cluster/home/YOUR_ETH_USERNAME/AbaqusProject/Naka100_W50_t1p5_ang0_ms1e5_mr2/ ./Naka100_W50_t1p5_ang0_ms1e5_mr2/

# FLC output directory (all widths)
rsync -az YOUR_ETH_USERNAME@euler.ethz.ch:/cluster/home/YOUR_ETH_USERNAME/AbaqusProject/FLC_nakazima_t1p5_ang0/ ./FLC_output/FLC_nakazima_t1p5_ang0/
```

The ODB files stay in `/cluster/scratch/$USER/<job_name>/` and are
auto-deleted by Euler after 2 weeks. Retrieve them manually if needed before
that window closes.

**Note on disk quota:** The Euler home has a ~43 GB soft quota. The pipeline
auto-deletes `.inp` files after submission, but large `strain_dome.csv` files
(100 MB – 2 GB each) can accumulate. These can be deleted after you have
retrieved the key post-processing outputs such as `forming_limits.csv`.

---

## Re-running post-processing only

If you want to re-plot without re-solving (e.g. after updating `plot_results.py`):

```bash
# Single ODB via SLURM queue
sbatch run_postproc_odb.sh /cluster/scratch/<user>/<JOB_NAME>/<JOB_NAME>.odb

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
├── build_mesh_only.py         ← builds mesh only (no solver step), for mesh checks
├── Nakazima_BM.py             ← parametric specimen mesh builder (MESH_BACKEND=bm)
├── VUMAT_explicit.f           ← user material subroutine
│
├── modules/                   ← Python modules imported by build_model.py
│   ├── parts.py               ← specimen + tooling geometry and meshing
│   ├── assembly.py            ← part instances + constraints
│   ├── material.py            ← VUMAT material definition
│   ├── contact.py             ← contact pairs
│   ├── boundary.py            ← BCs and loads
│   ├── step.py                ← Abaqus/Explicit step settings
│   └── job.py                 ← output requests (INP injection), job export
│
├── postproc.py                ← Abaqus Python: extracts CSVs from ODB
├── postproc_movie.py          ← Abaqus Python: renders EQPS animation
├── screenshot_mesh.py         ← Abaqus Python: renders mesh PNGs after build
├── plot_results.py            ← Python+matplotlib: per-specimen PDF
├── plot_flc.py                ← Python+matplotlib: FLC aggregation PDF
│
├── app.py                     ← Streamlit pipeline manager (submit / monitor / results / AI)
│
├── deploy.sh                  ← single-specimen deploy (push + build + submit)
├── deploy_movie.sh            ← EQPS animation render deploy
│
├── submit_one.sh              ← runs ON Euler: build + submit for a single specimen
│
├── run_cluster.sh             ← SLURM: solver + postproc + movie
├── run_plots.sh               ← SLURM: plotting — flc | results
├── run_postproc.sh            ← SLURM: postproc-only re-run
├── run_movie.sh               ← SLURM: movie render job
│
├── collect_results.sh         ← local: rsync CSVs + movies from Euler
├── submit_postproc.sh         ← local: submit postproc-only SLURM job
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
| `cov_data.csv` | Pham-Sigvant CoV time history: `time_s`, `cov`, `eps1_dot_mean` |
| `postproc_plots.pdf` | Per-specimen diagnostic plots (8 pages) |
| `FLC_<type>.pdf` | Aggregated FLC across all widths |
| `<job>_mesh.png` | ISO view of the specimen mesh — generated at build time |
| `<job>_mesh_top.png` | Face-on (+Z) view of the specimen mesh |
| `<job>_movie.webm` | EQPS field animation — isometric full view with translucent tooling |
| `<job>_cut.webm` | EQPS animation — front view of Y=0 half-model; tooling shown translucent |

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
