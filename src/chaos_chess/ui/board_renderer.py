from __future__ import annotations

import chess
import pygame

from chaos_chess.chaos.models import ChaosEventType
from chaos_chess.config import (
    ACCENT_COLOR,
    BLACK_PIECE_FILL,
    BLACK_PIECE_TEXT,
    BOARD_EDGE_COLOR,
    BOARD_ORIGIN,
    BOARD_SHADOW_COLOR,
    BOARD_SIZE,
    CAPTURE_HINT_COLOR,
    CHECK_HIGHLIGHT_COLOR,
    DARK_SQUARE_COLOR,
    FROZEN_BORDER_COLOR,
    FROZEN_SQUARE_COLOR,
    LAST_MOVE_FROM_COLOR,
    LAST_MOVE_TO_COLOR,
    LIGHT_SQUARE_COLOR,
    LOCKED_BORDER_COLOR,
    LOCKED_SQUARE_COLOR,
    MOVE_HINT_COLOR,
    PIECE_BORDER_COLOR,
    PROMOTION_BUTTON_COLOR,
    PROMOTION_BUTTON_HOVER_COLOR,
    PROMOTION_OVERLAY_COLOR,
    PROMOTION_PANEL_COLOR,
    SELECTED_SQUARE_COLOR,
    SLIPPERY_BORDER_COLOR,
    SLIPPERY_SQUARE_COLOR,
    SQUARE_SIZE,
    SUBTLE_TEXT_COLOR,
    TEXT_COLOR,
    WHITE_PIECE_FILL,
    WHITE_PIECE_TEXT,
)
from chaos_chess.game.state import GameState
from chaos_chess.game.types import PromotionPrompt
from chaos_chess.infra.asset_loader import load_font


PIECE_LABELS = {
    chess.PAWN: "P",
    chess.KNIGHT: "N",
    chess.BISHOP: "B",
    chess.ROOK: "R",
    chess.QUEEN: "Q",
    chess.KING: "K",
}

PROMOTION_LABELS = {
    chess.QUEEN: "Queen",
    chess.ROOK: "Rook",
    chess.BISHOP: "Bishop",
    chess.KNIGHT: "Knight",
}


