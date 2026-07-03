from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

from services.euler import EulerService

from .base import BasePage


class ModernQueueTable(ctk.CTkFrame):
    columns = [
        ("JOBID", "JOBID", 1, 95),
        ("ST", "ST", 0, 58),
        ("NAME", "NAME", 4, 280),
        ("PARTITION", "PARTITION", 1, 95),
        ("TIME", "TIME", 1, 90),
        ("LIMIT", "TIME_LIMIT", 1, 90),
        ("NODES", "NODES", 0, 62),
        ("PROGRESS", "PROGRESS", 2, 180),
        ("ETA", "ETA", 2, 150),
        ("NODELIST / REASON", "NODELIST(REASON)", 2, 210),
    ]

    def __init__(self, master, theme) -> None:
        super().__init__(master, **theme.frame_kwargs())
        self.theme = theme
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.header = ctk.CTkFrame(self, fg_color=theme.colors.panel_alt, corner_radius=6)
        self.header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        self.rows = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.rows.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.rows.grid_columnconfigure(0, weight=1)
        self._build_header()

    def _build_header(self) -> None:
        for col, (label, _key, weight, width) in enumerate(self.columns):
            self.header.grid_columnconfigure(col, weight=weight, minsize=width)
            ctk.CTkLabel(
                self.header,
                text=label,
                text_color=self.theme.colors.text_muted,
                font=ctk.CTkFont(size=11, weight="bold"),
                anchor="w",
            ).grid(row=0, column=col, sticky="ew", padx=8, pady=8)

    def set_rows(self, rows: list[dict[str, str]]) -> None:
        for child in self.rows.winfo_children():
            child.destroy()
        if not rows:
            ctk.CTkLabel(
                self.rows,
                text="No jobs in queue.",
                text_color=self.theme.colors.text_muted,
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=20)
            return
        for idx, row in enumerate(rows):
            self._add_row(idx, row)

    def _add_row(self, idx: int, row: dict[str, str]) -> None:
        fg = self.theme.colors.panel_alt if idx % 2 == 0 else self.theme.colors.panel
        item = ctk.CTkFrame(self.rows, fg_color=fg, border_color=self.theme.colors.border, border_width=1, corner_radius=6)
        item.grid(row=idx, column=0, sticky="ew", pady=3)
        for col, (_label, _key, weight, width) in enumerate(self.columns):
            item.grid_columnconfigure(col, weight=weight, minsize=width)
        for col, (_label, key, _weight, _width) in enumerate(self.columns):
            if key == "ST":
                self._status_cell(item, row.get(key, ""), col)
            elif key == "PROGRESS":
                self._progress_cell(item, row, col)
            elif key == "NAME":
                ctk.CTkLabel(item, text=row.get(key, ""), anchor="w", font=ctk.CTkFont(size=12, weight="bold")).grid(
                    row=0, column=col, sticky="ew", padx=8, pady=9
                )
            else:
                ctk.CTkLabel(item, text=row.get(key, ""), anchor="w", text_color=self.theme.colors.text).grid(
                    row=0, column=col, sticky="ew", padx=8, pady=9
                )

    def _status_cell(self, parent: ctk.CTkFrame, state: str, col: int) -> None:
        color = {
            "R": self.theme.colors.success,
            "PD": self.theme.colors.warning,
            "F": self.theme.colors.error,
            "CG": self.theme.colors.accent,
            "CD": self.theme.colors.accent,
        }.get(state, self.theme.colors.border)
        ctk.CTkLabel(
            parent,
            text=state or "-",
            fg_color=color,
            text_color="#FFFFFF",
            corner_radius=10,
            width=42,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=col, sticky="w", padx=8, pady=8)

    def _progress_cell(self, parent: ctk.CTkFrame, row: dict[str, str], col: int) -> None:
        pct_text = row.get("PROGRESS", "")
        pct = self._parse_pct(pct_text)
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=0, column=col, sticky="ew", padx=8, pady=6)
        cell.grid_columnconfigure(0, weight=1)
        bar = ctk.CTkProgressBar(cell, height=8)
        bar.grid(row=0, column=0, sticky="ew")
        bar.set(pct / 100.0)
        text = pct_text or ("pre-solve" if row.get("ST") == "R" and row.get("NAME", "").startswith(("Naka", "Marc", "Pip")) else "-")
        ctk.CTkLabel(cell, text=text, text_color=self.theme.colors.text_muted, font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )

    @staticmethod
    def _parse_pct(value: str) -> float:
        try:
            return max(0.0, min(100.0, float(str(value).strip().rstrip("%"))))
        except ValueError:
            return 0.0


