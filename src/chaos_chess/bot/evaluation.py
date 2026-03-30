from __future__ import annotations

import chess


PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


def material_score(board: chess.Board, perspective: chess.Color) -> int:
    """Return a simple material evaluation from one side's perspective."""

    score = 0
    opponent = not perspective
    for piece_type, value in PIECE_VALUES.items():
        score += len(board.pieces(piece_type, perspective)) * value
        score -= len(board.pieces(piece_type, opponent)) * value
    return score