class BoardRenderer:
    def __init__(self) -> None:
        self.board_rect = pygame.Rect(BOARD_ORIGIN[0], BOARD_ORIGIN[1], BOARD_SIZE, BOARD_SIZE)
        self.piece_font = load_font(32, bold=True)
        self.coord_font = load_font(16, bold=True)
        self.promotion_title_font = load_font(22, bold=True)
        self.promotion_button_font = load_font(18, bold=True)

    def draw(self, surface: pygame.Surface, state: GameState) -> None:
        self._draw_board_frame(surface)
        self._draw_board(surface)
        self._draw_last_move(surface, state)
        self._draw_chaos_annotations(surface, state)
        self._draw_highlights(surface, state)
        self._draw_check_marker(surface, state.board)
        self._draw_pieces(surface, state.board)
        self._draw_coordinates(surface)

        if state.pending_promotion is not None:
            self._draw_promotion_prompt(surface, state.pending_promotion)

    def square_at_position(self, position: tuple[int, int]) -> int | None:
        if not self.board_rect.collidepoint(position):
            return None

        x_offset = position[0] - self.board_rect.left
        y_offset = position[1] - self.board_rect.top
        file_index = x_offset // SQUARE_SIZE
        rank_from_top = y_offset // SQUARE_SIZE
        rank_index = 7 - rank_from_top
        return chess.square(file_index, rank_index)

    def promotion_piece_at_position(
        self,
        position: tuple[int, int],
        prompt: PromotionPrompt,
    ) -> int | None:
        for piece_type, rect in self._promotion_button_rects(prompt).items():
            if rect.collidepoint(position):
                return piece_type
        return None

    def _draw_board_frame(self, surface: pygame.Surface) -> None:
        shadow_rect = self.board_rect.inflate(18, 18)
        shadow = pygame.Surface(shadow_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(shadow, BOARD_SHADOW_COLOR, shadow.get_rect(), border_radius=22)
        surface.blit(shadow, (shadow_rect.left + 8, shadow_rect.top + 10))

        frame_rect = self.board_rect.inflate(12, 12)
        pygame.draw.rect(surface, (18, 22, 27), frame_rect, border_radius=18)
        pygame.draw.rect(surface, BOARD_EDGE_COLOR, frame_rect, width=2, border_radius=18)

    def _draw_board(self, surface: pygame.Surface) -> None:
        for rank in range(8):
            for file_index in range(8):
                rect = pygame.Rect(
                    self.board_rect.left + file_index * SQUARE_SIZE,
                    self.board_rect.top + rank * SQUARE_SIZE,
                    SQUARE_SIZE,
                    SQUARE_SIZE,
                )
                is_light = (file_index + rank) % 2 == 0
                color = LIGHT_SQUARE_COLOR if is_light else DARK_SQUARE_COLOR
                pygame.draw.rect(surface, color, rect)

    def _draw_last_move(self, surface: pygame.Surface, state: GameState) -> None:
        if state.last_move_from is not None:
            self._fill_square(surface, state.last_move_from, LAST_MOVE_FROM_COLOR)
        if state.last_move_to is not None:
            self._fill_square(surface, state.last_move_to, LAST_MOVE_TO_COLOR)

    def _draw_highlights(self, surface: pygame.Surface, state: GameState) -> None:
        if state.selected_square is not None:
            rect = self._square_rect(state.selected_square)
            self._fill_square(surface, state.selected_square, SELECTED_SQUARE_COLOR)
            pygame.draw.rect(surface, ACCENT_COLOR, rect.inflate(-8, -8), width=3, border_radius=12)

        for target in state.legal_targets:
            rect = self._square_rect(target)
            if state.board.piece_at(target) is not None:
                capture = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
                pygame.draw.circle(capture, (*CAPTURE_HINT_COLOR, 72), (SQUARE_SIZE // 2, SQUARE_SIZE // 2), 26)
                surface.blit(capture, rect.topleft)
                pygame.draw.circle(surface, CAPTURE_HINT_COLOR, rect.center, 24, width=4)
                pygame.draw.circle(surface, CAPTURE_HINT_COLOR, rect.center, 8)
            else:
                hint = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
                pygame.draw.circle(hint, (*MOVE_HINT_COLOR, 60), (SQUARE_SIZE // 2, SQUARE_SIZE // 2), 18)
                surface.blit(hint, rect.topleft)
                pygame.draw.circle(surface, MOVE_HINT_COLOR, rect.center, 11)

    def _draw_chaos_annotations(self, surface: pygame.Surface, state: GameState) -> None:
        event = state.active_event
        if event is None:
            return

        if event.event_type == ChaosEventType.LOCKED_SQUARES:
            for square in event.locked_squares:
                rect = self._square_rect(square)
                self._fill_square(surface, square, LOCKED_SQUARE_COLOR)
                pygame.draw.rect(surface, LOCKED_BORDER_COLOR, rect.inflate(-8, -8), width=3, border_radius=12)
                pygame.draw.line(surface, LOCKED_BORDER_COLOR, rect.move(10, 10).topleft, rect.move(-10, -10).bottomright, width=3)
                pygame.draw.line(surface, LOCKED_BORDER_COLOR, rect.move(-10, 10).topright, rect.move(10, -10).bottomleft, width=3)

        elif event.event_type == ChaosEventType.FROZEN_PIECE and event.frozen_square is not None:
            rect = self._square_rect(event.frozen_square)
            self._fill_square(surface, event.frozen_square, FROZEN_SQUARE_COLOR)
            pygame.draw.rect(surface, FROZEN_BORDER_COLOR, rect.inflate(-8, -8), width=3, border_radius=12)
            pygame.draw.circle(surface, FROZEN_BORDER_COLOR, rect.center, 18, width=3)

        elif event.event_type == ChaosEventType.SLIPPERY_SQUARE and event.slippery_square is not None:
            rect = self._square_rect(event.slippery_square)
            self._fill_square(surface, event.slippery_square, SLIPPERY_SQUARE_COLOR)
            pygame.draw.rect(surface, SLIPPERY_BORDER_COLOR, rect.inflate(-8, -8), width=3, border_radius=12)
            pygame.draw.circle(surface, SLIPPERY_BORDER_COLOR, rect.center, 16, width=3)
            pygame.draw.arc(surface, SLIPPERY_BORDER_COLOR, rect.inflate(-20, -20), 0.4, 2.6, width=3)

    def _draw_check_marker(self, surface: pygame.Surface, board: chess.Board) -> None:
        if not board.is_check():
            return

        king_square = board.king(board.turn)
        if king_square is None:
            return

        rect = self._square_rect(king_square)
        self._fill_square(surface, king_square, CHECK_HIGHLIGHT_COLOR)
        pygame.draw.rect(surface, CAPTURE_HINT_COLOR, rect.inflate(-6, -6), width=3, border_radius=14)

    def _draw_pieces(self, surface: pygame.Surface, board: chess.Board) -> None:
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece is None:
                continue

            rect = self._square_rect(square)
            center = rect.center
            radius = SQUARE_SIZE // 2 - 11
            fill = WHITE_PIECE_FILL if piece.color == chess.WHITE else BLACK_PIECE_FILL
            text_color = WHITE_PIECE_TEXT if piece.color == chess.WHITE else BLACK_PIECE_TEXT

            shadow = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
            pygame.draw.circle(shadow, (0, 0, 0, 45), (SQUARE_SIZE // 2 + 2, SQUARE_SIZE // 2 + 3), radius)
            surface.blit(shadow, rect.topleft)
            pygame.draw.circle(surface, fill, center, radius)
            pygame.draw.circle(surface, PIECE_BORDER_COLOR, center, radius, width=2)

            label = PIECE_LABELS[piece.piece_type]
            text_surface = self.piece_font.render(label, True, text_color)
            text_rect = text_surface.get_rect(center=center)
            surface.blit(text_surface, text_rect)

    def _draw_coordinates(self, surface: pygame.Surface) -> None:
        for file_index in range(8):
            file_label = chr(ord("a") + file_index)
            text = self.coord_font.render(file_label, True, SUBTLE_TEXT_COLOR)
            x = self.board_rect.left + file_index * SQUARE_SIZE + 6
            y = self.board_rect.bottom - 22
            surface.blit(text, (x, y))

        for rank in range(8):
            rank_label = str(8 - rank)
            text = self.coord_font.render(rank_label, True, SUBTLE_TEXT_COLOR)
            x = self.board_rect.left + 5
            y = self.board_rect.top + rank * SQUARE_SIZE + 4
            surface.blit(text, (x, y))

    def _draw_promotion_prompt(self, surface: pygame.Surface, prompt: PromotionPrompt) -> None:
        overlay = pygame.Surface((BOARD_SIZE, BOARD_SIZE), pygame.SRCALPHA)
        overlay.fill(PROMOTION_OVERLAY_COLOR)
        surface.blit(overlay, self.board_rect.topleft)

        panel_width = 360
        panel_height = 160
        panel_rect = pygame.Rect(0, 0, panel_width, panel_height)
        panel_rect.center = self.board_rect.center
        pygame.draw.rect(surface, PROMOTION_PANEL_COLOR, panel_rect, border_radius=14)
        pygame.draw.rect(surface, ACCENT_COLOR, panel_rect, width=2, border_radius=14)

        title = self.promotion_title_font.render("Choose a promotion", True, TEXT_COLOR)
        title_rect = title.get_rect(center=(panel_rect.centerx, panel_rect.top + 28))
        surface.blit(title, title_rect)

        mouse_pos = pygame.mouse.get_pos()
        for piece_type, rect in self._promotion_button_rects(prompt).items():
            hovered = rect.collidepoint(mouse_pos)
            color = PROMOTION_BUTTON_HOVER_COLOR if hovered else PROMOTION_BUTTON_COLOR
            pygame.draw.rect(surface, color, rect, border_radius=10)
            pygame.draw.rect(surface, ACCENT_COLOR, rect, width=2, border_radius=10)

            label = self.promotion_button_font.render(PROMOTION_LABELS[piece_type], True, TEXT_COLOR)
            label_rect = label.get_rect(center=rect.center)
            surface.blit(label, label_rect)

    def _promotion_button_rects(self, prompt: PromotionPrompt) -> dict[int, pygame.Rect]:
        order = [
            chess.QUEEN,
            chess.ROOK,
            chess.BISHOP,
            chess.KNIGHT,
        ]
        total_width = 4 * 76 + 3 * 12
        start_x = self.board_rect.centerx - total_width // 2
        top_y = self.board_rect.centery

        rects: dict[int, pygame.Rect] = {}
        for index, piece_type in enumerate(order):
            if piece_type not in prompt.options:
                continue
            rects[piece_type] = pygame.Rect(start_x + index * 88, top_y, 76, 44)
        return rects

    def _fill_square(self, surface: pygame.Surface, square: int, color: tuple[int, int, int, int]) -> None:
        rect = self._square_rect(square)
        highlight = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
        highlight.fill(color)
        surface.blit(highlight, rect.topleft)

    def _square_rect(self, square: int) -> pygame.Rect:
        file_index = chess.square_file(square)
        rank_index = chess.square_rank(square)
        x = self.board_rect.left + file_index * SQUARE_SIZE
        y = self.board_rect.top + (7 - rank_index) * SQUARE_SIZE
        return pygame.Rect(x, y, SQUARE_SIZE, SQUARE_SIZE)