class JobQueuePage(BasePage):
    title = "Job Queue"

    columns = ["JOBID", "PARTITION", "NAME", "USER", "ST", "TIME", "TIME_LIMIT", "NODES", "PROGRESS", "ETA", "NODELIST(REASON)"]

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.filter_var = ctk.StringVar(value="All")
        self.search_var = ctk.StringVar(value="")
        self._refresh_after_id = None
        self._sta_last_refresh: datetime | None = None

        controls = ctk.CTkFrame(self, **self.theme.frame_kwargs())
        controls.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        controls.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(
            controls,
            text="Auto-refresh every 30 s",
            text_color=self.theme.colors.text_muted,
        ).grid(row=0, column=0, padx=12, pady=10, sticky="w")
        ctk.CTkOptionMenu(controls, variable=self.filter_var, values=["All", "Running", "Pending", "Completed/Other"], command=lambda _: self.populate()).grid(
            row=0, column=1, padx=10, pady=10
        )
        ctk.CTkEntry(controls, textvariable=self.search_var, placeholder_text="Search jobs").grid(
            row=0, column=3, padx=10, pady=10, sticky="ew"
        )
        self.search_var.trace_add("write", lambda *_: self.populate())

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        queue_section = ctk.CTkFrame(body, **self.theme.frame_kwargs())
        queue_section.grid(row=0, column=0, sticky="nsew")
        queue_section.grid_columnconfigure(0, weight=1)
        queue_section.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(queue_section, text="Queue Output", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4)
        )
        self.queue_meta = ctk.CTkLabel(queue_section, text="", text_color=self.theme.colors.text_muted)
        self.queue_meta.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))
        self.table = ModernQueueTable(queue_section, self.theme)
        self.table.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.schedule_refresh()

    def on_show(self) -> None:
        self.populate()
        self.refresh()
        self.schedule_refresh()

    def schedule_refresh(self) -> None:
        if self._refresh_after_id:
            self.after_cancel(self._refresh_after_id)
            self._refresh_after_id = None
        self._refresh_after_id = self.after(30_000, self._auto_refresh)

    def _auto_refresh(self) -> None:
        self.refresh()
        self.schedule_refresh()

    def refresh(self) -> None:
        username = self.session.connection.username or self.session.settings.remembered_username
        host = self.session.connection.host or self.session.settings.euler_host

        def task(ctx):
            ctx.log(f"Fetching Euler queue for {username}@{host}")
            service = EulerService(host)
            rows = service.fetch_queue(username)
            return service.enrich_progress(username, rows)

        def success(rows):
            self.session.cached_jobs = rows
            self._sta_last_refresh = datetime.now()
            self.populate()
            self.session.logger.info(f"Fetched {len(rows)} queue rows.")

        self.app.tasks.submit("Fetch Euler queue", task, on_success=success)

    def populate(self) -> None:
        rows = self.session.cached_jobs
        query = self.search_var.get().lower().strip()
        filter_value = self.filter_var.get()
        filtered = []
        for row in rows:
            state = row.get("ST", "")
            if filter_value == "Running" and state != "R":
                continue
            if filter_value == "Pending" and state != "PD":
                continue
            if filter_value == "Completed/Other" and state in {"R", "PD"}:
                continue
            values = [row.get(col, "") for col in self.columns]
            if query and query not in " ".join(values).lower():
                continue
            filtered.append(row)
        stamp = self._sta_last_refresh.strftime("%H:%M:%S") if self._sta_last_refresh else "not fetched"
        self.queue_meta.configure(text=f"{len(filtered)} shown / {len(rows)} total · .sta last fetched: {stamp}")
        self.table.set_rows(filtered)
