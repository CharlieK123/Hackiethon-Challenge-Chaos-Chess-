from __future__ import annotations

import pygame


def load_font(size: int, *, bold: bool = False) -> pygame.font.Font:
    """Return a readable system font with a sensible fallback."""

    font = pygame.font.SysFont("segoeui", size, bold=bold)
    if font is not None:
        return font
    return pygame.font.Font(None, size)
