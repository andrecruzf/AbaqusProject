from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from app.constants import FEM_GUI_DIR

_mpl_dir = FEM_GUI_DIR / ".cache" / "matplotlib"
_mpl_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


@dataclass(frozen=True)
class NumberSpec:
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    integer: bool = False


class ToolTip:
    def __init__(self, widget, text: str, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text.strip()
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip: tk.Toplevel | None = None
        if self.text:
            widget.bind("<Enter>", self._schedule, add="+")
            widget.bind("<Leave>", self._hide, add="+")
            widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._tip,
            text=self.text,
            justify="left",
            background="#111418",
            foreground="#E6EAF0",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            wraplength=320,
        )
        label.pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


class SectionFrame(ctk.CTkFrame):
    def __init__(self, master, title: str, theme, **kwargs) -> None:
        super().__init__(master, **theme.frame_kwargs(), **kwargs)
        self.theme = theme
        self.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=theme.colors.text,
        )
        self.title_label.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.body.grid_columnconfigure(0, weight=1)

    def refresh_theme(self) -> None:
        self.configure(**self.theme.frame_kwargs())
        self.title_label.configure(text_color=self.theme.colors.text)


class LabeledEntry(ctk.CTkFrame):
    def __init__(
        self,
        master,
        label: str,
        variable: tk.Variable,
        theme,
        width: int = 130,
        **entry_kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.theme = theme
        self.grid_columnconfigure(0, weight=1)
        self.label = ctk.CTkLabel(self, text=label, text_color=theme.colors.text_muted, anchor="w")
        self.label.grid(
            row=0, column=0, sticky="ew", pady=(0, 2)
        )
        self.entry = ctk.CTkEntry(
            self,
            textvariable=variable,
            width=width,
            fg_color=theme.colors.input_bg,
            border_color=theme.colors.border,
            **entry_kwargs,
        )
        self.entry.grid(row=1, column=0, sticky="ew")

    def set_enabled(self, enabled: bool) -> None:
        self.entry.configure(state="normal" if enabled else "disabled")

    def refresh_theme(self) -> None:
        self.entry.configure(fg_color=self.theme.colors.input_bg, border_color=self.theme.colors.border)
        self.label.configure(text_color=self.theme.colors.text_muted)


class ValidatedEntry(LabeledEntry):
    def __init__(
        self,
        master,
        label: str,
        variable: tk.Variable,
        theme,
        spec: NumberSpec | None = None,
        tooltip: str = "",
        width: int = 130,
        **entry_kwargs,
    ) -> None:
        self.spec = spec
        self._enabled = True
        self._valid = True
        self.error_message = ""
        super().__init__(master, label, variable, theme, width=width, **entry_kwargs)
        self.tooltip = ToolTip(self.entry, tooltip)
        ToolTip(self.label, tooltip)
        variable.trace_add("write", lambda *_: self.validate())
        self.entry.bind("<FocusOut>", lambda _event: self.validate(), add="+")
        self.validate()

    def validate(self) -> bool:
        if not self._enabled:
            self._valid = True
            self.error_message = ""
            self.entry.configure(border_color=self.theme.colors.border)
            return True
        if self.spec is None:
            value = str(self.entry.get()).strip()
            self._valid = bool(value)
            self.error_message = "" if self._valid else "Value is required."
            self.entry.configure(border_color=self.theme.colors.border if self._valid else self.theme.colors.error)
            return self._valid

        text = str(self.entry.get()).strip()
        try:
            value = float(text)
        except ValueError:
            self._valid = False
            self.error_message = "Enter a numeric value."
            self.entry.configure(border_color=self.theme.colors.error)
            return False
        if self.spec.integer and abs(value - round(value)) > 1e-9:
            self._valid = False
            self.error_message = "Enter a whole number."
        elif self.spec.minimum is not None and value < self.spec.minimum - 1e-9:
            self._valid = False
            self.error_message = f"Minimum value is {self.spec.minimum:g}."
        elif self.spec.maximum is not None and value > self.spec.maximum + 1e-9:
            self._valid = False
            self.error_message = f"Maximum value is {self.spec.maximum:g}."
        elif self.spec.step is not None and self.spec.step > 0:
            quotient = value / self.spec.step
            self._valid = abs(quotient - round(quotient)) < 1e-7
            self.error_message = "" if self._valid else f"Use increments of {self.spec.step:g}."
        else:
            self._valid = True
            self.error_message = ""
        self.entry.configure(border_color=self.theme.colors.border if self._valid else self.theme.colors.error)
        return self._valid

    def is_valid(self) -> bool:
        return self.validate()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        state = "normal" if enabled else "disabled"
        fg = self.theme.colors.input_bg if enabled else self.theme.colors.panel_alt
        text = self.theme.colors.text if enabled else self.theme.colors.text_muted
        self.entry.configure(state=state, fg_color=fg, text_color=text, border_color=self.theme.colors.border)
        self.label.configure(text_color=self.theme.colors.text_muted if enabled else self.theme.colors.border)
        self.validate()

    def refresh_theme(self) -> None:
        self.set_enabled(self._enabled)


class DataTable(ctk.CTkFrame):
    def __init__(self, master, theme, columns: list[str] | None = None) -> None:
        super().__init__(master, **theme.frame_kwargs())
        self.theme = theme
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.columns = columns or []
        self._sort_reverse: dict[str, bool] = {}
        self._configure_style()
        self.tree = ttk.Treeview(self, columns=self.columns, show="headings", selectmode="browse")
        self.v_scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.h_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 0))
        self.v_scroll.grid(row=0, column=1, sticky="ns", pady=(8, 0), padx=(0, 8))
        self.h_scroll.grid(row=1, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))
        if self.columns:
            self.set_columns(self.columns)

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        colors = self.theme.colors
        style.configure(
            "Treeview",
            background=colors.panel,
            foreground=colors.text,
            fieldbackground=colors.panel,
            bordercolor=colors.border,
            rowheight=26,
        )
        style.configure(
            "Treeview.Heading",
            background=colors.panel_alt,
            foreground=colors.text,
            bordercolor=colors.border,
            relief="flat",
        )
        style.map("Treeview", background=[("selected", colors.accent)], foreground=[("selected", "#FFFFFF")])

    def set_columns(self, columns: list[str]) -> None:
        self.columns = columns
        self.tree.configure(columns=columns)
        for col in columns:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_by(c))
            self.tree.column(col, width=max(90, min(240, len(col) * 12)), anchor="w", stretch=True)

    def set_rows(self, rows: Iterable[Iterable[str]], tags: Iterable[str] | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        tag_iter = iter(tags) if tags is not None else None
        for row in rows:
            tag_tuple = ()
            if tag_iter is not None:
                tag = next(tag_iter, "")
                tag_tuple = (tag,) if tag else ()
            self.tree.insert("", "end", values=list(row), tags=tag_tuple)

    def configure_tags(self, mapping: dict[str, dict[str, str]]) -> None:
        for tag, opts in mapping.items():
            self.tree.tag_configure(tag, **opts)

    def sort_by(self, column: str) -> None:
        children = list(self.tree.get_children(""))
        idx = self.columns.index(column)
        reverse = self._sort_reverse.get(column, False)

        def key(item: str):
            value = self.tree.item(item, "values")[idx]
            try:
                return float(str(value).replace("%", ""))
            except ValueError:
                return str(value).lower()

        for item in sorted(children, key=key, reverse=reverse):
            self.tree.move(item, "", "end")
        self._sort_reverse[column] = not reverse

    def selected_values(self) -> list[str] | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return list(self.tree.item(sel[0], "values"))

    def refresh_theme(self) -> None:
        self.configure(**self.theme.frame_kwargs())
        self._configure_style()


class MetricCard(ctk.CTkFrame):
    def __init__(self, master, theme, value: str = "-", caption: str = "") -> None:
        super().__init__(master, **theme.frame_kwargs(alt=True))
        self.theme = theme
        self.grid_columnconfigure(0, weight=1)
        self.value_label = ctk.CTkLabel(self, text=value, font=ctk.CTkFont(size=28, weight="bold"))
        self.value_label.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 0))
        self.caption_label = ctk.CTkLabel(self, text=caption, text_color=theme.colors.text_muted, anchor="w")
        self.caption_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))

    def set_metric(self, value: str, caption: str) -> None:
        self.value_label.configure(text=value)
        self.caption_label.configure(text=caption)

    def refresh_theme(self) -> None:
        self.configure(**self.theme.frame_kwargs(alt=True))
        self.value_label.configure(text_color=self.theme.colors.text)
        self.caption_label.configure(text_color=self.theme.colors.text_muted)


class PlotPanel(ctk.CTkFrame):
    def __init__(self, master, theme) -> None:
        super().__init__(master, **theme.frame_kwargs())
        self.theme = theme
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas: FigureCanvasTkAgg | None = None
        self.toolbar: NavigationToolbar2Tk | None = None
        self.current_figure = None
        self.message = ctk.CTkLabel(self, text="No plot selected", text_color=theme.colors.text_muted)
        self.message.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)

    def show_message(self, message: str) -> None:
        self.clear()
        self.message = ctk.CTkLabel(self, text=message, text_color=self.theme.colors.text_muted)
        self.message.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)

    def show_figure(self, fig) -> None:
        self.clear()
        self.current_figure = fig
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        widget = self.canvas.get_tk_widget()
        widget.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))
        toolbar_frame = ctk.CTkFrame(self, fg_color="transparent")
        toolbar_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side="left", fill="x")
        self.canvas.draw_idle()

    def save_current(self, path: Path) -> None:
        if self.current_figure is None:
            raise RuntimeError("No plot to export")
        self.current_figure.savefig(path, dpi=200, bbox_inches="tight")

    def clear(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.canvas = None
        self.toolbar = None
        self.current_figure = None
