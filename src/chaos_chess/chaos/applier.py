from __future__ import annotations

import chess

from chaos_chess.chaos.models import ChaosEvent, ChaosEventType


PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


def apply_piece_shift(board: chess.Board, from_square: int, to_square: int) -> None:
    piece = board.piece_at(from_square)
    if piece is None:
        raise ValueError("No piece found on the source square.")

    promoted = bool(board.promoted & chess.BB_SQUARES[from_square])
    board.remove_piece_at(from_square)
    board.set_piece_at(to_square, piece, promoted=promoted)
    board.ep_square = None
    board.castling_rights = board.clean_castling_rights()


def apply_gust(board: chess.Board, event: ChaosEvent) -> list[str]:
    if event.event_type != ChaosEventType.GUST_OF_WIND:
        return []

    messages: list[str] = []
    for shift in event.gust_shifts:
        apply_piece_shift(board, shift.from_square, shift.to_square)
        color_name = "White" if shift.color == chess.WHITE else "Black"
        piece_name = PIECE_NAMES[shift.piece_type]
        messages.append(
            f"{color_name} {piece_name} {chess.square_name(shift.from_square)} -> "
            f"{chess.square_name(shift.to_square)}"
        )
    return messages


def apply_teleport(board: chess.Board, event: ChaosEvent) -> list[str]:
    """Swap two friendly non-king pieces of the current player."""
    if event.event_type != ChaosEventType.TELEPORT:
        return []
    squares = event.teleport_squares
    if squares is None:
        return []
    sq_a, sq_b = squares
    piece_a = board.piece_at(sq_a)
    piece_b = board.piece_at(sq_b)
    if piece_a is None or piece_b is None:
        return []
    board.remove_piece_at(sq_a)
    board.remove_piece_at(sq_b)
    board.set_piece_at(sq_a, piece_b)
    board.set_piece_at(sq_b, piece_a)
    board.ep_square = None
    board.castling_rights = board.clean_castling_rights()
    return [
        f"Teleport: {PIECE_NAMES[piece_a.piece_type].capitalize()} {chess.square_name(sq_a)} \u2194 "
        f"{PIECE_NAMES[piece_b.piece_type].capitalize()} {chess.square_name(sq_b)}."
    ]


def apply_mirror_follow(board: chess.Board, from_square: int) -> str:
    """Advance the opponent piece at from_square one square forward, if unobstructed."""
    piece = board.piece_at(from_square)
    if piece is None:
        return ""
    forward_dir = 1 if piece.color == chess.WHITE else -1
    new_rank = chess.square_rank(from_square) + forward_dir
    new_file = chess.square_file(from_square)
    if not (0 <= new_rank < 8):
        return ""
    # Pawns reaching the back rank would need promotion — skip to keep the board valid.
    if piece.piece_type == chess.PAWN:
        back_rank = 7 if piece.color == chess.WHITE else 0
        if new_rank == back_rank:
            return ""
    to_square = chess.square(new_file, new_rank)
    if board.piece_at(to_square) is not None:
        return ""
    piece_name = PIECE_NAMES[piece.piece_type].capitalize()
    color_str = "White" if piece.color == chess.WHITE else "Black"
    apply_piece_shift(board, from_square, to_square)
    return (
        f"Mirror: {color_str} {piece_name} {chess.square_name(from_square)} \u2192 "
        f"{chess.square_name(to_square)}."
    )


def apply_slippery_follow(
    board: chess.Board,
    from_square: int,
    to_square: int,
) -> str:
    piece = board.piece_at(from_square)
    if piece is None:
        raise ValueError("No piece found to slide.")

    piece_name = PIECE_NAMES[piece.piece_type].capitalize()
    color_name = "White" if piece.color == chess.WHITE else "Black"
    apply_piece_shift(board, from_square, to_square)
    return (
        f"{color_name} {piece_name} slides from {chess.square_name(from_square)} "
        f"to {chess.square_name(to_square)}."
    )
