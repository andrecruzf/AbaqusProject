from __future__ import annotations

from dataclasses import dataclass

import customtkinter as ctk


@dataclass(frozen=True)
class ThemeColors:
    bg: str
    panel: str
    panel_alt: str
    border: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    success: str
    warning: str
    error: str
    input_bg: str


class ThemeManager:
    dark = ThemeColors(
        bg="#111418",
        panel="#171B21",
        panel_alt="#1D232B",
        border="#2A323C",
        text="#E6EAF0",
        text_muted="#9BA6B2",
        accent="#007A96",
        accent_hover="#0A8EAE",
        success="#3BA55D",
        warning="#D19A3A",
        error="#D85757",
        input_bg="#20262E",
    )
    light = ThemeColors(
        bg="#F4F6F8",
        panel="#FFFFFF",
        panel_alt="#EDF1F5",
        border="#D3D9E0",
        text="#101418",
        text_muted="#5A6673",
        accent="#007A96",
        accent_hover="#086F86",
        success="#237A3B",
        warning="#9A6B14",
        error="#B3261E",
        input_bg="#FFFFFF",
    )

    def __init__(self, mode: str = "Dark") -> None:
        self.mode = mode if mode in ("Dark", "Light") else "Dark"
        ctk.set_appearance_mode(self.mode)
        ctk.set_default_color_theme("blue")

    @property
    def colors(self) -> ThemeColors:
        return self.dark if self.mode == "Dark" else self.light

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in ("Dark", "Light") else "Dark"
        ctk.set_appearance_mode(self.mode)

    def frame_kwargs(self, alt: bool = False) -> dict[str, str | int]:
        c = self.colors
        return {
            "fg_color": c.panel_alt if alt else c.panel,
            "border_color": c.border,
            "border_width": 1,
            "corner_radius": 8,
        }

    def button_kwargs(self, primary: bool = False) -> dict[str, str | int]:
        c = self.colors
        if primary:
            return {
                "fg_color": c.accent,
                "hover_color": c.accent_hover,
                "text_color": "#FFFFFF",
                "corner_radius": 6,
            }
        return {
            "fg_color": c.panel_alt,
            "hover_color": c.border,
            "text_color": c.text,
            "corner_radius": 6,
            "border_color": c.border,
            "border_width": 1,
        }

