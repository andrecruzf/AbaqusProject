from __future__ import annotations

import customtkinter as ctk

from app.constants import EULER_HOST
from services.euler import EulerService

from .base import BasePage


class ConnectionPage(BasePage):
    title = "Connection"

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        settings = self.session.settings
        self.username_var = ctk.StringVar(value=settings.remembered_username if settings.remember_username else "")
        self.host_var = ctk.StringVar(value=settings.euler_host)
        self.remember_var = ctk.BooleanVar(value=settings.remember_username)
        self.key_only_var = ctk.BooleanVar(value=False)
        self.status_var = ctk.StringVar(value="Not connected")
        self.last_var = ctk.StringVar(value="Never")

        header = ctk.CTkFrame(self, **self.theme.frame_kwargs())
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="Euler Connection", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 2)
        )
        ctk.CTkLabel(
            header,
            text=(
                "Uses the system ssh command. Passwords are never stored; if ETH password or 2FA is needed, "
                "complete the prompt in the terminal that launched this app."
            ),
            text_color=self.theme.colors.text_muted,
            wraplength=900,
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 12), columnspan=2)

        form = ctk.CTkFrame(self, **self.theme.frame_kwargs())
        form.grid(row=1, column=0, sticky="nsew", padx=14, pady=8)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="ETH username").grid(row=0, column=0, sticky="w", padx=14, pady=(18, 6))
        ctk.CTkEntry(form, textvariable=self.username_var, width=260).grid(
            row=0, column=1, sticky="w", padx=14, pady=(18, 6)
        )
        ctk.CTkLabel(form, text="Remote host").grid(row=1, column=0, sticky="w", padx=14, pady=6)
        ctk.CTkEntry(form, textvariable=self.host_var, width=260).grid(row=1, column=1, sticky="w", padx=14, pady=6)
        ctk.CTkCheckBox(form, text="Remember username locally", variable=self.remember_var).grid(
            row=2, column=1, sticky="w", padx=14, pady=6
        )
        ctk.CTkCheckBox(
            form,
            text="Key-only check (no password prompt)",
            variable=self.key_only_var,
        ).grid(row=3, column=1, sticky="w", padx=14, pady=6)
        ctk.CTkButton(
            form,
            text="Verify connection",
            command=self.verify,
            **self.theme.button_kwargs(primary=True),
        ).grid(row=4, column=1, sticky="w", padx=14, pady=(14, 8))

        status = ctk.CTkFrame(form, **self.theme.frame_kwargs(alt=True))
        status.grid(row=5, column=0, columnspan=2, sticky="ew", padx=14, pady=(18, 14))
        status.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(status, text="Status", text_color=self.theme.colors.text_muted).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        ctk.CTkLabel(status, textvariable=self.status_var).grid(row=0, column=1, sticky="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(status, text="Last success", text_color=self.theme.colors.text_muted).grid(
            row=1, column=0, sticky="w", padx=12, pady=(4, 10)
        )
        ctk.CTkLabel(status, textvariable=self.last_var).grid(row=1, column=1, sticky="w", padx=12, pady=(4, 10))
        self.on_session_update()

    def verify(self) -> None:
        username = self.username_var.get().strip()
        host = self.host_var.get().strip() or EULER_HOST
        self.session.settings.euler_host = host

        def task(ctx):
            ctx.log(f"Verifying SSH connection to {username}@{host}")
            return EulerService(host).verify_connection(username, key_only=bool(self.key_only_var.get()))

        def success(result):
            if result.ok:
                self.session.set_connected(result.username, result.host)
                self.status_var.set(result.message)
                self.session.logger.info(result.message)
                if self.remember_var.get():
                    self.session.settings.remembered_username = result.username
                self.session.settings.remember_username = bool(self.remember_var.get())
                self.app.save_settings()
            else:
                self.session.set_disconnected(result.message)
                self.status_var.set(result.message)
                self.session.logger.error(result.message)
            self.app.refresh_connection_status()
            self.on_session_update()

        self.app.tasks.submit("Verify Euler connection", task, on_success=success)

    def on_session_update(self) -> None:
        state = self.session.connection
        if state.connected:
            self.status_var.set(f"Connected as {state.username}@{state.host}")
            if state.last_success:
                self.last_var.set(f"{state.last_success:%Y-%m-%d %H:%M:%S}")
        elif state.last_error:
            self.status_var.set(state.last_error)
        else:
            self.status_var.set("Not connected")
