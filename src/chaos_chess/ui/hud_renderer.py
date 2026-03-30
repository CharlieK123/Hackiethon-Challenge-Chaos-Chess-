from __future__ import annotations

from dataclasses import dataclass

import chess
import pygame

from chaos_chess.config import (
    ACCENT_COLOR,
    BOARD_MARGIN,
    BOARD_SIZE,
    BUTTON_ACTIVE_COLOR,
    BUTTON_COLOR,
    BUTTON_DISABLED_COLOR,
    BUTTON_HOVER_COLOR,
    CARD_ALT_COLOR,
    CARD_COLOR,
    CARD_SHADOW_COLOR,
    PANEL_BORDER_COLOR,
    PANEL_COLOR,
    PANEL_ORIGIN_X,
    PANEL_WIDTH,
    SUBTLE_TEXT_COLOR,
    SUCCESS_COLOR,
    TEXT_COLOR,
    WARNING_COLOR,
)
from chaos_chess.game.session import GameSession, color_name
from chaos_chess.game.types import GameMode, GamePhase
from chaos_chess.infra.asset_loader import load_font


def draw_wrapped_text(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: tuple,
    rect: pygame.Rect,
    line_spacing: int = 2,
) -> int:
    """Draws text wrapped to rect width. Returns the total height used in pixels."""
    words = text.split()
    if not words:
        return 0

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if font.size(trial)[0] <= rect.width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)

    line_height = font.get_linesize() + line_spacing
    y = rect.top
    for line in lines:
        if y + font.get_linesize() > rect.bottom:
            break
        surface.blit(font.render(line, True, color), (rect.left, y))
        y += line_height

    return y - rect.top


@dataclass(slots=True, frozen=True)
class HudViewState:
    game_mode: GameMode
    chaos_enabled: bool
    claude_enabled: bool
    claude_available: bool


