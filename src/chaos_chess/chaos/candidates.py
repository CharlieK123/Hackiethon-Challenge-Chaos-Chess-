from __future__ import annotations

from collections.abc import Iterable

import chess

from chaos_chess.chaos.models import ChaosEventType
from chaos_chess.chaos.schemas import RawChaosEvent
from chaos_chess.chaos.validator import ChaosValidator


PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


def locked_square_candidates(board: chess.Board, moves: Iterable[chess.Move] | None = None) -> list[int]:
    move_list = list(moves) if moves is not None else list(board.legal_moves)
    return sorted({move.to_square for move in move_list})


def frozen_piece_candidates(board: chess.Board, moves: Iterable[chess.Move] | None = None) -> list[dict[str, str]]:
    move_list = list(moves) if moves is not None else list(board.legal_moves)
    movable_by_square: dict[int, list[chess.Move]] = {}
    for move in move_list:
        movable_by_square.setdefault(move.from_square, []).append(move)

    candidates: list[dict[str, str]] = []
    for square in sorted(movable_by_square):
        piece = board.piece_at(square)
        if piece is None or piece.color != board.turn or piece.piece_type == chess.KING:
            continue
        candidates.append(
            {
                "square": chess.square_name(square),
                "piece_type": PIECE_NAMES[piece.piece_type],
                "color": "white" if piece.color == chess.WHITE else "black",
            }
        )

    return candidates


def slippery_square_candidates(board: chess.Board, moves: Iterable[chess.Move] | None = None) -> list[int]:
    move_list = list(moves) if moves is not None else list(board.legal_moves)
    candidates: list[int] = []
    for move in move_list:
        if board.piece_at(move.to_square) is not None:
            continue
        if ChaosValidator.preview_slippery_destination(board, move) is None:
            continue
        candidates.append(move.to_square)

    return list(dict.fromkeys(candidates))


def gust_shift_candidates(
    board: chess.Board,
    direction: int,
    color: chess.Color,
) -> list[dict[str, str]]:
    shifts: list[dict[str, str]] = []
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece is None or piece.color != color or piece.piece_type == chess.KING:
            continue

        next_file = chess.square_file(square) + direction
        if not (0 <= next_file < 8):
            continue

        target_square = chess.square(next_file, chess.square_rank(square))
        if board.piece_at(target_square) is not None:
            continue

        shift = {
            "from_square": chess.square_name(square),
            "to_square": chess.square_name(target_square),
            "piece_type": PIECE_NAMES[piece.piece_type],
            "color": "white" if piece.color == chess.WHITE else "black",
        }
        payload = build_gust_payload(direction, [shift], description="A gust of wind shoves pieces.")
        if ChaosValidator.validate_payload(board, payload) is not None:
            shifts.append(shift)

    return shifts


def teleport_candidates(board: chess.Board) -> list[int]:
    """Squares occupied by the current player's non-king pieces."""
    return [
        sq for sq in chess.SQUARES
        if (p := board.piece_at(sq)) is not None
        and p.color == board.turn
        and p.piece_type != chess.KING
    ]


def mirror_candidates(board: chess.Board) -> list[int]:
    """Opponent non-king piece squares that have an empty forward square (no pawn-to-back-rank)."""
    opponent = not board.turn
    forward_dir = 1 if opponent == chess.WHITE else -1
    candidates: list[int] = []
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None or piece.color != opponent or piece.piece_type == chess.KING:
            continue
        new_rank = chess.square_rank(sq) + forward_dir
        if not (0 <= new_rank < 8):
            continue
        if piece.piece_type == chess.PAWN:
            back_rank = 7 if opponent == chess.WHITE else 0
            if new_rank == back_rank:
                continue
        to_sq = chess.square(chess.square_file(sq), new_rank)
        if board.piece_at(to_sq) is None:
            candidates.append(sq)
    return candidates


def promotion_move_candidates(board: chess.Board) -> list[chess.Move]:
    """Legal moves where a pawn reaches the back rank."""
    return [m for m in board.legal_moves if m.promotion is not None]


def build_gust_payload(
    direction: int,
    shifts: list[dict[str, str]],
    description: str,
) -> RawChaosEvent:
    return {
        "event_type": ChaosEventType.GUST_OF_WIND.value,
        "description": description,
        "duration_turns": 1,
        "parameters": {
            "direction": "left" if direction == -1 else "right",
            "targets": "non_king_pieces",
            "shifts": shifts,
        },
    }
