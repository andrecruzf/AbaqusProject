from __future__ import annotations

import customtkinter as ctk


class BasePage(ctk.CTkFrame):
    title = "Page"

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.session = app.session
        self.theme = app.theme

    def on_show(self) -> None:
        pass

    def on_session_update(self) -> None:
        pass

