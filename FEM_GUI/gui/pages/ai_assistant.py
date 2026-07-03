from __future__ import annotations

import customtkinter as ctk

from services.ai import AIService

from .base import BasePage


class AIAssistantPage(BasePage):
    title = "AI Assistant"

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, **self.theme.frame_kwargs())
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        top.grid_columnconfigure(1, weight=1)
        self.api_var = ctk.StringVar(value="")
        ctk.CTkLabel(top, text="Anthropic API key").grid(row=0, column=0, padx=12, pady=12)
        ctk.CTkEntry(top, textvariable=self.api_var, show="*", placeholder_text="Not stored").grid(
            row=0, column=1, sticky="ew", padx=12, pady=12
        )
        body = ctk.CTkFrame(self, **self.theme.frame_kwargs())
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.chat = ctk.CTkTextbox(body, fg_color=self.theme.colors.input_bg)
        self.chat.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))
        bottom = ctk.CTkFrame(body, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        bottom.grid_columnconfigure(0, weight=1)
        self.prompt = ctk.CTkTextbox(bottom, height=70, fg_color=self.theme.colors.input_bg)
        self.prompt.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(bottom, text="Send", command=self.send, **self.theme.button_kwargs(primary=True)).grid(
            row=0, column=1, sticky="ns"
        )
        self.refresh_chat()

    def refresh_chat(self) -> None:
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        for message in self.session.ai_messages:
            self.chat.insert("end", f"{message['role'].upper()}: {message['content']}\n\n")
        self.chat.configure(state="disabled")

    def send(self) -> None:
        key = self.api_var.get().strip()
        content = self.prompt.get("1.0", "end").strip()
        if not key or not content:
            return
        self.session.ai_messages.append({"role": "user", "content": content})
        self.prompt.delete("1.0", "end")
        self.refresh_chat()

        state = self.session.connection
        system = (
            "You are an Abaqus expert helping with the local FEM desktop application.\n"
            f"Euler user: {state.username or 'not connected'}\n"
            f"Euler host: {state.host}\n"
        )

        def task(ctx):
            ctx.log("Sending AI assistant request")
            return AIService().send(key, self.session.ai_messages, system)

        def success(reply: str):
            self.session.ai_messages.append({"role": "assistant", "content": reply})
            self.refresh_chat()

        self.app.tasks.submit("AI request", task, on_success=success)

