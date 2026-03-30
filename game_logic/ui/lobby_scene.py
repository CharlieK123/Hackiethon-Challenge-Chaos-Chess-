from __future__ import annotations

import os
from dataclasses import dataclass

import pygame

from chaos_chess.config import (
    ACCENT_COLOR,
    BACKGROUND_COLOR,
    BOARD_MARGIN,
    BUTTON_ACTIVE_COLOR,
    BUTTON_HOVER_COLOR,
    CARD_COLOR,
    PANEL_BORDER_COLOR,
    PANEL_COLOR,
    SUBTLE_TEXT_COLOR,
    TEXT_COLOR,
    WARNING_COLOR,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from chaos_chess.game.types import GameMode
from chaos_chess.infra.asset_loader import load_font


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

@dataclass
class LobbyResult:
    mode: GameMode
    initial_time_ms: int       # 0 = Unlimited
    chaos_mode: str            # "disabled" | "local" | "hybrid"
    chaos_frequency: str       # "calm" | "normal" | "mayhem"
    bot_difficulty: str        # "simple" | "stockfish_easy" | "stockfish_hard"
    custom_chaos_prompt: str   # empty string if not set or not applicable


# ---------------------------------------------------------------------------
# Static option tables
# ---------------------------------------------------------------------------

_MODE_OPTIONS = [
    ("vs Bot",      GameMode.HUMAN_VS_BOT,
     "Play against the built-in chess engine. Stockfish is used if available, "
     "otherwise a simple material bot."),
    ("vs Friend",   GameMode.LOCAL_PVP,
     "Local two-player game. Both players share the keyboard and mouse."),
    ("Bot vs Bot",  GameMode.BOT_VS_BOT,
     "Watch two bots play each other. You observe only. Press F to adjust speed."),
]

_TIME_OPTIONS = [
    ("1 min",      60_000),
    ("3 min",     180_000),
    ("5 min",     300_000),
    ("10 min",    600_000),
    ("Unlimited",       0),
]
_TIME_DESCRIPTION = (
    "Set the starting clock time for each player. "
    "Chaos escalates faster when time is running low."
)

_CHAOS_OPTIONS = [
    ("Disabled",              "disabled",
     "No chaos events. Standard chess rules apply."),
    ("Local Only",            "local",
     "Chaos events are generated locally. No API key required."),
    ("Hybrid (Claude + Local)", "hybrid",
     "Claude designs chaos events when an API key is available, with local fallback."),
]

_FREQ_OPTIONS = [
    ("Calm (every 5–7 turns)",   "calm",
     "How often chaos events fire. Escalating clock pressure will increase frequency "
     "further regardless of this setting."),
    ("Normal (every 3–5 turns)", "normal",
     "How often chaos events fire. Escalating clock pressure will increase frequency "
     "further regardless of this setting."),
    ("Mayhem (every 1–3 turns)", "mayhem",
     "How often chaos events fire. Escalating clock pressure will increase frequency "
     "further regardless of this setting."),
]

_DIFF_OPTIONS = [
    ("Simple",         "simple",
     "One-ply material bot. Always available regardless of installed engines."),
    ("Stockfish Easy", "stockfish_easy",
     "Stockfish at shorter search time. Falls back to Simple if Stockfish is not installed."),
    ("Stockfish Hard", "stockfish_hard",
     "Stockfish at longer search depth. Falls back to Simple if Stockfish is not installed."),
]
_DIFF_DESCRIPTION = (
    "Simple uses a one-ply material bot. Stockfish difficulty controls search depth. "
    "Falls back to Simple if Stockfish is not installed."
)

_PROMPT_DESCRIPTION = (
    "Give Claude a custom personality or bias for chaos event generation. "
    "This is appended to Claude's system prompt. Leave blank for default behaviour."
)
_PROMPT_LOCAL_DESCRIPTION = "Custom prompts require Hybrid mode."
_PROMPT_PLACEHOLDER = (
    "e.g. 'favour events that punish the winning side'"
)
_PROMPT_MAX_LEN = 200

_DEFAULT_DESCRIPTION = "Hover over a setting to see its description."

# Layout constants
_M = BOARD_MARGIN          # 20 px outer margin
_GAP = 8                   # gap between panels
_HEADER_H = 34             # panel title bar height
_OPT_H = 30               # height of each option row
_PAD_B = 10               # bottom padding inside panel
_TITLE_AREA_H = 78        # height reserved for lobby title
_BUTTON_AREA_H = 68       # height reserved for start button + warning


def _panel_height(n_options: int) -> int:
    return _HEADER_H + n_options * _OPT_H + _PAD_B


def _option_rects(panel_rect: pygame.Rect, n: int) -> list[pygame.Rect]:
    rects: list[pygame.Rect] = []
    y = panel_rect.top + _HEADER_H
    for _ in range(n):
        rects.append(pygame.Rect(panel_rect.left + 4, y, panel_rect.width - 8, _OPT_H))
        y += _OPT_H
    return rects


# ---------------------------------------------------------------------------
# LobbyScene
# ---------------------------------------------------------------------------

class LobbyScene:
    """Full-screen lobby for configuring a Chaos Chess match."""

    def __init__(self) -> None:
        self._title_font   = load_font(40, bold=True)
        self._subtitle_font = load_font(17)
        self._section_font = load_font(16, bold=True)
        self._body_font    = load_font(15)
        self._small_font   = load_font(13)
        self._button_font  = load_font(17, bold=True)

        # Default selections
        self._mode_idx:  int = 0   # vs Bot
        self._time_idx:  int = 2   # 5 min
        self._chaos_idx: int = 2   # Hybrid
        self._freq_idx:  int = 1   # Normal
        self._diff_idx:  int = 0   # Simple

        self._custom_prompt: str  = ""
        self._text_active:   bool = False
        self._hover_desc:    str  = _DEFAULT_DESCRIPTION

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._api_key_available = bool(api_key and api_key.strip())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, surface: pygame.Surface) -> LobbyResult | None:
        """Block until the player starts the game or quits.

        Returns LobbyResult on Start, None if the player pressed Escape or closed
        the window.
        """
        pygame.key.set_repeat(400, 30)
        frame_clock = pygame.time.Clock()

        while True:
            frame_clock.tick(60)
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                outcome = self._handle_event(event, mouse_pos)
                if outcome == "quit":
                    pygame.key.set_repeat(0, 0)
                    return None
                if isinstance(outcome, LobbyResult):
                    pygame.key.set_repeat(0, 0)
                    return outcome

            self._update_hover(mouse_pos)
            self._render(surface, mouse_pos)
            pygame.display.flip()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _handle_event(self, event: pygame.event.Event, mouse_pos) -> object:
        if event.type == pygame.QUIT:
            return "quit"

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self._text_active:
                    self._text_active = False
                else:
                    return "quit"
            elif self._text_active:
                self._handle_text_key(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._handle_click(mouse_pos)

        return None

    def _handle_text_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_BACKSPACE:
            self._custom_prompt = self._custom_prompt[:-1]
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._text_active = False
        elif event.unicode and event.unicode.isprintable():
            if len(self._custom_prompt) < _PROMPT_MAX_LEN:
                self._custom_prompt += event.unicode

    def _handle_click(self, pos) -> object:
        layout = self._layout()

        # Text input activation / deactivation
        if layout["prompt_visible"]:
            if layout["prompt_input_rect"].collidepoint(pos):
                chaos_mode = _CHAOS_OPTIONS[self._chaos_idx][1]
                if chaos_mode == "hybrid":
                    self._text_active = True
                    return None
            else:
                self._text_active = False
        else:
            self._text_active = False

        # Option panels
        for i, rect in enumerate(layout["mode_rects"]):
            if rect.collidepoint(pos):
                self._mode_idx = i
                return None

        for i, rect in enumerate(layout["time_rects"]):
            if rect.collidepoint(pos):
                self._time_idx = i
                return None

        for i, rect in enumerate(layout["chaos_rects"]):
            if rect.collidepoint(pos):
                self._chaos_idx = i
                return None

        if layout["freq_visible"]:
            for i, rect in enumerate(layout["freq_rects"]):
                if rect.collidepoint(pos):
                    self._freq_idx = i
                    return None

        if layout["diff_visible"]:
            for i, rect in enumerate(layout["diff_rects"]):
                if rect.collidepoint(pos):
                    self._diff_idx = i
                    return None

        if layout["start_rect"].collidepoint(pos):
            return self._build_result()

        return None

    # ------------------------------------------------------------------
    # Hover / description
    # ------------------------------------------------------------------

    def _update_hover(self, pos) -> None:
        layout = self._layout()
        desc = ""

        for i, rect in enumerate(layout["mode_rects"]):
            if rect.collidepoint(pos):
                desc = _MODE_OPTIONS[i][2]
                break

        if not desc:
            for rect in layout["time_rects"]:
                if rect.collidepoint(pos):
                    desc = _TIME_DESCRIPTION
                    break

        if not desc:
            for i, rect in enumerate(layout["chaos_rects"]):
                if rect.collidepoint(pos):
                    desc = _CHAOS_OPTIONS[i][2]
                    break

        if not desc and layout["freq_visible"]:
            for i, rect in enumerate(layout["freq_rects"]):
                if rect.collidepoint(pos):
                    desc = _FREQ_OPTIONS[i][2]
                    break

        if not desc and layout["diff_visible"]:
            for rect in layout["diff_rects"]:
                if rect.collidepoint(pos):
                    desc = _DIFF_DESCRIPTION
                    break

        if not desc and layout["prompt_visible"]:
            chaos_mode = _CHAOS_OPTIONS[self._chaos_idx][1]
            if layout["prompt_input_rect"].collidepoint(pos):
                desc = _PROMPT_LOCAL_DESCRIPTION if chaos_mode == "local" else _PROMPT_DESCRIPTION

        if desc:
            self._hover_desc = desc

    # ------------------------------------------------------------------
    # Layout computation
    # ------------------------------------------------------------------

    def _layout(self) -> dict:
        chaos_mode = _CHAOS_OPTIONS[self._chaos_idx][1]
        game_mode  = _MODE_OPTIONS[self._mode_idx][1]

        freq_visible   = chaos_mode != "disabled"
        prompt_visible = chaos_mode != "disabled"
        diff_visible   = game_mode != GameMode.LOCAL_PVP

        col_w   = (WINDOW_WIDTH - 3 * _M) // 2
        left_x  = _M
        right_x = _M + col_w + _M
        top_y   = _TITLE_AREA_H

        mode_h  = _panel_height(len(_MODE_OPTIONS))
        time_h  = _panel_height(len(_TIME_OPTIONS))
        diff_h  = _panel_height(len(_DIFF_OPTIONS))
        chaos_h = _panel_height(len(_CHAOS_OPTIONS))
        freq_h  = _panel_height(len(_FREQ_OPTIONS))
        prompt_h = _HEADER_H + 40 + _PAD_B + 18  # title + input + padding + counter

        mode_rect  = pygame.Rect(left_x, top_y,                   col_w, mode_h)
        time_rect  = pygame.Rect(left_x, mode_rect.bottom + _GAP, col_w, time_h)
        diff_rect  = pygame.Rect(left_x, time_rect.bottom + _GAP, col_w, diff_h)

        chaos_rect = pygame.Rect(right_x, top_y,                    col_w, chaos_h)
        freq_y     = chaos_rect.bottom + _GAP
        freq_rect  = pygame.Rect(right_x, freq_y,                   col_w, freq_h)

        prompt_y = (freq_rect.bottom if freq_visible else chaos_rect.bottom) + _GAP
        prompt_rect = pygame.Rect(right_x, prompt_y, col_w, prompt_h)
        prompt_input_rect = pygame.Rect(
            prompt_rect.left + 8,
            prompt_rect.top + _HEADER_H,
            prompt_rect.width - 16,
            36,
        )

        desc_y = (prompt_rect.bottom if prompt_visible else
                  (freq_rect.bottom if freq_visible else chaos_rect.bottom)) + _GAP
        desc_h = max(50, WINDOW_HEIGHT - _BUTTON_AREA_H - desc_y)
        desc_rect = pygame.Rect(right_x, desc_y, col_w, desc_h)

        btn_w = 200
        btn_h = 42
        start_rect = pygame.Rect(
            (WINDOW_WIDTH - btn_w) // 2,
            WINDOW_HEIGHT - _BUTTON_AREA_H + 10,
            btn_w, btn_h,
        )

        return {
            "mode_panel":   mode_rect,
            "mode_rects":   _option_rects(mode_rect,  len(_MODE_OPTIONS)),
            "time_panel":   time_rect,
            "time_rects":   _option_rects(time_rect,  len(_TIME_OPTIONS)),
            "diff_panel":   diff_rect,
            "diff_rects":   _option_rects(diff_rect,  len(_DIFF_OPTIONS)),
            "diff_visible": diff_visible,
            "chaos_panel":  chaos_rect,
            "chaos_rects":  _option_rects(chaos_rect, len(_CHAOS_OPTIONS)),
            "freq_panel":   freq_rect,
            "freq_rects":   _option_rects(freq_rect,  len(_FREQ_OPTIONS)),
            "freq_visible": freq_visible,
            "prompt_panel":      prompt_rect,
            "prompt_input_rect": prompt_input_rect,
            "prompt_visible":    prompt_visible,
            "desc_panel":   desc_rect,
            "start_rect":   start_rect,
        }

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self, surface: pygame.Surface, mouse_pos) -> None:
        surface.fill(BACKGROUND_COLOR)
        layout = self._layout()
        chaos_mode = _CHAOS_OPTIONS[self._chaos_idx][1]

        self._draw_title(surface)

        # Left column
        self._draw_option_panel(
            surface, layout["mode_panel"], layout["mode_rects"],
            "Game Mode", [o[0] for o in _MODE_OPTIONS], self._mode_idx, mouse_pos,
        )
        self._draw_option_panel(
            surface, layout["time_panel"], layout["time_rects"],
            "Time Control", [o[0] for o in _TIME_OPTIONS], self._time_idx, mouse_pos,
        )
        if layout["diff_visible"]:
            self._draw_option_panel(
                surface, layout["diff_panel"], layout["diff_rects"],
                "Bot Difficulty", [o[0] for o in _DIFF_OPTIONS], self._diff_idx, mouse_pos,
            )

        # Right column
        self._draw_option_panel(
            surface, layout["chaos_panel"], layout["chaos_rects"],
            "Chaos Mode", [o[0] for o in _CHAOS_OPTIONS], self._chaos_idx, mouse_pos,
        )
        if layout["freq_visible"]:
            self._draw_option_panel(
                surface, layout["freq_panel"], layout["freq_rects"],
                "Chaos Frequency", [o[0] for o in _FREQ_OPTIONS], self._freq_idx, mouse_pos,
            )
        if layout["prompt_visible"]:
            self._draw_prompt_panel(
                surface, layout["prompt_panel"], layout["prompt_input_rect"], chaos_mode,
            )
        self._draw_description_panel(surface, layout["desc_panel"])

        self._draw_start_button(surface, layout["start_rect"], mouse_pos, chaos_mode)

    def _draw_title(self, surface: pygame.Surface) -> None:
        title = self._title_font.render("Chaos Chess", True, TEXT_COLOR)
        surface.blit(title, title.get_rect(centerx=WINDOW_WIDTH // 2, top=14))

        sub = self._subtitle_font.render("Configure your match", True, SUBTLE_TEXT_COLOR)
        surface.blit(sub, sub.get_rect(centerx=WINDOW_WIDTH // 2, top=56))

    def _draw_option_panel(
        self,
        surface: pygame.Surface,
        panel_rect: pygame.Rect,
        option_rects: list[pygame.Rect],
        title: str,
        labels: list[str],
        selected_idx: int,
        mouse_pos,
    ) -> None:
        pygame.draw.rect(surface, PANEL_COLOR, panel_rect, border_radius=12)
        pygame.draw.rect(surface, PANEL_BORDER_COLOR, panel_rect, width=1, border_radius=12)

        t = self._section_font.render(title, True, TEXT_COLOR)
        surface.blit(t, (panel_rect.left + 12, panel_rect.top + 9))

        for i, (rect, label) in enumerate(zip(option_rects, labels)):
            selected = i == selected_idx
            hovered  = rect.collidepoint(mouse_pos)

            if selected:
                bg = (PANEL_COLOR[0] + 14, PANEL_COLOR[1] + 20, PANEL_COLOR[2] + 28)
                pygame.draw.rect(surface, bg, rect, border_radius=7)
                pygame.draw.rect(surface, ACCENT_COLOR, rect, width=1, border_radius=7)
            elif hovered:
                bg = (PANEL_COLOR[0] + 8, PANEL_COLOR[1] + 10, PANEL_COLOR[2] + 14)
                pygame.draw.rect(surface, bg, rect, border_radius=7)

            color = TEXT_COLOR if (selected or hovered) else SUBTLE_TEXT_COLOR
            lbl = self._body_font.render(label, True, color)
            surface.blit(lbl, lbl.get_rect(midleft=(rect.left + 10, rect.centery)))

            if selected:
                pygame.draw.circle(surface, ACCENT_COLOR, (rect.right - 12, rect.centery), 4)

    def _draw_prompt_panel(
        self,
        surface: pygame.Surface,
        panel_rect: pygame.Rect,
        input_rect: pygame.Rect,
        chaos_mode: str,
    ) -> None:
        greyed = chaos_mode == "local"
        pygame.draw.rect(surface, PANEL_COLOR, panel_rect, border_radius=12)
        pygame.draw.rect(surface, PANEL_BORDER_COLOR, panel_rect, width=1, border_radius=12)

        title_color = SUBTLE_TEXT_COLOR if greyed else TEXT_COLOR
        t = self._section_font.render("Custom Chaos Prompt", True, title_color)
        surface.blit(t, (panel_rect.left + 12, panel_rect.top + 9))

        if greyed:
            box_color    = (max(0, PANEL_COLOR[0] - 4), max(0, PANEL_COLOR[1] - 4), max(0, PANEL_COLOR[2] - 4))
            border_color = (max(0, PANEL_BORDER_COLOR[0] - 22), max(0, PANEL_BORDER_COLOR[1] - 22), max(0, PANEL_BORDER_COLOR[2] - 22))
        elif self._text_active:
            box_color    = CARD_COLOR
            border_color = ACCENT_COLOR
        else:
            box_color    = CARD_COLOR
            border_color = PANEL_BORDER_COLOR

        pygame.draw.rect(surface, box_color,    input_rect, border_radius=7)
        pygame.draw.rect(surface, border_color, input_rect, width=1, border_radius=7)

        if greyed:
            ph = self._small_font.render("Custom prompts require Hybrid mode.", True, SUBTLE_TEXT_COLOR)
            surface.blit(ph, ph.get_rect(midleft=(input_rect.left + 8, input_rect.centery)))
        else:
            display = self._custom_prompt
            if self._text_active and (pygame.time.get_ticks() // 500) % 2 == 0:
                display += "|"
            if display:
                ts = self._small_font.render(display, True, TEXT_COLOR)
                avail = input_rect.width - 16
                clip = pygame.Rect(input_rect.left + 8, input_rect.top + 2, avail, input_rect.height - 4)
                surface.set_clip(clip)
                x = input_rect.right - 8 - ts.get_width() if ts.get_width() > avail else input_rect.left + 8
                surface.blit(ts, (x, input_rect.centery - ts.get_height() // 2))
                surface.set_clip(None)
            elif not self._text_active:
                ph = self._small_font.render(_PROMPT_PLACEHOLDER, True, SUBTLE_TEXT_COLOR)
                clip = pygame.Rect(input_rect.left + 8, input_rect.top + 2, input_rect.width - 16, input_rect.height - 4)
                surface.set_clip(clip)
                surface.blit(ph, ph.get_rect(midleft=(input_rect.left + 8, input_rect.centery)))
                surface.set_clip(None)

            counter_text = f"{len(self._custom_prompt)}/{_PROMPT_MAX_LEN}"
            counter_color = WARNING_COLOR if len(self._custom_prompt) >= _PROMPT_MAX_LEN else SUBTLE_TEXT_COLOR
            cs = self._small_font.render(counter_text, True, counter_color)
            surface.blit(cs, (panel_rect.right - cs.get_width() - 10, input_rect.bottom + 4))

    def _draw_description_panel(self, surface: pygame.Surface, panel_rect: pygame.Rect) -> None:
        pygame.draw.rect(surface, PANEL_COLOR, panel_rect, border_radius=12)
        pygame.draw.rect(surface, PANEL_BORDER_COLOR, panel_rect, width=1, border_radius=12)

        t = self._section_font.render("Description", True, TEXT_COLOR)
        surface.blit(t, (panel_rect.left + 12, panel_rect.top + 9))

        lines = self._wrap_text(self._hover_desc, self._small_font, panel_rect.width - 24)
        y = panel_rect.top + _HEADER_H
        for line in lines:
            if y + 16 > panel_rect.bottom - 6:
                break
            ls = self._small_font.render(line, True, SUBTLE_TEXT_COLOR)
            surface.blit(ls, (panel_rect.left + 12, y))
            y += 17

    def _draw_start_button(
        self,
        surface: pygame.Surface,
        btn_rect: pygame.Rect,
        mouse_pos,
        chaos_mode: str,
    ) -> None:
        hovered = btn_rect.collidepoint(mouse_pos)
        color = BUTTON_HOVER_COLOR if hovered else BUTTON_ACTIVE_COLOR
        pygame.draw.rect(surface, color, btn_rect, border_radius=12)
        pygame.draw.rect(surface, PANEL_BORDER_COLOR, btn_rect, width=1, border_radius=12)
        lbl = self._button_font.render("Start Game", True, TEXT_COLOR)
        surface.blit(lbl, lbl.get_rect(center=btn_rect.center))

        if chaos_mode == "hybrid" and not self._api_key_available:
            warn = self._small_font.render(
                "No API key found — will fall back to local chaos.", True, WARNING_COLOR,
            )
            surface.blit(warn, warn.get_rect(centerx=WINDOW_WIDTH // 2, top=btn_rect.bottom + 6))

    # ------------------------------------------------------------------
    # Result building
    # ------------------------------------------------------------------

    def _build_result(self) -> LobbyResult:
        chaos_mode = _CHAOS_OPTIONS[self._chaos_idx][1]
        prompt = self._custom_prompt.strip() if chaos_mode == "hybrid" else ""
        return LobbyResult(
            mode=_MODE_OPTIONS[self._mode_idx][1],
            initial_time_ms=_TIME_OPTIONS[self._time_idx][1],
            chaos_mode=chaos_mode,
            chaos_frequency=_FREQ_OPTIONS[self._freq_idx][1],
            bot_difficulty=_DIFF_OPTIONS[self._diff_idx][1],
            custom_chaos_prompt=prompt,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if font.size(trial)[0] <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines
