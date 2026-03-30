from __future__ import annotations

import chess

from chaos_chess.game.move_resolver import MoveResolver


def test_move_resolver_returns_all_promotion_choices() -> None:
    board = chess.Board("7k/P7/8/8/8/8/8/K7 w - - 0 1")
    resolver = MoveResolver()

    moves = resolver.matching_moves(board, chess.A7, chess.A8)

    assert {move.promotion for move in moves} == {
        chess.QUEEN,
        chess.ROOK,
        chess.BISHOP,
        chess.KNIGHT,
    }
