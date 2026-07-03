from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import customtkinter as ctk

from app.log import AppLogger
from app.session import AppSession
from app.settings import SettingsStore
from app.tasks import TaskEvent, TaskRunner
from app.theme import ThemeManager
from gui.pages.ai_assistant import AIAssistantPage
from gui.pages.connection import ConnectionPage
from gui.pages.job_queue import JobQueuePage
from gui.pages.results_browser import ResultsBrowserPage
from gui.pages.submit_job import SubmitJobPage


class FEMApp(ctk.CTk):
    def __init__(self) -> None:
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.theme = ThemeManager(self.settings.theme)
        super().__init__(fg_color=self.theme.colors.bg)
        self.title("Abaqus FEM Pipeline")
        self.geometry(self.settings.window_geometry)
        self.minsize(1180, 760)
        self.logger = AppLogger()
        self.session = AppSession(settings=self.settings, logger=self.logger)
        self.tasks = TaskRunner(self.session)
        self.pages: dict[str, ctk.CTkFrame] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.current_page = ""
        self._toast_after_id = None
        self._toast_widget: ctk.CTkFrame | None = None
        self._build_layout()
        self.show_page("Connection")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<Control-Return>", self._submit_shortcut)
        self.bind_all("<F5>", self._refresh_shortcut)
        self.after(100, self.process_task_events)
        self.after(150, self.drain_logs)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header = ctk.CTkFrame(self, fg_color=self.theme.colors.panel, corner_radius=0)
        self.header.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.header, text="Abaqus FEM Pipeline", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=10
        )
        self.connection_label = ctk.CTkLabel(self.header, text="Not connected", text_color=self.theme.colors.warning)
        self.connection_label.grid(row=0, column=1, sticky="e", padx=16, pady=10)
        self.theme_switch = ctk.CTkSegmentedButton(
            self.header,
            values=["Dark", "Light"],
            command=self.switch_theme,
            selected_color=self.theme.colors.accent,
        )
        self.theme_switch.set(self.settings.theme)
        self.theme_switch.grid(row=0, column=2, padx=16, pady=10)

        self.nav = ctk.CTkFrame(self, fg_color=self.theme.colors.panel, corner_radius=0, width=190)
        self.nav.grid(row=1, column=0, sticky="nsew")
        self.nav.grid_propagate(False)
        self.nav.grid_columnconfigure(0, weight=1)
        for idx, name in enumerate(["Connection", "Submit Job", "Job Queue", "Results", "AI Assistant"]):
            btn = ctk.CTkButton(
                self.nav,
                text=name,
                anchor="w",
                command=lambda n=name: self.show_page(n),
                **self.theme.button_kwargs(),
            )
            btn.grid(row=idx, column=0, sticky="ew", padx=10, pady=(10 if idx == 0 else 4, 4))
            self.nav_buttons[name] = btn

        self.workspace = ctk.CTkFrame(self, fg_color=self.theme.colors.bg, corner_radius=0)
        self.workspace.grid(row=1, column=1, sticky="nsew")
        self.workspace.grid_rowconfigure(0, weight=1)
        self.workspace.grid_columnconfigure(0, weight=1)

        self.bottom = ctk.CTkFrame(self, fg_color=self.theme.colors.panel, corner_radius=0)
        self.bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.bottom.grid_columnconfigure(1, weight=1)
        self.task_label = ctk.CTkLabel(self.bottom, text="Idle", text_color=self.theme.colors.text_muted)
        self.task_label.grid(row=0, column=0, sticky="w", padx=12, pady=8)
        self.progress = ctk.CTkProgressBar(self.bottom, height=8)
        self.progress.grid(row=0, column=1, sticky="ew", padx=12, pady=8)
        self.progress.set(0)

        self._create_pages()

    def _create_pages(self) -> None:
        page_classes = {
            "Connection": ConnectionPage,
            "Submit Job": SubmitJobPage,
            "Job Queue": JobQueuePage,
            "Results": ResultsBrowserPage,
            "AI Assistant": AIAssistantPage,
        }
        for name, cls in page_classes.items():
            page = cls(self.workspace, self)
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()
            self.pages[name] = page

    def show_page(self, name: str) -> None:
        if self.current_page:
            self.pages[self.current_page].grid_remove()
            self.nav_buttons[self.current_page].configure(**self.theme.button_kwargs())
        self.current_page = name
        self.pages[name].grid()
        self.pages[name].on_show()
        self.nav_buttons[name].configure(**self.theme.button_kwargs(primary=True))

    def refresh_connection_status(self) -> None:
        state = self.session.connection
        if state.connected:
            text = f"Connected: {state.username}@{state.host}"
            self.connection_label.configure(text=text, text_color=self.theme.colors.success)
        else:
            self.connection_label.configure(text="Not connected", text_color=self.theme.colors.warning)
        for page in self.pages.values():
            if hasattr(page, "on_session_update"):
                page.on_session_update()

    def process_task_events(self) -> None:
        while not self.tasks.events.empty():
            event: TaskEvent = self.tasks.events.get()
            if event.kind == "start":
                self.session.task.running = True
                self.session.task.name = event.name
                self.session.task.progress = 0
                self.task_label.configure(text=event.name)
                self.progress.set(0)
                self.logger.info(f"Task started: {event.name}")
            elif event.kind == "progress":
                value, message = event.payload
                self.session.task.progress = float(value)
                self.progress.set(max(0.0, min(1.0, float(value))))
                if message:
                    self.task_label.configure(text=f"{event.name}: {message}")
            elif event.kind == "success":
                result, callback = event.payload
                if callback:
                    callback(result)
            elif event.kind == "error":
                exc, callback = event.payload
                self.logger.error(f"{event.name} failed: {exc}")
                self.show_toast(f"{event.name} failed: {exc}", "error")
                if callback:
                    callback(exc)
            elif event.kind == "finish":
                self.session.task.running = False
                self.session.task.name = "Idle"
                self.session.task.progress = 0
                self.task_label.configure(text="Idle")
                self.progress.set(0)
                self.logger.info(f"Task finished: {event.name}")
        self.after(100, self.process_task_events)

    def drain_logs(self) -> None:
        while not self.logger.queue.empty():
            self.logger.queue.get()
        self.after(150, self.drain_logs)

    def switch_theme(self, mode: str) -> None:
        old_colors = self.theme.colors
        self.settings.theme = mode
        self.theme.set_mode(mode)
        self.save_settings()
        self.apply_theme(old_colors)
        self.show_toast(f"{mode} theme applied.", "info")

    def apply_theme(self, old_colors=None) -> None:
        colors = self.theme.colors
        self.configure(fg_color=colors.bg)
        self.header.configure(fg_color=colors.panel)
        self.nav.configure(fg_color=colors.panel)
        self.workspace.configure(fg_color=colors.bg)
        self.bottom.configure(fg_color=colors.panel)
        self.task_label.configure(text_color=colors.text_muted)
        self.theme_switch.configure(selected_color=colors.accent, selected_hover_color=colors.accent_hover)
        self._refresh_widget_tree(self, old_colors)
        for name, button in self.nav_buttons.items():
            button.configure(**self.theme.button_kwargs(primary=(name == self.current_page)))
        self.refresh_connection_status()
        for page in self.pages.values():
            if hasattr(page, "on_theme_update"):
                page.on_theme_update()

    def _refresh_widget_tree(self, widget, old_colors=None) -> None:
        if hasattr(widget, "refresh_theme"):
            try:
                widget.refresh_theme()
            except Exception:
                pass
        colors = self.theme.colors
        try:
            if isinstance(widget, ctk.CTkEntry):
                widget.configure(fg_color=colors.input_bg, border_color=colors.border, text_color=colors.text)
            elif isinstance(widget, ctk.CTkTextbox):
                widget.configure(fg_color=colors.input_bg, text_color=colors.text)
            elif isinstance(widget, ctk.CTkButton) and old_colors is not None:
                current = getattr(widget, "_fg_color", "")
                primary = self._matches_color(current, old_colors.accent)
                widget.configure(**self.theme.button_kwargs(primary=primary))
            elif isinstance(widget, ctk.CTkLabel):
                current = getattr(widget, "_text_color", "")
                if old_colors is None or self._matches_color(current, old_colors.text_muted):
                    widget.configure(text_color=colors.text_muted)
                elif self._matches_color(current, old_colors.text):
                    widget.configure(text_color=colors.text)
            elif isinstance(widget, ctk.CTkFrame):
                current = getattr(widget, "_fg_color", "")
                if old_colors is not None:
                    if self._matches_color(current, old_colors.panel):
                        widget.configure(fg_color=colors.panel)
                    elif self._matches_color(current, old_colors.panel_alt):
                        widget.configure(fg_color=colors.panel_alt)
                    elif self._matches_color(current, old_colors.bg):
                        widget.configure(fg_color=colors.bg)
        except Exception:
            pass
        for child in widget.winfo_children():
            self._refresh_widget_tree(child, old_colors)

    @staticmethod
    def _matches_color(value, color: str) -> bool:
        if isinstance(value, str):
            return value.lower() == color.lower()
        if isinstance(value, (tuple, list)):
            return any(isinstance(item, str) and item.lower() == color.lower() for item in value)
        return False

    def show_toast(self, message: str, kind: str = "info") -> None:
        if self._toast_after_id:
            self.after_cancel(self._toast_after_id)
            self._toast_after_id = None
        if self._toast_widget:
            self._toast_widget.destroy()
            self._toast_widget = None
        colors = self.theme.colors
        fg = {
            "success": colors.success,
            "warning": colors.warning,
            "error": colors.error,
            "info": colors.accent,
        }.get(kind, colors.accent)
        toast = ctk.CTkFrame(self.workspace, fg_color=fg, corner_radius=8)
        ctk.CTkLabel(toast, text=message, text_color="#FFFFFF", wraplength=720).pack(padx=16, pady=9)
        toast.place(relx=0.5, y=14, anchor="n")
        toast.lift()
        self._toast_widget = toast
        self._toast_after_id = self.after(5000, self._dismiss_toast)

    def _dismiss_toast(self) -> None:
        if self._toast_widget:
            self._toast_widget.destroy()
            self._toast_widget = None
        self._toast_after_id = None

    def _submit_shortcut(self, _event=None):
        if self.current_page == "Submit Job":
            page = self.pages.get("Submit Job")
            if hasattr(page, "submit_job"):
                page.submit_job()
                return "break"
        return None

    def _refresh_shortcut(self, _event=None):
        if self.current_page == "Job Queue":
            page = self.pages.get("Job Queue")
            if hasattr(page, "refresh"):
                page.refresh()
                return "break"
        return None

    def save_settings(self) -> None:
        try:
            self.settings.window_geometry = self.geometry()
            self.settings_store.save(self.settings)
        except Exception as exc:
            self.logger.error(f"Could not save settings: {exc}")

    def open_path(self, path: Path) -> None:
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", "", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            self.logger.error(f"Could not open {path}: {exc}")

    def on_close(self) -> None:
        self.save_settings()
        self.tasks.shutdown()
        self.destroy()
