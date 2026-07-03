from __future__ import annotations

import os
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from app.constants import FEM_GUI_DIR, MS_OPTIONS, PIP_OPTIONS, PROJECT_ROOT, SETTINGS_PATH, TEST_TYPES, VELOCITY_PROFILES, WIDTH_OPTIONS

_mpl_dir = FEM_GUI_DIR / ".cache" / "matplotlib"
_mpl_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from gui.widgets import LabeledEntry, MetricCard, NumberSpec, SectionFrame, ToolTip, ValidatedEntry
from logic.job_config import JobConfig, load_streamlit_defaults, make_study_root_name, save_job_defaults
from logic.mesh_estimates import mesh_estimates, suggest_resources
from logic.stl_preview import punch_preview_figure
from services.deploy import DeployService

from .base import BasePage


ADVANCED_FIELDS = [
    "bm_p_inner_x", "bm_p_inner_r", "bm_p_circle_r", "bm_p_xzplane_1",
    "bm_w200_section1_y", "bm_w200_section2_r", "bm_w200_section3_r",
    "bm_mesh_section1_x", "bm_mesh_section1_y", "bm_mesh_section2_x",
    "bm_mesh_section2_y", "bm_mesh_section3_y", "bm_mesh_section3_1_y",
    "bm_mesh_section4_y", "bm_mesh_w200_section1", "bm_mesh_w200_section2",
    "bm_mesh_w200_section3", "bm_mesh_w200_section4",
]


