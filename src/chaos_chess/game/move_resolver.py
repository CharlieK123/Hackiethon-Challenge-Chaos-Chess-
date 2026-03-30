from __future__ import annotations

import chess

from chaos_chess.chaos.models import ChaosEvent
from chaos_chess.chaos.validator import ChaosValidator


class MoveResolver:
    """Adapter around python-chess move generation."""

    def legal_moves(
        self,
        board: chess.Board,
        active_event: ChaosEvent | None = None,
    ) -> list[chess.Move]:
        return ChaosValidator.filter_moves(board, board.legal_moves, active_event)

    def legal_moves_for_square(
        self,
        board: chess.Board,
        square: int,
        active_event: ChaosEvent | None = None,
    ) -> list[chess.Move]:
        return [
            move
            for move in self.legal_moves(board, active_event)
            if move.from_square == square
        ]

    def legal_targets_for_square(
        self,
        board: chess.Board,
        square: int,
        active_event: ChaosEvent | None = None,
    ) -> set[int]:
        return {move.to_square for move in self.legal_moves_for_square(board, square, active_event)}

    def matching_moves(
        self,
        board: chess.Board,
        from_square: int,
        to_square: int,
        active_event: ChaosEvent | None = None,
    ) -> list[chess.Move]:
        return [
            move
            for move in self.legal_moves(board, active_event)
            if move.from_square == from_square and move.to_square == to_square
        ]

    def san(self, board: chess.Board, move: chess.Move) -> str:
        return board.san(move)
