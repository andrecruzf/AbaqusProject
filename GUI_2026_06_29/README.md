# FLD Evaluation GUI (2026-06-29)

Copy of `GUI_FLD-evaluation` with the **Min-Stoughton curvature criterion
(Min et al. 2017)** wired directly into the GUI. The original GUI is left
untouched.

## Run

```bash
python3 GUI_2026_06_29/main.py
```

## Forming-limit methods

The "Select method" dropdown offers:

- `ISO12004`  – DIN EN ISO 12004-2 (section/parabola fit), marker `x`
- `VolkHora`  – Völk & Hora time-dependent criterion, marker `o`
- `MinStoughton` – surface-curvature criterion (Min et al. 2017), marker `D`
- `both` – ISO + Völk & Hora
- `all`  – all three

## Min-Stoughton: launching the post-processing from the GUI

Unlike DIN and Völk & Hora (whose limit strains are read from the
pre-computed `all_results_<mat>.txt` summary), the Min-Stoughton FLC is
produced on demand by the **`Min-Stroughton_post_pro`** pipeline, launched
straight from this GUI:

1. Select a material folder and at least one configuration.
2. Press **Run Min-Stoughton**.
3. Confirm/adjust the method parameters (paper defaults are pre-filled):
   `W_X`, `W_Y`, `SAC`, `n`, `alpha` (Δ = α·SAC), `M` (reference frame as a
   fraction of the crack frame F).
4. The pipeline runs on every usable experiment of the selected
   configurations. For each it locates the specimen folder
   (`<material>/<Configuration>/<Geometry>/<Experiment name>`), reads its
   `Results/__mesh/*.vtk`, `Results/CrackData.txt` and `project.xml`/
   `sample_ID.xml`, detects the onset of localized necking from the surface
   curvature evolution, and extracts the limit strains `eps1_L`/`eps2_L`.

### Non-destructive: your data files are never modified

`all_results_<mat>.txt` (and everything else in your data tree) is treated as
**read-only** — it is read only to enumerate which experiments to process.
All Min-Stoughton output is written inside this GUI copy, under:

- `ms_output/min_stoughton_<mat>.csv` – per-experiment results: limit strains,
  nearest/local strains, onset frame, failure reason, and the parameters used.

When you press **Show FLD** (or **Export FLD Data**) with `MinStoughton`/`all`
selected, the curvature limit strains are merged from this file **in memory**
and plotted as diamonds. Nothing is written back to the material folder.

`ms_output/` is git-ignored, so beta results never get committed.

The pipeline itself lives in
`Post_processing_Nakazima_tests/Min-Stroughton_post_pro/` and is added to
`sys.path` at run time. Override its location with the `MIN_STOUGHTON_PKG`
environment variable if the GUI folder is moved away from the repo.

Specimen thickness, punch radius and width are derived from the material
campaign code and the experiment name as a robustness net, so unknown codes in
the VIC XML do not abort the run.