class SubmitJobPage(BasePage):
    title = "Submit Job"

    numeric_specs = {
        "thickness": NumberSpec(minimum=0.1, step=0.1),
        "angle": NumberSpec(minimum=0, maximum=90, step=1),
        "punch_diam": NumberSpec(minimum=1, step=1),
        "mesh_factor": NumberSpec(minimum=0.1, step=0.1),
        "thickness_seeds": NumberSpec(minimum=1, maximum=64, step=1, integer=True),
        "punch_speed": NumberSpec(minimum=0.1, step=0.5),
        "punch_displacement": NumberSpec(minimum=0.1, step=1),
        "fr_punch": NumberSpec(minimum=0, maximum=0.5, step=0.01),
        "num_cpus": NumberSpec(minimum=1, maximum=64, step=1, integer=True),
        "slurm_mem_per_cpu_gb": NumberSpec(minimum=1, step=1),
        "slurm_time_hours": NumberSpec(minimum=1, maximum=168, step=1, integer=True),
        "bm_p_inner_x": NumberSpec(minimum=0.1, step=0.5),
        "bm_p_inner_r": NumberSpec(minimum=1, step=5),
        "bm_p_circle_r": NumberSpec(minimum=1, step=1),
        "bm_p_xzplane_1": NumberSpec(minimum=0.1, step=0.5),
        "bm_w200_section1_y": NumberSpec(minimum=0.1, step=1),
        "bm_w200_section2_r": NumberSpec(minimum=0.1, step=1),
        "bm_w200_section3_r": NumberSpec(minimum=0.1, step=1),
        "bm_mesh_section1_x": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_section1_y": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_section2_x": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_section2_y": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_section3_y": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_section3_1_y": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_section4_y": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_w200_section1": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_w200_section2": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_w200_section3": NumberSpec(minimum=0.01, step=0.05),
        "bm_mesh_w200_section4": NumberSpec(minimum=0.01, step=0.05),
    }

    help_text = {
        "test_type": "Nakazima, Marciniak, or PiP simulation workflow.",
        "width": "Specimen width in millimeters.",
        "thickness": "Blank sheet thickness in millimeters.",
        "angle": "Material orientation angle in degrees.",
        "punch_diam": "Nakazima/Marciniak punch diameter in millimeters. PiP uses the selected CAD punch instead.",
        "pip_id": "Inner punch CAD/STL identifier for PiP tests.",
        "mesh_factor": "Global multiplier for the legacy BM mesh sizes.",
        "thickness_seeds": "Number of C3D8R elements through the thickness.",
        "mass_scaling": "Explicit mass-scaling target time increment.",
        "punch_speed": "Standard Nakazima/Marciniak punch speed. Disabled for PiP.",
        "punch_displacement": "Standard Nakazima/Marciniak punch travel. Disabled for PiP.",
        "punch_velocity_profile": "smoothstep decelerates near fracture; constant keeps strain rate steadier for V&H analysis.",
        "fr_punch": "Coulomb friction coefficient between punch and blank.",
        "enable_symmetries": "Apply XSYMM and YSYMM boundary conditions.",
        "bm_mesh_manual": "Use absolute BM mesh settings below instead of scaling by Mesh Factor.",
        "bm_mesh_tag": "Optional manual mesh suffix used in directory labels.",
        "num_cpus": "Abaqus/Explicit thread count and SLURM cpus-per-task.",
        "abaqus_memory_percent": "Abaqus memory percentage passed to the job script.",
        "slurm_mem_per_cpu_gb": "SLURM memory request per CPU in GB.",
        "slurm_time_hours": "SLURM wall-clock time limit in hours.",
        "bm_p_inner_x": "Vertical partition at x = P_inner_x. Not used by W200.",
        "bm_p_inner_r": "Radius of the curved partition centered at (P_inner_x + P_inner_r, 12.5).",
        "bm_p_circle_r": "Radius of the circular partition centered at the specimen origin.",
        "bm_p_xzplane_1": "Horizontal partition below y = 12.5 mm.",
        "bm_w200_section1_y": "W200 inner square partition dimension.",
        "bm_w200_section2_r": "W200 second radial partition.",
        "bm_w200_section3_r": "W200 third radial partition.",
        "bm_mesh_section1_x": "Target element size in W20-W120 section 1 x direction.",
        "bm_mesh_section1_y": "Target element size in W20-W120 section 1 y direction.",
        "bm_mesh_section2_x": "Target element size in W20-W120 section 2 x direction.",
        "bm_mesh_section2_y": "Target element size in W20-W120 section 2 y direction.",
        "bm_mesh_section3_y": "Target element size in W20-W120 section 3.",
        "bm_mesh_section3_1_y": "Target element size in W20-W120 section 3_1.",
        "bm_mesh_section4_y": "Target element size in W20-W120 section 4.",
        "bm_mesh_w200_section1": "Target element size in W200 section 1.",
        "bm_mesh_w200_section2": "Target element size in W200 section 2.",
        "bm_mesh_w200_section3": "Target element size in W200 section 3.",
        "bm_mesh_w200_section4": "Target element size in W200 section 4.",
    }

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.deploy = DeployService()
        self.defaults_path = SETTINGS_PATH.parent / "job_defaults.json"
        self.entries: dict[str, ValidatedEntry] = {}
        self.text_entries: dict[str, LabeledEntry] = {}
        self.option_menus: dict[str, ctk.CTkOptionMenu] = {}
        self._pip_canvas: FigureCanvasTkAgg | None = None
        self._pip_image = None
        self._mesh_zone_image = None
        self._last_pip_key = ""
        self._build_vars(load_streamlit_defaults())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.scroll.grid_columnconfigure(0, weight=1)
        self._build()
        self._bind_preview_updates()
        self._update_field_states()
        self.update_preview()
        self._update_pip_preview(force=True)

    def _build_vars(self, cfg: JobConfig) -> None:
        self.v = {
            "test_type": ctk.StringVar(value=cfg.test_type),
            "width": ctk.StringVar(value=str(cfg.width)),
            "thickness": ctk.StringVar(value=str(cfg.thickness)),
            "angle": ctk.StringVar(value=str(cfg.angle)),
            "punch_diam": ctk.StringVar(value=str(cfg.punch_diam)),
            "pip_id": ctk.StringVar(value=cfg.pip_id),
            "mesh_factor": ctk.StringVar(value=str(cfg.mesh_factor)),
            "thickness_seeds": ctk.StringVar(value=str(cfg.thickness_seeds)),
            "mass_scaling": ctk.StringVar(value=f"{cfg.mass_scaling:.1e}"),
            "punch_speed": ctk.StringVar(value=str(cfg.punch_speed)),
            "punch_displacement": ctk.StringVar(value=str(cfg.punch_displacement)),
            "punch_velocity_profile": ctk.StringVar(value=cfg.punch_velocity_profile),
            "fr_punch": ctk.StringVar(value=str(cfg.fr_punch)),
            "enable_symmetries": ctk.BooleanVar(value=cfg.enable_symmetries),
            "bm_mesh_manual": ctk.BooleanVar(value=cfg.bm_mesh_manual),
            "bm_mesh_tag": ctk.StringVar(value=cfg.bm_mesh_tag),
            "num_cpus": ctk.StringVar(value=str(self.session.settings.preferred_cpus or cfg.num_cpus)),
            "abaqus_memory_percent": ctk.StringVar(value=str(self.session.settings.preferred_memory_percent)),
            "slurm_mem_per_cpu_gb": ctk.StringVar(value=str(self.session.settings.preferred_mem_per_cpu_gb)),
            "slurm_time_hours": ctk.StringVar(value=str(cfg.slurm_time_hours)),
        }
        for name in ADVANCED_FIELDS:
            self.v[name] = ctk.StringVar(value=str(getattr(cfg, name)))

    def _build(self) -> None:
        basic = SectionFrame(self.scroll, "Model parameters", self.theme)
        basic.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        b = basic.body
        for col in range(5):
            b.grid_columnconfigure(col, weight=1)
        self._option(b, "Test Type", "test_type", TEST_TYPES, 0, 0)
        self._option(b, "Width", "width", [str(w) for w in WIDTH_OPTIONS], 0, 1)
        self._entry(b, "Thickness", "thickness", 0, 2)
        self._entry(b, "Angle", "angle", 0, 3)
        self._entry(b, "Punch Diameter", "punch_diam", 0, 4)
        self._option(b, "PiP Punch", "pip_id", PIP_OPTIONS, 1, 0)
        self._entry(b, "Mesh Factor", "mesh_factor", 1, 1)
        self._entry(b, "Thickness Seeds", "thickness_seeds", 1, 2)
        self._option(b, "Mass Scaling dt", "mass_scaling", [f"{v:.1e}" for v in MS_OPTIONS], 1, 3)
        self._entry(b, "Punch Speed", "punch_speed", 1, 4)
        self._entry(b, "Punch Travel", "punch_displacement", 2, 0)
        self._option(b, "Velocity Profile", "punch_velocity_profile", VELOCITY_PROFILES, 2, 1)
        self._entry(b, "Punch Friction", "fr_punch", 2, 2)
        check = ctk.CTkCheckBox(b, text="Enable symmetries", variable=self.v["enable_symmetries"])
        check.grid(row=2, column=3, padx=8, pady=8, sticky="w")
        ToolTip(check, self.help_text["enable_symmetries"])

        self._build_mesh_settings(row=1)
        self._build_pip_preview(row=2)
        self._build_compute(row=3)
        self._build_preview(row=4)

    def _build_mesh_settings(self, row: int) -> None:
        mesh = SectionFrame(self.scroll, "Advanced BM mesh settings", self.theme)
        mesh.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        m = mesh.body
        m.grid_columnconfigure(0, weight=1)
        self._add_mesh_zone_image(m)

        top = ctk.CTkFrame(m, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        top.grid_columnconfigure(1, weight=1)
        manual = ctk.CTkCheckBox(top, text="Manual mesh settings", variable=self.v["bm_mesh_manual"])
        manual.grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ToolTip(manual, self.help_text["bm_mesh_manual"])
        tag = LabeledEntry(top, "Mesh Tag", self.v["bm_mesh_tag"], self.theme)
        tag.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        ToolTip(tag.entry, self.help_text["bm_mesh_tag"])
        self.text_entries["bm_mesh_tag"] = tag

        self._mesh_group(
            m,
            "Partition geometry for W20-W120",
            [
                ("Inner split x", "bm_p_inner_x"),
                ("Inner arc radius", "bm_p_inner_r"),
                ("Circle radius", "bm_p_circle_r"),
                ("XZ plane y", "bm_p_xzplane_1"),
            ],
            2,
        )
        self._mesh_group(
            m,
            "W200 partition geometry",
            [
                ("W200 section 1 y", "bm_w200_section1_y"),
                ("W200 section 2 r", "bm_w200_section2_r"),
                ("W200 section 3 r", "bm_w200_section3_r"),
            ],
            3,
        )
        self._mesh_group(
            m,
            "Target element sizes for W20-W120",
            [
                ("S1 x", "bm_mesh_section1_x"),
                ("S1 y", "bm_mesh_section1_y"),
                ("S2 x", "bm_mesh_section2_x"),
                ("S2 y", "bm_mesh_section2_y"),
                ("S3 y", "bm_mesh_section3_y"),
                ("S3_1 y", "bm_mesh_section3_1_y"),
                ("S4 y", "bm_mesh_section4_y"),
            ],
            4,
        )
        self._mesh_group(
            m,
            "Target element sizes for W200",
            [
                ("W200 S1", "bm_mesh_w200_section1"),
                ("W200 S2", "bm_mesh_w200_section2"),
                ("W200 S3", "bm_mesh_w200_section3"),
                ("W200 S4", "bm_mesh_w200_section4"),
            ],
            5,
        )

    def _add_mesh_zone_image(self, parent: ctk.CTkFrame) -> None:
        path = PROJECT_ROOT / "report" / "img" / "gui_mesh_settings.png"
        if not path.exists():
            ctk.CTkLabel(parent, text="Mesh zone diagram not found.", text_color=self.theme.colors.text_muted).grid(
                row=0, column=0, sticky="w", padx=8, pady=8
            )
            return
        image = Image.open(path)
        # The report screenshot contains the annotated diagram plus the Streamlit
        # controls below it.  Crop to the diagram card so the desktop page shows
        # only the annotated mesh-zone reference.
        if image.width >= 2000 and image.height >= 1400:
            image = image.crop((40, 105, min(2025, image.width), min(1390, image.height)))
        max_width = 980
        scale = min(1.0, max_width / max(1, image.width))
        size = (int(image.width * scale), int(image.height * scale))
        self._mesh_zone_image = ctk.CTkImage(dark_image=image, light_image=image, size=size)
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 10))
        wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(wrap, image=self._mesh_zone_image, text="").grid(row=0, column=0, padx=8, pady=4)

    def _mesh_group(self, parent: ctk.CTkFrame, title: str, fields: list[tuple[str, str]], row: int) -> None:
        frame = ctk.CTkFrame(parent, **self.theme.frame_kwargs(alt=True))
        frame.grid(row=row, column=0, sticky="ew", padx=4, pady=6)
        for col in range(4):
            frame.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(frame, text=title, text_color=self.theme.colors.text_muted).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(8, 2)
        )
        for idx, (label, key) in enumerate(fields):
            self._entry(frame, label, key, 1 + idx // 4, idx % 4)

    def _build_pip_preview(self, row: int) -> None:
        self.pip_section = SectionFrame(self.scroll, "PiP punch preview", self.theme)
        self.pip_section.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        body = self.pip_section.body
        body.grid_columnconfigure(0, weight=1)
        self.pip_preview_frame = ctk.CTkFrame(body, **self.theme.frame_kwargs(alt=True))
        self.pip_preview_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.pip_preview_frame.grid_columnconfigure(0, weight=1)
        self.step_button = ctk.CTkButton(
            body,
            text="Download STEP",
            command=self.open_step_location,
            **self.theme.button_kwargs(),
        )
        self.step_button.grid(row=1, column=0, sticky="w", padx=4, pady=(6, 0))

    def _build_compute(self, row: int) -> None:
        compute = SectionFrame(self.scroll, "Computational settings", self.theme)
        compute.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        c = compute.body
        for col in range(5):
            c.grid_columnconfigure(col, weight=1)
        self._entry(c, "Solver CPUs", "num_cpus", 0, 0)
        self._memory_slider(c, 0, 1)
        self._entry(c, "Mem per CPU [GB]", "slurm_mem_per_cpu_gb", 0, 2)
        self._entry(c, "Wall time [h]", "slurm_time_hours", 0, 3)
        ctk.CTkButton(c, text="Use suggested resources", command=self.use_suggested, **self.theme.button_kwargs()).grid(
            row=0, column=4, padx=8, pady=8, sticky="ew"
        )

    def _build_preview(self, row: int) -> None:
        preview = SectionFrame(self.scroll, "Preview and submission", self.theme)
        preview.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        p = preview.body
        p.grid_columnconfigure(0, weight=1)
        self.mesh_metric = MetricCard(p, self.theme, "-", "Estimated mesh cells")
        self.mesh_metric.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 10))
        self.preview_text = ctk.CTkTextbox(p, height=120, fg_color=self.theme.colors.input_bg)
        self.preview_text.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 10))
        buttons = ctk.CTkFrame(p, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew")
        ctk.CTkButton(buttons, text="Submit", command=self.submit_job, **self.theme.button_kwargs(primary=True)).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(buttons, text="Save as default", command=self.save_defaults, **self.theme.button_kwargs()).pack(
            side="left", padx=8
        )

    def _entry(self, parent, label: str, key: str, row: int, col: int) -> ValidatedEntry:
        entry = ValidatedEntry(
            parent,
            label,
            self.v[key],
            self.theme,
            spec=self.numeric_specs.get(key),
            tooltip=self.help_text.get(key, ""),
        )
        entry.grid(row=row, column=col, sticky="ew", padx=8, pady=8)
        self.entries[key] = entry
        return entry

    def _option(self, parent, label: str, key: str, values: list[str], row: int, col: int) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=col, sticky="ew", padx=8, pady=8)
        frame.grid_columnconfigure(0, weight=1)
        label_widget = ctk.CTkLabel(frame, text=label, text_color=self.theme.colors.text_muted, anchor="w")
        label_widget.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        menu = ctk.CTkOptionMenu(
            frame,
            variable=self.v[key],
            values=values,
            command=lambda _=None: self._option_changed(key),
        )
        menu.grid(row=1, column=0, sticky="ew")
        self.option_menus[key] = menu
        ToolTip(label_widget, self.help_text.get(key, ""))
        ToolTip(menu, self.help_text.get(key, ""))

    def _memory_slider(self, parent, row: int, col: int) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=col, sticky="ew", padx=8, pady=8)
        frame.grid_columnconfigure(0, weight=1)
        self.memory_label = ctk.CTkLabel(frame, text="", text_color=self.theme.colors.text_muted, anchor="w")
        self.memory_label.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        self.memory_slider = ctk.CTkSlider(
            frame,
            from_=50,
            to=95,
            number_of_steps=45,
            command=self._memory_slider_changed,
        )
        self.memory_slider.grid(row=1, column=0, sticky="ew")
        ToolTip(self.memory_slider, self.help_text["abaqus_memory_percent"])
        self._set_memory_value(self.v["abaqus_memory_percent"].get())

    def _option_changed(self, key: str) -> None:
        if key in {"test_type", "width"}:
            self._update_field_states()
        if key in {"test_type", "pip_id"}:
            self._update_pip_preview()
        self.update_preview()

    def _memory_slider_changed(self, value: float) -> None:
        self._set_memory_value(int(round(value)), update_slider=False)
        self.update_preview()

    def _set_memory_value(self, value, update_slider: bool = True) -> None:
        try:
            numeric = int(round(float(value)))
        except (TypeError, ValueError):
            numeric = 90
        numeric = max(50, min(95, numeric))
        self.v["abaqus_memory_percent"].set(str(numeric))
        if update_slider and hasattr(self, "memory_slider"):
            self.memory_slider.set(numeric)
        if hasattr(self, "memory_label"):
            self.memory_label.configure(text=f"Abaqus memory: {numeric}%")

    def _bind_preview_updates(self) -> None:
        for key, variable in self.v.items():
            variable.trace_add("write", lambda *_: self.after_idle(self.update_preview))
        for key in ("test_type", "width", "bm_mesh_manual"):
            self.v[key].trace_add("write", lambda *_: self.after_idle(self._update_field_states))
        self.v["pip_id"].trace_add("write", lambda *_: self.after_idle(self._update_pip_preview))

    def _update_field_states(self) -> None:
        is_pip = self.v["test_type"].get() == "pip"
        manual = bool(self.v["bm_mesh_manual"].get())
        width = self.v["width"].get()
        for key in ("punch_speed", "punch_displacement", "fr_punch", "punch_diam"):
            if key in self.entries:
                self.entries[key].set_enabled(not is_pip)
        if "punch_velocity_profile" in self.option_menus:
            self.option_menus["punch_velocity_profile"].configure(state="disabled" if is_pip else "normal")
        if "bm_mesh_tag" in self.text_entries:
            self.text_entries["bm_mesh_tag"].set_enabled(manual)

        w20_fields = {
            "bm_p_inner_x", "bm_p_inner_r", "bm_p_circle_r", "bm_p_xzplane_1",
            "bm_mesh_section1_x", "bm_mesh_section1_y", "bm_mesh_section2_x",
            "bm_mesh_section2_y", "bm_mesh_section3_y", "bm_mesh_section3_1_y",
            "bm_mesh_section4_y",
        }
        w200_fields = {
            "bm_w200_section1_y", "bm_w200_section2_r", "bm_w200_section3_r",
            "bm_mesh_w200_section1", "bm_mesh_w200_section2", "bm_mesh_w200_section3", "bm_mesh_w200_section4",
        }
        for key in w20_fields:
            self.entries[key].set_enabled(manual and width != "200")
        for key in w200_fields:
            self.entries[key].set_enabled(manual)
        if is_pip:
            self.pip_section.grid()
        else:
            self.pip_section.grid_remove()

    def _cfg(self) -> JobConfig:
        def f(key: str, default: float = 0.0) -> float:
            try:
                return float(self.v[key].get())
            except ValueError:
                return default

        def i(key: str, default: int = 0) -> int:
            try:
                return int(float(self.v[key].get()))
            except ValueError:
                return default

        return JobConfig(
            test_type=self.v["test_type"].get(),
            width=i("width", 100),
            thickness=f("thickness", 1.5),
            angle=f("angle", 0.0),
            punch_diam=f("punch_diam", 100.0),
            mesh_factor=f("mesh_factor", 3.0),
            thickness_seeds=i("thickness_seeds", 16),
            enable_symmetries=bool(self.v["enable_symmetries"].get()),
            bm_mesh_manual=bool(self.v["bm_mesh_manual"].get()),
            bm_mesh_tag=self.v["bm_mesh_tag"].get(),
            mass_scaling=float(self.v["mass_scaling"].get()),
            punch_speed=f("punch_speed", 5.0),
            punch_displacement=f("punch_displacement", 35.0),
            punch_velocity_profile=self.v["punch_velocity_profile"].get(),
            fr_punch=f("fr_punch", 0.0),
            pip_id=self.v["pip_id"].get(),
            num_cpus=i("num_cpus", 24),
            abaqus_memory_percent=i("abaqus_memory_percent", 90),
            slurm_mem_per_cpu_gb=f("slurm_mem_per_cpu_gb", 4.0),
            slurm_time_hours=i("slurm_time_hours", 48),
            **{key: f(key, getattr(JobConfig(), key)) for key in ADVANCED_FIELDS},
        ).sanitize()

    def update_preview(self) -> None:
        try:
            cfg = self._cfg()
            job_name = self.deploy.preview_name(cfg)
            study = make_study_root_name(cfg)
            estimates, total = mesh_estimates(cfg, [cfg.width])
            resource = suggest_resources(estimates[0].solid)
            sym_desc = "quarter-model" if cfg.enable_symmetries else "full-model"
            self.mesh_metric.set_metric(
                f"{total:,}",
                f"{sym_desc}: {estimates[0].in_plane:,} in-plane x {cfg.thickness_seeds} thickness seeds",
            )
            text = (
                f"Job name: {job_name}\n"
                f"Study root: {study}\n"
                f"Suggested resources: {resource['num_cpus']} CPUs, "
                f"{resource['slurm_mem_per_cpu_gb']} GB/CPU, {resource['slurm_time_limit']} wall time\n"
                f"Deploy command: bash deploy.sh {cfg.test_type} {cfg.thickness:g} {cfg.angle:g} "
                f"{cfg.width} {cfg.pip_id if cfg.test_type == 'pip' else 'none'} "
                f"{cfg.mesh_factor:g} {cfg.mass_scaling:.2e} {cfg.punch_speed:g}"
            )
        except Exception as exc:
            self.mesh_metric.set_metric("-", "Invalid configuration")
            text = f"Invalid configuration: {exc}"
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def _update_pip_preview(self, force: bool = False) -> None:
        if not hasattr(self, "pip_preview_frame"):
            return
        key = f"{self.v['test_type'].get()}:{self.v['pip_id'].get()}:{self.theme.mode}"
        if not force and key == self._last_pip_key:
            return
        self._last_pip_key = key
        for child in self.pip_preview_frame.winfo_children():
            child.destroy()
        self._pip_canvas = None
        pip_id = self.v["pip_id"].get()
        punch_dir = PROJECT_ROOT / "PiP_Punches"
        stl_path = punch_dir / f"{pip_id}.stl"
        png_path = punch_dir / f"{pip_id}.png"
        if stl_path.exists():
            fig = punch_preview_figure(stl_path, self.theme)
            self._pip_canvas = FigureCanvasTkAgg(fig, master=self.pip_preview_frame)
            self._pip_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
            self._pip_canvas.draw_idle()
        elif png_path.exists():
            image = Image.open(png_path)
            scale = min(1.0, 680 / max(1, image.width))
            size = (int(image.width * scale), int(image.height * scale))
            self._pip_image = ctk.CTkImage(dark_image=image, light_image=image, size=size)
            ctk.CTkLabel(self.pip_preview_frame, image=self._pip_image, text="").grid(row=0, column=0, padx=8, pady=8)
        else:
            ctk.CTkLabel(
                self.pip_preview_frame,
                text=f"No STL or PNG preview found for {pip_id}.",
                text_color=self.theme.colors.text_muted,
            ).grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        step_path = punch_dir / f"{pip_id}.step"
        self.step_button.configure(state="normal" if step_path.exists() else "disabled", text=f"Open {pip_id}.step location")

    def open_step_location(self) -> None:
        step_path = PROJECT_ROOT / "PiP_Punches" / f"{self.v['pip_id'].get()}.step"
        if step_path.exists():
            self.app.open_path(step_path.parent)
        else:
            messagebox.showinfo("STEP not found", f"{step_path.name} was not found.")

    def _validate_form(self) -> bool:
        invalid = []
        for key, entry in self.entries.items():
            if not entry.is_valid():
                invalid.append(f"{key}: {entry.error_message}")
        if invalid:
            message = "Fix invalid inputs before submitting:\n" + "\n".join(invalid[:6])
            self.session.logger.warning(message)
            if hasattr(self.app, "show_toast"):
                self.app.show_toast("Invalid job parameters. Check red fields.", "error")
            else:
                messagebox.showerror("Invalid inputs", message)
            return False
        return True

    def use_suggested(self) -> None:
        if not self._validate_form():
            return
        cfg = self._cfg()
        estimates, _ = mesh_estimates(cfg, [cfg.width])
        resource = suggest_resources(estimates[0].solid)
        self.v["num_cpus"].set(str(resource["num_cpus"]))
        self._set_memory_value(resource["abaqus_memory_percent"])
        self.v["slurm_mem_per_cpu_gb"].set(str(resource["slurm_mem_per_cpu_gb"]))
        self.v["slurm_time_hours"].set(str(resource["slurm_time_hours"]))

    def save_defaults(self) -> None:
        if not self._validate_form():
            return
        cfg = self._cfg()
        save_job_defaults(self.defaults_path, cfg)
        self.session.settings.preferred_cpus = cfg.num_cpus
        self.session.settings.preferred_memory_percent = cfg.abaqus_memory_percent
        self.session.settings.preferred_mem_per_cpu_gb = cfg.slurm_mem_per_cpu_gb
        self.app.save_settings()
        self.session.logger.info("Saved current job settings as defaults.")
        if hasattr(self.app, "show_toast"):
            self.app.show_toast("Saved job defaults.", "success")

    def submit_job(self) -> None:
        if not self._validate_form():
            return
        cfg = self._cfg()
        job_name = self.deploy.preview_name(cfg)
        if not self.session.connection.connected:
            if not messagebox.askyesno(
                "Submit without verified connection",
                "Euler connection has not been verified in this session. Submit anyway?",
            ):
                return

        def task(ctx):
            ctx.log(f"Submitting {job_name}")
            ctx.progress(0.1, "Starting deploy.sh")
            result = self.deploy.submit_job(cfg)
            ctx.progress(1.0, "Submission finished")
            return result

        def success(result):
            if result.returncode == 0:
                self.session.logger.info("Submitted job successfully.")
                if hasattr(self.app, "show_toast"):
                    self.app.show_toast(f"Submitted {job_name}", "success")
                if result.stdout:
                    self.session.logger.info(result.stdout.strip()[-3000:])
            else:
                error = (result.stderr or result.stdout or "deploy.sh failed").strip()
                self.session.logger.error(error)
                if hasattr(self.app, "show_toast"):
                    self.app.show_toast(f"Submission failed: {error[:120]}", "error")

        self.app.tasks.submit(f"Submit {job_name}", task, on_success=success)

    def on_theme_update(self) -> None:
        for entry in self.entries.values():
            entry.refresh_theme()
        for entry in self.text_entries.values():
            entry.refresh_theme()
        self.preview_text.configure(fg_color=self.theme.colors.input_bg)
        self.mesh_metric.refresh_theme()
        self._update_pip_preview(force=True)
