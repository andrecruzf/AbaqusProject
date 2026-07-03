# FEM_GUI

CustomTkinter desktop application for the Abaqus/FEM workflow.

## Run

From the repository root:

```bash
python3 FEM_GUI/main.py
```

Install dependencies if needed:

```bash
python3 -m pip install -r FEM_GUI/requirements.txt
```

## Current Scope

- Modern CustomTkinter shell with dark theme by default.
- Central session, persistent JSON settings, task runner, and compact task status bar.
- Euler connection page using the standard system `ssh` command, with optional key-only verification.
- Submit Job page with job preview, mesh estimates, resource suggestions, saved defaults, and async `deploy.sh`.
- Submit Job page validation, help tooltips, grouped BM mesh controls, memory slider, PiP punch preview, mesh-zone diagram, and mesh-cell metric card.
- Job Queue manager with async refresh, filtering, searching, sorting, `.sta` progress enrichment, per-job progress bars, and detail view.
- Results browser with async scan/sync, job explorer, media thumbnails, summary tables, desktop plot workspaces, V&H connected-zone analysis, and plot export/copy actions.
- Plotting logic split under `logic/plotting/` and displayed through `gui/plot_viewer.py`.
- FLC, sensitivity, convergence, force-displacement, strain, and material-response plots use Matplotlib conventions adapted from `GUI_FLD-evaluation`.
- Live theme switching, global shortcuts, and toast notifications.
- AI assistant page with session-scoped conversation history and no persisted API key.

The application stores local settings under:

```text
FEM_GUI/.state/settings.json
```

No passwords are stored.
