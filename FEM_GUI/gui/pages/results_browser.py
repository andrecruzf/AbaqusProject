from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

try:
    import cv2
except Exception:  # pragma: no cover - optional runtime dependency
    cv2 = None

from app.constants import DEFAULT_EULER_USER, EULER_HOST
from gui.plot_viewer import PlotViewer
from gui.widgets import ToolTip
from logic.plotting import flc, force_displacement, material_response, strain
from logic.plotting import vh as vh_plotting
from logic.results_scan import CsvCache, ScanResult, dedupe_jobs, jobs_newest_first, scan_results
from services.sync import SyncService

from .base import BasePage


class ResultsBrowserPage(BasePage):
    title = "Results"

    PANEL_FORCE = "Force-Disp."
    PANEL_ENERGY = "Energy"
    PANEL_STRAIN = "Strain Path"
    PANEL_VH = "V&H Rate"
    PANEL_TRIAX = "Triaxiality"
    PANEL_FLD = "FLD"
    PLOT_PANELS = [PANEL_FORCE, PANEL_ENERGY, PANEL_STRAIN, PANEL_VH, PANEL_TRIAX, PANEL_FLD]
    PLOT_TITLES = {
        PANEL_FORCE: "Force-displacement",
        PANEL_ENERGY: "Energy history",
        PANEL_STRAIN: "Strain path",
        PANEL_VH: "V&H thinning rate",
        PANEL_TRIAX: "Triaxiality",
        PANEL_FLD: "FLD",
    }

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.cache = CsvCache()
        self.scan = ScanResult()
        self.jobs: dict[str, Path] = {}
        self.selected_job: str | None = None
        self.results_dir_var = ctk.StringVar(value=self.session.settings.results_dir)
        self.sync_status_var = ctk.StringVar(value="")
        self.fld_paths_var = ctk.BooleanVar(value=True)
        self.video_frame_var = ctk.DoubleVar(value=0)
        self.job_buttons: dict[str, ctk.CTkButton] = {}
        self.plot_viewers: dict[str, PlotViewer] = {}
        self.plot_buttons: dict[str, ctk.CTkButton] = {}
        self.media_images: list[ctk.CTkImage] = []
        self.video_frame_images: list[ctk.CTkImage] = []
        self.video_info: dict[Path, tuple[int, float]] = {}
        self.current_video_pair: tuple[Path | None, Path | None] | None = None
        self.current_video_max_frame = 0
        self._video_after_id = None
        self._video_play_after_id = None
        self._video_playing = False
        self._sync_running = False
        self._plot_requests: dict[str, int] = {}
        self._plot_batch = 0
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self._build_controls()
        self._build_viewer()

    def _build_controls(self) -> None:
        controls = ctk.CTkFrame(self, **self.theme.frame_kwargs())
        controls.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        controls.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(controls, text="Results dir").grid(row=0, column=0, sticky="w", padx=(12, 4), pady=(8, 2))
        ctk.CTkEntry(controls, textvariable=self.results_dir_var, width=340).grid(
            row=0, column=1, sticky="w", padx=4, pady=(8, 2)
        )
        ctk.CTkButton(controls, text="Browse", width=70, command=self.browse_dir, **self.theme.button_kwargs()).grid(
            row=0, column=2, sticky="w", padx=4, pady=(8, 2)
        )
        ctk.CTkButton(
            controls, text="Sync results", width=100, command=self.sync_results, **self.theme.button_kwargs(primary=True)
        ).grid(row=0, column=3, padx=4, pady=(8, 2))
        self.sync_status_label = ctk.CTkLabel(
            controls, textvariable=self.sync_status_var, width=60, text_color=self.theme.colors.text_muted
        )
        self.sync_status_label.grid(row=0, column=4, sticky="w", padx=(0, 12), pady=(8, 2))
        self.job_strip = ctk.CTkScrollableFrame(
            controls, orientation="horizontal", height=34, fg_color=self.theme.colors.panel_alt
        )
        self.job_strip.grid(row=1, column=0, columnspan=5, sticky="ew", padx=10, pady=(2, 8))
        # CTk only maps Shift+wheel to horizontal scroll; make the plain wheel roll the strip too.
        canvas = getattr(self.job_strip, "_parent_canvas", None)
        if canvas is not None:
            canvas.bind("<MouseWheel>", self._on_strip_wheel, add="+")

    def _on_strip_wheel(self, event) -> None:
        canvas = getattr(self.job_strip, "_parent_canvas", None)
        if canvas is not None and canvas.xview() != (0.0, 1.0):
            canvas.xview("scroll", -event.delta, "units")

    def _scroll_strip_to_selection(self) -> None:
        button = self.job_buttons.get(self.selected_job or "")
        canvas = getattr(self.job_strip, "_parent_canvas", None)
        if button is None or canvas is None:
            return
        self.job_strip.update_idletasks()
        bbox = canvas.bbox("all")
        if not bbox or bbox[2] <= 0:
            return
        fraction = max(0.0, (button.winfo_x() - 40) / bbox[2])
        canvas.xview_moveto(fraction)

    def _build_viewer(self) -> None:
        # One continuous vertically scrolling page, mirroring the Streamlit
        # results view: movies, then mesh pictures, then the plot sections.
        self.page = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.page.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.page.grid_columnconfigure(0, weight=1)
        self._build_movies_section(self.page)
        self._build_mesh_section(self.page)
        self._build_plots_section(self.page)

    def _build_movies_section(self, master) -> None:
        movies = ctk.CTkFrame(master, **self.theme.frame_kwargs())
        movies.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        movies.grid_columnconfigure(0, weight=1)
        movies.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(movies, text="Movies", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 2)
        )
        self.iso_panel = self._movie_panel(movies, "ISO view", column=0)
        self.section_panel = self._movie_panel(movies, "Section view", column=1)

        slider_row = ctk.CTkFrame(movies, fg_color="transparent")
        slider_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 10))
        slider_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(slider_row, text="Frame", text_color=self.theme.colors.text_muted).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.video_slider = ctk.CTkSlider(
            slider_row,
            from_=0,
            to=1,
            number_of_steps=1,
            variable=self.video_frame_var,
            command=self._on_video_frame_change,
            state="disabled",
        )
        self.video_slider.grid(row=0, column=1, sticky="ew")
        self.video_frame_label = ctk.CTkLabel(
            slider_row, text="No movie loaded", text_color=self.theme.colors.text_muted
        )
        self.video_frame_label.grid(row=0, column=2, sticky="e", padx=(10, 0))

        buttons_row = ctk.CTkFrame(movies, fg_color="transparent")
        buttons_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
        buttons_row.grid_columnconfigure(0, weight=1)
        buttons_row.grid_columnconfigure(6, weight=1)
        self.video_buttons = {
            "start": ctk.CTkButton(
                buttons_row,
                text="⏮",
                width=44,
                state="disabled",
                command=lambda: self._seek_video_frame(0, pause=True),
                **self.theme.button_kwargs(),
            ),
            "prev": ctk.CTkButton(
                buttons_row,
                text="⏴",
                width=44,
                state="disabled",
                command=lambda: self._step_video_frame(-1),
                **self.theme.button_kwargs(),
            ),
            "play": ctk.CTkButton(
                buttons_row,
                text="▶",
                width=54,
                state="disabled",
                command=self._toggle_video_playback,
                **self.theme.button_kwargs(primary=True),
            ),
            "next": ctk.CTkButton(
                buttons_row,
                text="⏵",
                width=44,
                state="disabled",
                command=lambda: self._step_video_frame(1),
                **self.theme.button_kwargs(),
            ),
            "end": ctk.CTkButton(
                buttons_row,
                text="⏭",
                width=44,
                state="disabled",
                command=lambda: self._seek_video_frame(self.current_video_max_frame, pause=True),
                **self.theme.button_kwargs(),
            ),
        }
        tips = {
            "start": "Go to start",
            "prev": "Frame back",
            "play": "Play or pause",
            "next": "Frame forward",
            "end": "Go to end",
        }
        for column, key in enumerate(("start", "prev", "play", "next", "end"), start=1):
            button = self.video_buttons[key]
            button.grid(row=0, column=column, padx=4)
            ToolTip(button, tips[key])

    def _movie_panel(self, master: ctk.CTkFrame, title: str, column: int) -> dict[str, ctk.CTkLabel]:
        panel = ctk.CTkFrame(master, **self.theme.frame_kwargs(alt=True))
        panel.grid(row=1, column=column, sticky="nsew", padx=(12 if column == 0 else 4, 4 if column == 0 else 12), pady=2)
        panel.grid_columnconfigure(0, weight=1)
        heading = ctk.CTkLabel(panel, text=title, text_color=self.theme.colors.text_muted)
        heading.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 0))
        image_label = ctk.CTkLabel(panel, text="No movie", text_color=self.theme.colors.text_muted, height=200)
        image_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(2, 8))
        image_label.bind("<Double-Button-1>", lambda _e, t=title: self._open_panel_video(t))
        return {"heading": heading, "image": image_label}

    def _build_mesh_section(self, master) -> None:
        mesh = ctk.CTkFrame(master, **self.theme.frame_kwargs())
        mesh.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        mesh.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(mesh, text="Mesh pictures", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 2)
        )
        self.mesh_grid = ctk.CTkFrame(mesh, fg_color="transparent")
        self.mesh_grid.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 10))
        for col in range(3):
            self.mesh_grid.grid_columnconfigure(col, weight=1)

    def _build_plots_section(self, master) -> None:
        plots = ctk.CTkFrame(master, **self.theme.frame_kwargs())
        plots.grid(row=2, column=0, sticky="ew")
        plots.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(plots, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(header, text="Post-processing plots", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self.render_all_button = ctk.CTkButton(
            header,
            text="Render all",
            width=90,
            state="disabled",
            command=self._render_all_plots,
            **self.theme.button_kwargs(),
        )
        self.render_all_button.pack(side="right")
        for row, panel in enumerate(self.PLOT_PANELS, start=1):
            self._build_plot_section(plots, row, panel)

    def _build_plot_section(self, master: ctk.CTkFrame, row: int, panel: str) -> None:
        section = ctk.CTkFrame(master, fg_color="transparent")
        section.grid(row=row, column=0, sticky="ew", padx=12, pady=(0, 12))
        section.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(section, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(
            header,
            text=self.PLOT_TITLES.get(panel, panel),
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        render_button = ctk.CTkButton(
            header,
            text="Render",
            width=72,
            state="disabled",
            command=lambda p=panel: self._render_plot_section(p),
            **self.theme.button_kwargs(),
        )
        render_button.pack(side="right")
        self.plot_buttons[panel] = render_button
        if panel == self.PANEL_FLD:
            ctk.CTkCheckBox(
                header,
                text="Show strain paths",
                variable=self.fld_paths_var,
                command=lambda: self._render_plot_section(self.PANEL_FLD),
            ).pack(side="right", padx=(0, 10))
        viewer = PlotViewer(section, self.theme)
        viewer.configure(height=430)
        viewer.grid(row=1, column=0, sticky="ew")
        viewer.grid_propagate(False)
        self.plot_viewers[panel] = viewer

    # ── Top-bar actions ───────────────────────────────────────────────────

    def on_show(self) -> None:
        if not self.jobs:
            self.scan_jobs()

    def browse_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.results_dir_var.get() or str(Path.home() / "Downloads"))
        if chosen:
            self.results_dir_var.set(chosen)
            self.scan_jobs()

    def scan_jobs(self) -> None:
        path = Path(self.results_dir_var.get()).expanduser()
        self.session.settings.results_dir = str(path)
        self.app.save_settings()

        def task(_ctx):
            return scan_results(path)

        def success(result: ScanResult):
            self.scan = result
            self.session.cached_results = {"flc_dirs": result.flc_dirs, "job_dirs": result.job_dirs}
            self.jobs = jobs_newest_first(dedupe_jobs(result.job_dirs))
            self._rebuild_job_strip()

        self.app.tasks.submit("Scan results", task, on_success=success)

    def _sync_identity(self) -> tuple[str, str]:
        username = self.session.connection.username or self.session.settings.remembered_username or DEFAULT_EULER_USER
        host = self.session.connection.host or self.session.settings.euler_host or EULER_HOST
        return username, host

    def sync_results(self) -> None:
        if self._sync_running:
            return
        target = Path(self.results_dir_var.get()).expanduser()
        username, host = self._sync_identity()
        if not username:
            self._set_sync_status("Failed", "error")
            return
        self._sync_running = True
        self._set_sync_status("Syncing", "warning")

        def task(_ctx):
            return SyncService().sync_remote_job(username, "", target, host, delete_stale=False)

        def success(result):
            self._sync_running = False
            if result.returncode == 0:
                self._set_sync_status("Done", "success")
                self.cache.clear()
                self.scan_jobs()
            else:
                self._set_sync_status("Failed", "error")
                self.session.logger.error((result.stderr or result.stdout or "rsync failed").strip()[-1500:])

        def failure(_exc):
            self._sync_running = False
            self._set_sync_status("Failed", "error")

        self.app.tasks.submit("Sync results", task, on_success=success, on_error=failure)

    def _set_sync_status(self, text: str, kind: str) -> None:
        colors = {
            "success": self.theme.colors.success,
            "warning": self.theme.colors.warning,
            "error": self.theme.colors.error,
        }
        self.sync_status_var.set(text)
        self.sync_status_label.configure(text_color=colors.get(kind, self.theme.colors.text_muted))

    # ── Job strip ─────────────────────────────────────────────────────────

    def _rebuild_job_strip(self) -> None:
        for child in self.job_strip.winfo_children():
            child.destroy()
        self.job_buttons.clear()
        if not self.jobs:
            ctk.CTkLabel(
                self.job_strip,
                text="No jobs found — sync results or pick another directory.",
                text_color=self.theme.colors.text_muted,
            ).pack(side="left", padx=10)
            self.selected_job = None
            self._show_job(None)
            return
        for name, path in self.jobs.items():
            button = ctk.CTkButton(
                self.job_strip,
                text=Path(path).name,
                height=24,
                width=0,
                command=lambda n=name: self.select_job(n),
                **self.theme.button_kwargs(),
            )
            button.pack(side="left", padx=3, pady=1)
            button.bind("<MouseWheel>", self._on_strip_wheel)
            ToolTip(button, name)
            self.job_buttons[name] = button
        if self.selected_job not in self.jobs:
            self.selected_job = next(iter(self.jobs))
        self.select_job(self.selected_job)
        self.after(80, self._scroll_strip_to_selection)

    def select_job(self, name: str) -> None:
        if name not in self.jobs:
            return
        self.selected_job = name
        for job_name, button in self.job_buttons.items():
            button.configure(**self.theme.button_kwargs(primary=(job_name == name)))
        self._show_job(self.jobs[name])

    # ── Main viewer ───────────────────────────────────────────────────────

    def _show_job(self, path: Path | None) -> None:
        self._populate_movies(path)
        self._populate_mesh_pictures(path)
        self._reset_plot_sections()
        canvas = getattr(self.page, "_parent_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(0.0)

    def _job_files(self, path: Path | None, suffixes: set[str]) -> list[Path]:
        if path is None:
            return []
        try:
            return sorted(
                item for item in Path(path).iterdir()
                if item.is_file() and item.suffix.lower() in suffixes
            )
        except OSError:
            return []

    def _populate_movies(self, path: Path | None) -> None:
        self._pause_video_playback()
        videos = [item for item in self._job_files(path, {".webm", ".mp4"}) if item.stat().st_size > 0]
        iso = next((item for item in videos if item.stem.endswith("_movie")), None)
        section = next((item for item in videos if item.stem.endswith("_cut")), None)
        self.current_video_pair = (iso, section) if (iso or section) else None
        self.video_frame_images.clear()
        if self.current_video_pair is None:
            self._disable_video_slider("No movies for this job")
            for panel in (self.iso_panel, self.section_panel):
                panel["image"].configure(image=None, text="No movie")
            return
        if cv2 is None:
            self._disable_video_slider("Install opencv-python for frame preview")
            for panel, item in ((self.iso_panel, iso), (self.section_panel, section)):
                text = f"{item.name}\n(double-click to open)" if item else "No file for this view"
                panel["image"].configure(image=None, text=text)
            return
        frame_counts = [count for count, _fps in (self._video_info(item) for item in (iso, section) if item) if count > 0]
        if not frame_counts:
            self._disable_video_slider("Movie files could not be decoded")
            for panel in (self.iso_panel, self.section_panel):
                panel["image"].configure(image=None, text="Could not decode movie")
            return
        self.current_video_max_frame = max(0, min(frame_counts) - 1)
        self.video_slider.configure(
            state="normal",
            from_=0,
            to=max(1, self.current_video_max_frame),
            number_of_steps=max(1, self.current_video_max_frame),
        )
        self._set_video_buttons_enabled(True)
        current = int(min(max(round(self.video_frame_var.get()), 0), self.current_video_max_frame))
        self.video_frame_var.set(current)
        self._render_video_frame(current)

    def _disable_video_slider(self, message: str) -> None:
        self._pause_video_playback()
        self.video_slider.configure(state="disabled", to=1, number_of_steps=1)
        self.video_frame_label.configure(text=message)
        self._set_video_buttons_enabled(False)

    def _set_video_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in getattr(self, "video_buttons", {}).values():
            button.configure(state=state)
        if not enabled:
            self.video_buttons["play"].configure(text="▶")

    def _on_video_frame_change(self, value: float | str) -> None:
        if not self.current_video_pair:
            return
        self._pause_video_playback()
        try:
            frame_index = int(round(float(value)))
        except (TypeError, ValueError):
            frame_index = 0
        if self._video_after_id:
            self.after_cancel(self._video_after_id)
        self._video_after_id = self.after(45, lambda: self._render_video_frame(frame_index))

    def _seek_video_frame(self, frame_index: int, pause: bool = True) -> None:
        if not self.current_video_pair:
            return
        if pause:
            self._pause_video_playback()
        frame_index = max(0, min(int(frame_index), self.current_video_max_frame))
        self.video_frame_var.set(frame_index)
        self._render_video_frame(frame_index)

    def _step_video_frame(self, delta: int) -> None:
        current = int(round(self.video_frame_var.get()))
        self._seek_video_frame(current + delta, pause=True)

    def _toggle_video_playback(self) -> None:
        if self._video_playing:
            self._pause_video_playback()
        else:
            self._start_video_playback()

    def _start_video_playback(self) -> None:
        if not self.current_video_pair or self.current_video_max_frame <= 0:
            return
        self._video_playing = True
        self.video_buttons["play"].configure(text="⏸")
        if self._video_play_after_id is None:
            self._advance_video_playback()

    def _pause_video_playback(self) -> None:
        self._video_playing = False
        if hasattr(self, "video_buttons"):
            self.video_buttons["play"].configure(text="▶")
        if self._video_play_after_id is not None:
            self.after_cancel(self._video_play_after_id)
            self._video_play_after_id = None

    def _advance_video_playback(self) -> None:
        self._video_play_after_id = None
        if not self._video_playing or not self.current_video_pair:
            return
        current = int(round(self.video_frame_var.get()))
        next_frame = current + 1
        if next_frame > self.current_video_max_frame:
            next_frame = 0
        self._seek_video_frame(next_frame, pause=False)
        fps_values = [
            fps
            for path in self.current_video_pair
            if path is not None
            for _count, fps in [self._video_info(path)]
            if fps > 0
        ]
        fps = fps_values[0] if fps_values else 15.0
        delay_ms = max(20, min(250, int(1000.0 / fps)))
        self._video_play_after_id = self.after(delay_ms, self._advance_video_playback)

    def _video_info(self, path: Path) -> tuple[int, float]:
        path = Path(path)
        cached = self.video_info.get(path)
        if cached is not None:
            return cached
        if cv2 is None:
            return (0, 0.0)
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            self.video_info[path] = (0, 0.0)
            return self.video_info[path]
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        cap.release()
        self.video_info[path] = (count, fps)
        return self.video_info[path]

    def _render_video_frame(self, frame_index: int) -> None:
        self._video_after_id = None
        pair = self.current_video_pair
        if not pair:
            return
        frame_index = max(0, min(frame_index, self.current_video_max_frame))
        fps_values = [fps for path in pair if path is not None for _c, fps in [self._video_info(path)] if fps > 0]
        fps = fps_values[0] if fps_values else 0.0
        time_text = f"{frame_index / fps:.2f} s" if fps > 0 else ""
        self.video_frame_label.configure(
            text=f"{frame_index} / {self.current_video_max_frame}" + (f" · {time_text}" if time_text else "")
        )
        self.video_frame_images.clear()
        for panel, path in ((self.iso_panel, pair[0]), (self.section_panel, pair[1])):
            if path is None:
                panel["image"].configure(image=None, text="No file for this view")
                continue
            image = self._read_video_frame(path, frame_index)
            if image is None:
                panel["image"].configure(image=None, text=f"Could not decode {path.name}")
                continue
            thumb = self._ctk_image(image, max_width=620, max_height=380)
            self.video_frame_images.append(thumb)
            panel["image"].configure(image=thumb, text="")

    def _read_video_frame(self, path: Path, frame_index: int) -> Image.Image | None:
        if cv2 is None:
            return None
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_index)))
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def _open_panel_video(self, title: str) -> None:
        if not self.current_video_pair:
            return
        path = self.current_video_pair[0] if title == "ISO view" else self.current_video_pair[1]
        if path is not None:
            self.app.open_path(path)

    def _populate_mesh_pictures(self, path: Path | None) -> None:
        for child in self.mesh_grid.winfo_children():
            child.destroy()
        self.media_images.clear()
        pngs = self._job_files(path, {".png"})
        pngs.sort(key=lambda item: "mesh" not in item.stem.lower())
        if not pngs:
            ctk.CTkLabel(self.mesh_grid, text="No pictures for this job", text_color=self.theme.colors.text_muted).grid(
                row=0, column=0, sticky="w", padx=4, pady=6
            )
            return
        for idx, png in enumerate(pngs):
            try:
                image = Image.open(png).copy()
            except Exception:
                continue
            thumb = self._ctk_image(image, max_width=420, max_height=300)
            self.media_images.append(thumb)
            cell = ctk.CTkFrame(self.mesh_grid, fg_color="transparent")
            cell.grid(row=idx // 3, column=idx % 3, sticky="n", padx=4, pady=4)
            label = ctk.CTkLabel(cell, image=thumb, text="")
            label.pack()
            label.bind("<Double-Button-1>", lambda _e, p=png: self.app.open_path(p))
            ctk.CTkLabel(
                cell,
                text=png.name,
                text_color=self.theme.colors.text_muted,
                wraplength=400,
                justify="center",
                font=ctk.CTkFont(size=10),
            ).pack()

    @staticmethod
    def _scaled_size(image: Image.Image, max_width: int, max_height: int) -> tuple[int, int]:
        ratio = min(max_width / max(1, image.width), max_height / max(1, image.height), 1.0)
        return (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))

    def _ctk_image(self, image: Image.Image, max_width: int, max_height: int) -> ctk.CTkImage:
        size = self._scaled_size(image, max_width, max_height)
        return ctk.CTkImage(dark_image=image, light_image=image, size=size)

    # ── Plot sections ─────────────────────────────────────────────────────

    def _campaign_jobs(self) -> dict[str, Path]:
        """Jobs sharing the selected job's parent directory, i.e. its FLC set."""
        if not self.selected_job:
            return {}
        parent = Path(self.jobs[self.selected_job]).parent
        siblings = {name: path for name, path in self.jobs.items() if Path(path).parent == parent}
        return siblings or {self.selected_job: self.jobs[self.selected_job]}

    def _render_all_plots(self) -> None:
        self._plot_batch += 1
        batch = self._plot_batch
        if not self.selected_job:
            self._reset_plot_sections()
            return
        if hasattr(self, "render_all_button"):
            self.render_all_button.configure(text="Rendering...", state="disabled")
        for panel in self.PLOT_PANELS:
            viewer = self.plot_viewers.get(panel)
            if viewer is not None:
                viewer.show_message("Queued...")
        self._render_plot_batch(list(self.PLOT_PANELS), batch)

    def _reset_plot_sections(self) -> None:
        self._plot_batch += 1
        has_job = self.selected_job is not None
        if hasattr(self, "render_all_button"):
            self.render_all_button.configure(text="Render all", state="normal" if has_job else "disabled")
        for panel in self.PLOT_PANELS:
            self._plot_requests[panel] = self._plot_requests.get(panel, 0) + 1
            button = self.plot_buttons.get(panel)
            if button is not None:
                button.configure(text="Render", state="normal" if has_job else "disabled")
            viewer = self.plot_viewers.get(panel)
            if viewer is not None:
                viewer.show_message("Click Render to load this plot" if has_job else "No job selected")

    def _render_plot_batch(self, panels: list[str], batch: int) -> None:
        if batch != self._plot_batch:
            return
        if not panels:
            if hasattr(self, "render_all_button"):
                self.render_all_button.configure(text="Render all", state="normal" if self.selected_job else "disabled")
            return
        self._render_plot_section(
            panels[0],
            on_done=lambda: self._render_plot_batch(panels[1:], batch),
        )

    def _render_plot_section(self, panel: str, on_done=None) -> None:
        viewer = self.plot_viewers.get(panel)
        if viewer is None:
            if on_done is not None:
                on_done()
            return
        button = self.plot_buttons.get(panel)
        if button is not None:
            button.configure(text="Rendering...", state="disabled")
        self._plot_requests[panel] = self._plot_requests.get(panel, 0) + 1
        request = self._plot_requests[panel]
        if not self.selected_job:
            viewer.show_message("No job selected")
            if button is not None:
                button.configure(text="Render", state="disabled")
            if on_done is not None:
                on_done()
            return
        job_dir = self.jobs[self.selected_job]

        if panel == self.PANEL_FLD:
            campaign = self._campaign_jobs()
            show_paths = self.fld_paths_var.get()

            def task(_ctx):
                return flc.fld_for_jobs(campaign, self.cache, show_paths=show_paths)
        else:
            factory = {
                self.PANEL_FORCE: force_displacement.build,
                self.PANEL_ENERGY: material_response.energy,
                self.PANEL_STRAIN: strain.strain_path,
                self.PANEL_VH: vh_plotting.dome_rate,
                self.PANEL_TRIAX: strain.triaxiality,
            }[panel]

            def task(_ctx):
                return factory(job_dir, self.cache)

        viewer.show_message("Rendering...")

        def success(result):
            if request != self._plot_requests.get(panel):
                return
            fig, reason = result
            if fig is None:
                viewer.show_message(reason or "No data")
            else:
                viewer.show_figure(fig, self.PLOT_TITLES.get(panel, panel))
            if button is not None:
                button.configure(text="Render", state="normal")
            if on_done is not None:
                on_done()

        def failure(exc):
            if request != self._plot_requests.get(panel):
                return
            viewer.show_message(f"Plot failed: {exc}")
            if button is not None:
                button.configure(text="Render", state="normal")
            if on_done is not None:
                on_done()

        self.app.tasks.submit(f"Render {panel}", task, on_success=success, on_error=failure)
