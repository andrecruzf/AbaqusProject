from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.constants import FEM_GUI_DIR

_mpl_dir = FEM_GUI_DIR / ".cache" / "matplotlib"
_mpl_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


class PlotViewer(ctk.CTkFrame):
    def __init__(self, master, theme) -> None:
        super().__init__(master, **theme.frame_kwargs())
        self.theme = theme
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.current_figure = None
        self.canvas: FigureCanvasTkAgg | None = None
        self.toolbar: NavigationToolbar2Tk | None = None

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        ctk.CTkButton(actions, text="Export", width=82, command=self.export, **theme.button_kwargs()).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text="Copy", width=82, command=self.copy_snapshot, **theme.button_kwargs()).pack(side="left", padx=6)
        self.status = ctk.CTkLabel(actions, text="No plot loaded", text_color=theme.colors.text_muted)
        self.status.pack(side="left", padx=10)

        self.canvas_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.canvas_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)
        self.show_message("No plot selected")

    def show_message(self, message: str) -> None:
        self.clear_canvas()
        self.status.configure(text=message)
        ctk.CTkLabel(self.canvas_frame, text=message, text_color=self.theme.colors.text_muted).grid(
            row=0, column=0, sticky="nsew", padx=16, pady=16
        )

    def show_figure(self, fig, title: str = "") -> None:
        self.clear_canvas()
        self.current_figure = fig
        self.canvas = FigureCanvasTkAgg(fig, master=self.canvas_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar_frame = ctk.CTkFrame(self.canvas_frame, fg_color="transparent")
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side="left", fill="x")
        self.canvas.draw_idle()
        self.status.configure(text=title or "Plot loaded")

    def export(self) -> None:
        if self.current_figure is None:
            messagebox.showinfo("No plot", "There is no plot to export.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")],
        )
        if not path:
            return
        self.save(Path(path), dpi=300)
        self.status.configure(text=f"Exported {Path(path).name}")

    def save(self, path: Path, dpi: int = 300) -> None:
        if self.current_figure is None:
            raise RuntimeError("No plot to export")
        self.current_figure.savefig(path, dpi=dpi, bbox_inches="tight")

    def copy_snapshot(self) -> None:
        if self.current_figure is None:
            messagebox.showinfo("No plot", "There is no plot to copy.")
            return
        out = Path(tempfile.gettempdir()) / "fem_gui_plot_clipboard.png"
        self.save(out, dpi=200)
        copied_image = False
        if sys.platform == "darwin":
            script = f'set the clipboard to (POSIX file "{out}")'
            copied_image = subprocess.run(["osascript", "-e", script], capture_output=True, text=True).returncode == 0
        if not copied_image:
            self.clipboard_clear()
            self.clipboard_append(str(out))
        self.status.configure(text=f"Copied snapshot: {out.name}")

    def clear_canvas(self) -> None:
        for child in self.canvas_frame.winfo_children():
            child.destroy()
        self.current_figure = None
        self.canvas = None
        self.toolbar = None
