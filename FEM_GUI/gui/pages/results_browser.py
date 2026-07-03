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
    PANEL_VH = "V&H Rate"
    PANEL_TRIAX = "Triaxiality"
    PANEL_FLD = "FLD"
    PLOT_PANELS = [PANEL_FORCE, PANEL_ENERGY, PANEL_VH, PANEL_TRIAX, PANEL_FLD]

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.cache = CsvCache()
        self.scan = ScanResult()
        self.jobs: dict[str, Path] = {}
        self.selected_job: str | None = None
        self.results_dir_var = ctk.StringVar(value=self.session.settings.results_dir)
        self.sync_status_var = ctk.StringVar(value="")
        self.plot_panel_var = ctk.StringVar(value=self.PANEL_FORCE)
        self.fld_paths_var = ctk.BooleanVar(value=True)
        self.video_frame_var = ctk.DoubleVar(value=0)
        self.job_buttons: dict[str, ctk.CTkButton] = {}
        self.media_images: list[ctk.CTkImage] = []
        self.video_frame_images: list[ctk.CTkImage] = []
        self.video_info: dict[Path, tuple[int, float]] = {}
        self.current_video_pair: tuple[Path | None, Path | None] | None = None
        self.current_video_max_frame = 0
        self._video_after_id = None
        self._sync_running = False
        self._plot_request = 0
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
        controls.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(controls, text="Results dir").grid(row=0, column=0, sticky="w", padx=(12, 4), pady=10)
        ctk.CTkEntry(controls, textvariable=self.results_dir_var, width=280).grid(
            row=0, column=1, sticky="w", padx=4, pady=10
        )
        ctk.CTkButton(controls, text="Browse", width=70, command=self.browse_dir, **self.theme.button_kwargs()).grid(
            row=0, column=2, padx=4, pady=10
        )
        self.job_strip = ctk.CTkScrollableFrame(
            controls, orientation="horizontal", height=40, fg_color=self.theme.colors.panel_alt
        )
        self.job_strip.grid(row=0, column=3, sticky="ew", padx=8, pady=6)
        ctk.CTkButton(
            controls, text="Sync results", width=100, command=self.sync_results, **self.theme.button_kwargs(primary=True)
        ).grid(row=0, column=4, padx=(4, 4), pady=10)
        self.sync_status_label = ctk.CTkLabel(
            controls, textvariable=self.sync_status_var, width=60, text_color=self.theme.colors.text_muted
        )
        self.sync_status_label.grid(row=0, column=5, sticky="w", padx=(0, 12), pady=10)

    def _build_viewer(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        self._build_media_section(main)
        self._build_plots_section(main)

    def _build_media_section(self, master: ctk.CTkFrame) -> None:
        media = ctk.CTkFrame(master, **self.theme.frame_kwargs())
        media.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        media.grid_columnconfigure(0, weight=1)
        media.grid_columnconfigure(1, weight=1)
        media.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(media, text="Movies", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 2)
        )
        ctk.CTkLabel(media, text="Mesh pictures", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=2, sticky="w", padx=12, pady=(10, 2)
        )

        self.iso_panel = self._movie_panel(media, "ISO view", column=0)
        self.section_panel = self._movie_panel(media, "Section view", column=1)

        slider_row = ctk.CTkFrame(media, fg_color="transparent")
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

        self.mesh_column = ctk.CTkScrollableFrame(media, width=250, height=300, **self.theme.frame_kwargs(alt=True))
        self.mesh_column.grid(row=1, column=2, rowspan=2, sticky="nsew", padx=(4, 12), pady=(2, 10))

    def _movie_panel(self, master: ctk.CTkFrame, title: str, column: int) -> dict[str, ctk.CTkLabel]:
        panel = ctk.CTkFrame(master, **self.theme.frame_kwargs(alt=True))
        panel.grid(row=1, column=column, sticky="nsew", padx=(12 if column == 0 else 4, 4), pady=2)
        panel.grid_columnconfigure(0, weight=1)
        heading = ctk.CTkLabel(panel, text=title, text_color=self.theme.colors.text_muted)
        heading.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 0))
        image_label = ctk.CTkLabel(panel, text="No movie", text_color=self.theme.colors.text_muted, height=260)
        image_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(2, 8))
        image_label.bind("<Double-Button-1>", lambda _e, t=title: self._open_panel_video(t))
        return {"heading": heading, "image": image_label}

    def _build_plots_section(self, master: ctk.CTkFrame) -> None:
        plots = ctk.CTkFrame(master, **self.theme.frame_kwargs())
        plots.grid(row=1, column=0, sticky="nsew")
        plots.grid_columnconfigure(0, weight=1)
        plots.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(plots, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(header, text="Post-processing plots", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkSegmentedButton(
            header,
            values=self.PLOT_PANELS,
            variable=self.plot_panel_var,
            command=lambda _value: self._render_current_panel(),
        ).pack(side="left")
        self.fld_paths_checkbox = ctk.CTkCheckBox(
            header,
            text="Strain paths",
            variable=self.fld_paths_var,
            command=self._render_current_panel,
        )
        self.fld_paths_checkbox.pack(side="left", padx=14)
        self.plot_viewer = PlotViewer(plots, self.theme)
        self.plot_viewer.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

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
                height=26,
                width=0,
                command=lambda n=name: self.select_job(n),
                **self.theme.button_kwargs(),
            )
            button.pack(side="left", padx=3, pady=2)
            ToolTip(button, name)
            self.job_buttons[name] = button
        if self.selected_job not in self.jobs:
            self.selected_job = next(iter(self.jobs))
        self.select_job(self.selected_job)

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
        self._render_current_panel()

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
        current = int(min(max(round(self.video_frame_var.get()), 0), self.current_video_max_frame))
        self.video_frame_var.set(current)
        self._render_video_frame(current)

    def _disable_video_slider(self, message: str) -> None:
        self.video_slider.configure(state="disabled", to=1, number_of_steps=1)
        self.video_frame_label.configure(text=message)

    def _on_video_frame_change(self, value: float | str) -> None:
        if not self.current_video_pair:
            return
        try:
            frame_index = int(round(float(value)))
        except (TypeError, ValueError):
            frame_index = 0
        if self._video_after_id:
            self.after_cancel(self._video_after_id)
        self._video_after_id = self.after(45, lambda: self._render_video_frame(frame_index))

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
            thumb = self._ctk_image(image, max_width=520, max_height=280)
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
        for child in self.mesh_column.winfo_children():
            child.destroy()
        self.media_images.clear()
        pngs = self._job_files(path, {".png"})
        pngs.sort(key=lambda item: "mesh" not in item.stem.lower())
        if not pngs:
            ctk.CTkLabel(self.mesh_column, text="No pictures", text_color=self.theme.colors.text_muted).pack(
                anchor="w", padx=8, pady=8
            )
            return
        for png in pngs:
            try:
                image = Image.open(png).copy()
            except Exception:
                continue
            thumb = self._ctk_image(image, max_width=230, max_height=180)
            self.media_images.append(thumb)
            label = ctk.CTkLabel(self.mesh_column, image=thumb, text="")
            label.pack(anchor="w", padx=4, pady=(4, 0))
            label.bind("<Double-Button-1>", lambda _e, p=png: self.app.open_path(p))
            ctk.CTkLabel(self.mesh_column, text=png.name, text_color=self.theme.colors.text_muted).pack(
                anchor="w", padx=6, pady=(0, 4)
            )

    @staticmethod
    def _scaled_size(image: Image.Image, max_width: int, max_height: int) -> tuple[int, int]:
        ratio = min(max_width / max(1, image.width), max_height / max(1, image.height), 1.0)
        return (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))

    def _ctk_image(self, image: Image.Image, max_width: int, max_height: int) -> ctk.CTkImage:
        size = self._scaled_size(image, max_width, max_height)
        return ctk.CTkImage(dark_image=image, light_image=image, size=size)

    # ── Plot panels ───────────────────────────────────────────────────────

    def _campaign_jobs(self) -> dict[str, Path]:
        """Jobs sharing the selected job's parent directory, i.e. its FLC set."""
        if not self.selected_job:
            return {}
        parent = Path(self.jobs[self.selected_job]).parent
        siblings = {name: path for name, path in self.jobs.items() if Path(path).parent == parent}
        return siblings or {self.selected_job: self.jobs[self.selected_job]}

    def _render_current_panel(self) -> None:
        panel = self.plot_panel_var.get()
        if panel == self.PANEL_FLD:
            self.fld_paths_checkbox.pack(side="left", padx=14)
        else:
            self.fld_paths_checkbox.pack_forget()
        if not self.selected_job:
            self.plot_viewer.show_message("No job selected")
            return
        job_dir = self.jobs[self.selected_job]
        self._plot_request += 1
        request = self._plot_request

        if panel == self.PANEL_FLD:
            campaign = self._campaign_jobs()
            show_paths = self.fld_paths_var.get()

            def task(_ctx):
                return flc.fld_for_jobs(campaign, self.cache, show_paths=show_paths)
        else:
            factory = {
                self.PANEL_FORCE: force_displacement.build,
                self.PANEL_ENERGY: material_response.energy,
                self.PANEL_VH: vh_plotting.dome_rate,
                self.PANEL_TRIAX: strain.triaxiality,
            }[panel]

            def task(_ctx):
                return factory(job_dir, self.cache)

        self.plot_viewer.show_message("Rendering...")

        def success(result):
            if request != self._plot_request:
                return
            fig, reason = result
            if fig is None:
                self.plot_viewer.show_message(reason or "No data")
            else:
                self.plot_viewer.show_figure(fig, panel)

        self.app.tasks.submit(f"Render {panel}", task, on_success=success)