class HudRenderer:
    def __init__(self) -> None:
        self.panel_rect = pygame.Rect(PANEL_ORIGIN_X, BOARD_MARGIN, PANEL_WIDTH, BOARD_SIZE)
        self.title_font = load_font(30, bold=True)
        self.section_font = load_font(18, bold=True)
        self.body_font = load_font(18)
        self.clock_font = load_font(30, bold=True)
        self.small_font = load_font(15)
        self.button_font = load_font(16, bold=True)

    def draw(self, surface: pygame.Surface, session: GameSession, view_state: HudViewState) -> None:
        self._draw_panel(surface)

        left = self.panel_rect.left + 18
        top = self.panel_rect.top + 18

        title = self.title_font.render("Chaos Chess", True, TEXT_COLOR)
        surface.blit(title, (left, top))

        subtitle = self.small_font.render(self._subtitle(view_state), True, SUBTLE_TEXT_COLOR)
        surface.blit(subtitle, (left + 2, top + 34))

        top += 54
        top = self._draw_controls(surface, top, view_state)
        top += 12
        top = self._draw_status_card(surface, left, top, session)
        top += 12
        top = self._draw_clock_row(surface, top, session)
        top += 8
        top = self._draw_chaos_level_indicator(surface, top, session)
        top += 10
        top = self._draw_active_event(surface, left, top, session, view_state)
        top += 12
        top = self._draw_event_log(surface, left, top, session)
        top += 12
        self._draw_move_list(surface, left, top, session)

    def button_at_position(self, position: tuple[int, int], view_state: HudViewState) -> str | None:
        for kind, rect in self._control_button_rects(self.panel_rect.top + 72).items():
            if rect.collidepoint(position):
                if kind == "toggle_claude" and not view_state.claude_available:
                    return None
                return kind
        return None

    def _draw_panel(self, surface: pygame.Surface) -> None:
        shadow_rect = self.panel_rect.inflate(10, 12)
        shadow = pygame.Surface(shadow_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(shadow, CARD_SHADOW_COLOR, shadow.get_rect(), border_radius=22)
        surface.blit(shadow, (shadow_rect.left + 6, shadow_rect.top + 8))

        pygame.draw.rect(surface, PANEL_COLOR, self.panel_rect, border_radius=18)
        pygame.draw.rect(surface, PANEL_BORDER_COLOR, self.panel_rect, width=2, border_radius=18)

    def _draw_controls(self, surface: pygame.Surface, top: int, view_state: HudViewState) -> int:
        for kind, rect in self._control_button_rects(top).items():
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            color = BUTTON_COLOR
            text_color = TEXT_COLOR

            if kind == "toggle_mode" and view_state.game_mode == GameMode.LOCAL_PVP:
                color = BUTTON_ACTIVE_COLOR
            elif kind == "toggle_chaos" and view_state.chaos_enabled:
                color = BUTTON_ACTIVE_COLOR
            elif kind == "toggle_claude" and not view_state.claude_available:
                color = BUTTON_DISABLED_COLOR
                text_color = SUBTLE_TEXT_COLOR
            elif kind == "toggle_claude" and view_state.claude_enabled:
                color = BUTTON_ACTIVE_COLOR
            elif hovered:
                color = BUTTON_HOVER_COLOR

            pygame.draw.rect(surface, color, rect, border_radius=12)
            pygame.draw.rect(surface, PANEL_BORDER_COLOR, rect, width=2, border_radius=12)

            label = self.button_font.render(self._button_label(kind, view_state), True, text_color)
            label_rect = label.get_rect(center=rect.center)
            surface.blit(label, label_rect)

        return top + 34

    def _draw_status_card(self, surface: pygame.Surface, left: int, top: int, session: GameSession) -> int:
        card_rect = pygame.Rect(self.panel_rect.left + 14, top, self.panel_rect.width - 28, 78)
        self._draw_card(surface, card_rect, accent=session.state.result is not None)

        title = self.section_font.render("Match Status", True, TEXT_COLOR)
        surface.blit(title, (left, card_rect.top + 12))

        text_top = card_rect.top + 38
        for line in self._wrap_text(session.status_text(), self.body_font, card_rect.width - 24)[:2]:
            status = self.body_font.render(line, True, TEXT_COLOR)
            surface.blit(status, (card_rect.left + 12, text_top))
            text_top += 21

        detail_top = card_rect.top + 58
        for line in self._wrap_text(session.status_detail_text(), self.small_font, card_rect.width - 24)[:1]:
            detail = self.small_font.render(line, True, SUBTLE_TEXT_COLOR)
            surface.blit(detail, (card_rect.left + 12, detail_top))
            detail_top += 17
        return card_rect.bottom

    def _draw_clock_row(self, surface: pygame.Surface, top: int, session: GameSession) -> int:
        gap = 12
        card_width = (self.panel_rect.width - 28 - gap) // 2
        white_rect = pygame.Rect(self.panel_rect.left + 14, top, card_width, 80)
        black_rect = pygame.Rect(white_rect.right + gap, top, card_width, 80)

        self._draw_clock_card(surface, white_rect, chess.WHITE, session)
        self._draw_clock_card(surface, black_rect, chess.BLACK, session)
        return white_rect.bottom

    def _draw_clock_card(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        color: chess.Color,
        session: GameSession,
    ) -> None:
        active = session.clock.active_color == color and session.state.result is None
        accent = active
        self._draw_card(surface, rect, accent=accent)

        label_suffix = session.player_label(color)
        label = self.section_font.render(color_name(color), True, TEXT_COLOR)
        surface.blit(label, (rect.left + 12, rect.top + 10))

        role = self.small_font.render(label_suffix, True, SUBTLE_TEXT_COLOR)
        surface.blit(role, (rect.left + 12, rect.top + 30))

        clock_color = WARNING_COLOR if session.clock.remaining_ms(color) <= 10_000 else TEXT_COLOR
        clock = self.clock_font.render(session.formatted_clock(color), True, clock_color)
        surface.blit(clock, (rect.left + 12, rect.top + 40))

        state_text = self._clock_state_text(color, session)
        state_color = ACCENT_COLOR if active else SUBTLE_TEXT_COLOR
        if state_text == "Flagged":
            state_color = WARNING_COLOR
        badge = self.small_font.render(state_text, True, state_color)
        badge_rect = badge.get_rect(topright=(rect.right - 12, rect.top + 14))
        surface.blit(badge, badge_rect)

    def _draw_chaos_level_indicator(
        self,
        surface: pygame.Surface,
        top: int,
        session: GameSession,
    ) -> int:
        level = session.chaos_director.chaos_level
        labels = {1: "Chaos: Calm", 2: "Chaos: Rising", 3: "Chaos: Intense", 4: "Chaos: CRITICAL"}
        colors = {
            1: TEXT_COLOR,
            2: (255, 215, 0),    # yellow
            3: (255, 140, 0),    # orange
            4: (220, 50, 50),    # red
        }
        label = labels[level]
        color = colors[level]

        # At level 4, flash at 1 Hz (visible for 500 ms, hidden for 500 ms).
        if level == 4 and (pygame.time.get_ticks() // 500) % 2 != 0:
            return top + 20

        text = self.small_font.render(label, True, color)
        text_rect = text.get_rect(
            centerx=self.panel_rect.centerx,
            top=top,
        )
        surface.blit(text, text_rect)
        return top + 20

    def _draw_active_event(
        self,
        surface: pygame.Surface,
        left: int,
        top: int,
        session: GameSession,
        view_state: HudViewState,
    ) -> int:
        card_rect = pygame.Rect(self.panel_rect.left + 14, top, self.panel_rect.width - 28, 92)
        self._draw_card(surface, card_rect)

        title = self.section_font.render("Chaos Director", True, TEXT_COLOR)
        surface.blit(title, (left, card_rect.top + 12))

        badge_text, badge_color = self._chaos_badge(view_state)
        badge = self.small_font.render(badge_text, True, badge_color)
        badge_rect = badge.get_rect(topright=(card_rect.right - 12, card_rect.top + 16))
        surface.blit(badge, badge_rect)

        active_title = self.body_font.render(session.active_event_title, True, TEXT_COLOR)
        surface.blit(active_title, (card_rect.left + 12, card_rect.top + 38))

        text_top = card_rect.top + 60
        for line in self._wrap_text(session.active_event_description, self.small_font, card_rect.width - 24)[:2]:
            text = self.small_font.render(line, True, SUBTLE_TEXT_COLOR)
            surface.blit(text, (card_rect.left + 12, text_top))
            text_top += 18

        return card_rect.bottom

    def _draw_event_log(
        self,
        surface: pygame.Surface,
        left: int,
        top: int,
        session: GameSession,
    ) -> int:
        _PAD = 12
        _HEADER_H = 38
        _ENTRY_LEFT_PAD = 18   # space reserved for the coloured dot
        _DOT_X = 7
        _DOT_Y = 9             # from entry-row top
        _ENTRY_GAP = 10        # vertical gap between entries (includes divider)

        card_left = self.panel_rect.left + 14
        card_w = self.panel_rect.width - 28
        text_w = card_w - 20 - _ENTRY_LEFT_PAD  # 10px card-side-pad each side, then dot area

        entries = list(reversed(session.chaos_log_rows()[-4:]))

        # Pre-wrap every entry so we know how tall each one is.
        line_advance = self.small_font.get_linesize() + 2  # line_spacing=2
        entry_wraps = [self._wrap_text(e, self.small_font, text_w) for e in entries]
        entry_heights = [max(1, len(lines)) * line_advance for lines in entry_wraps]

        dividers = max(0, len(entries) - 1)
        content_h = sum(entry_heights) + dividers * _ENTRY_GAP
        card_h = max(80, _HEADER_H + content_h + _PAD)

        card_rect = pygame.Rect(card_left, top, card_w, card_h)
        self._draw_card(surface, card_rect)

        title = self.section_font.render("Event Log", True, TEXT_COLOR)
        surface.blit(title, (left, card_rect.top + _PAD))

        subtitle = self.small_font.render("Latest first", True, SUBTLE_TEXT_COLOR)
        subtitle_rect = subtitle.get_rect(topright=(card_rect.right - _PAD, card_rect.top + 15))
        surface.blit(subtitle, subtitle_rect)

        if not entries:
            empty = self.small_font.render("No chaos events yet.", True, SUBTLE_TEXT_COLOR)
            surface.blit(empty, (card_rect.left + _PAD, card_rect.top + _HEADER_H))
            return card_rect.bottom

        old_clip = surface.get_clip()
        surface.set_clip(card_rect)

        row_top = card_rect.top + _HEADER_H
        row_left = card_rect.left + 10
        row_w = card_w - 20

        for index, (entry, entry_h) in enumerate(zip(entries, entry_heights)):
            color = TEXT_COLOR if index == 0 else SUBTLE_TEXT_COLOR
            dot_color = ACCENT_COLOR if index == 0 else SUCCESS_COLOR

            pygame.draw.circle(surface, dot_color, (row_left + _DOT_X, row_top + _DOT_Y), 4)

            text_rect = pygame.Rect(
                row_left + _ENTRY_LEFT_PAD,
                row_top,
                text_w,
                card_rect.bottom - row_top - _PAD,
            )
            draw_wrapped_text(surface, entry, self.small_font, color, text_rect, line_spacing=2)

            row_top += entry_h

            if index < len(entries) - 1:
                divider_y = row_top + _ENTRY_GAP // 2
                pygame.draw.line(
                    surface, PANEL_BORDER_COLOR,
                    (row_left, divider_y), (row_left + row_w, divider_y),
                    width=1,
                )
                row_top += _ENTRY_GAP

        surface.set_clip(old_clip)
        return card_rect.bottom

    def _draw_move_list(self, surface: pygame.Surface, left: int, top: int, session: GameSession) -> None:
        card_rect = pygame.Rect(
            self.panel_rect.left + 14, top,
            self.panel_rect.width - 28,
            self.panel_rect.bottom - top - 14,
        )
        if card_rect.height < 40:
            return

        self._draw_card(surface, card_rect)

        title = self.section_font.render("Moves", True, TEXT_COLOR)
        surface.blit(title, (left, card_rect.top + 12))

        hint = self.small_font.render("Hotkeys: R restart, P mode, C chaos, D Claude", True, SUBTLE_TEXT_COLOR)
        hint_rect = hint.get_rect(topright=(card_rect.right - 12, card_rect.top + 15))
        surface.blit(hint, hint_rect)

        rows = session.move_rows()[-7:]
        if not rows:
            empty = self.small_font.render("No moves played yet.", True, SUBTLE_TEXT_COLOR)
            surface.blit(empty, (card_rect.left + 12, card_rect.top + 44))
            return

        old_clip = surface.get_clip()
        surface.set_clip(card_rect)

        text_top = card_rect.top + 42
        inner_w = card_rect.width - 24
        for row in rows:
            text_rect = pygame.Rect(card_rect.left + 12, text_top, inner_w, card_rect.bottom - text_top - 8)
            if text_rect.height < self.small_font.get_linesize():
                break
            used = draw_wrapped_text(surface, row, self.small_font, SUBTLE_TEXT_COLOR, text_rect, line_spacing=2)
            text_top += max(used, self.small_font.get_linesize() + 2) + 2

        surface.set_clip(old_clip)

    def _draw_card(self, surface: pygame.Surface, rect: pygame.Rect, *, accent: bool = False) -> None:
        pygame.draw.rect(surface, CARD_COLOR if not accent else CARD_ALT_COLOR, rect, border_radius=14)
        border_color = ACCENT_COLOR if accent else PANEL_BORDER_COLOR
        pygame.draw.rect(surface, border_color, rect, width=2, border_radius=14)

    def _control_button_rects(self, top: int) -> dict[str, pygame.Rect]:
        card_left = self.panel_rect.left + 14
        width = self.panel_rect.width - 28
        gap = 10
        button_width = (width - 3 * gap) // 4
        return {
            "restart": pygame.Rect(card_left, top, button_width, 34),
            "toggle_mode": pygame.Rect(card_left + button_width + gap, top, button_width, 34),
            "toggle_chaos": pygame.Rect(card_left + 2 * (button_width + gap), top, button_width, 34),
            "toggle_claude": pygame.Rect(card_left + 3 * (button_width + gap), top, button_width, 34),
        }

    def _button_label(self, kind: str, view_state: HudViewState) -> str:
        if kind == "restart":
            return "Restart"
        if kind == "toggle_mode":
            return "Vs Friend" if view_state.game_mode == GameMode.HUMAN_VS_BOT else "Vs Bot"
        if kind == "toggle_chaos":
            return f"Chaos {'On' if view_state.chaos_enabled else 'Off'}"
        if not view_state.claude_available:
            return "Claude N/A"
        return f"Claude {'On' if view_state.claude_enabled else 'Off'}"

    @staticmethod
    def _subtitle(view_state: HudViewState) -> str:
        mode_label = "Human vs Friend" if view_state.game_mode == GameMode.LOCAL_PVP else "Human vs Bot"
        return f"{mode_label}  |  5+0 rapid"

    def _chaos_badge(self, view_state: HudViewState) -> tuple[str, tuple[int, int, int]]:
        if not view_state.chaos_enabled:
            return ("Off", WARNING_COLOR)
        if view_state.claude_enabled and view_state.claude_available:
            return ("Claude + Local", ACCENT_COLOR)
        return ("Local Only", SUCCESS_COLOR)

    def _clock_state_text(self, color: chess.Color, session: GameSession) -> str:
        if session.state.result is not None and session.state.result.reason == "timeout":
            if session.clock.remaining_ms(color) <= 0:
                return "Flagged"
            return "Won"
        if session.clock.active_color == color and session.state.result is None:
            return "Running"
        if session.state.phase == GamePhase.CHAOS_PENDING:
            return "Paused"
        if session.state.result is not None:
            return "Stopped"
        return "Waiting"

    def _wrap_text(
        self,
        text: str,
        font: pygame.font.Font,
        max_width: int,
    ) -> list[str]:
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
