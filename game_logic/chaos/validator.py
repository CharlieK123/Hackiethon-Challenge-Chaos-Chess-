from __future__ import annotations

from collections.abc import Iterable, Mapping

import chess

from chaos_chess.chaos.applier import apply_piece_shift
from chaos_chess.chaos.models import ChaosEvent, ChaosEventType
from chaos_chess.chaos.schemas import ChaosSchemaValidator


class ChaosValidator:
    """Validation helpers for turn-scoped chaos effects."""

    @staticmethod
    def validate_payload(
        board: chess.Board,
        payload: Mapping[str, object],
    ) -> ChaosEvent | None:
        event = ChaosSchemaValidator.validate(payload)
        if event is None:
            return None
        if not ChaosValidator.validate_event(board, event):
            return None
        return event

    @staticmethod
    def filter_moves(
        board: chess.Board,
        moves: Iterable[chess.Move],
        event: ChaosEvent | None,
    ) -> list[chess.Move]:
        if event is None:
            return list(moves)

        allowed: list[chess.Move] = []
        for move in moves:
            if event.event_type == ChaosEventType.LOCKED_SQUARES:
                if move.to_square in event.locked_squares:
                    continue
            elif event.event_type == ChaosEventType.FROZEN_PIECE:
                if move.from_square == event.frozen_square:
                    continue
            elif event.event_type == ChaosEventType.PAWN_PROMOTION_BLOCK:
                if move.promotion is not None:
                    continue

            allowed.append(move)
        return allowed

    @staticmethod
    def validate_event(board: chess.Board, event: ChaosEvent) -> bool:
        if event.event_type == ChaosEventType.LOCKED_SQUARES:
            return ChaosValidator._validate_locked_squares(board, event)
        if event.event_type == ChaosEventType.FROZEN_PIECE:
            return ChaosValidator._validate_frozen_piece(board, event)
        if event.event_type == ChaosEventType.SLIPPERY_SQUARE:
            return ChaosValidator._validate_slippery_square(board, event)
        if event.event_type == ChaosEventType.GUST_OF_WIND:
            return ChaosValidator._validate_gust(board, event)
        if event.event_type == ChaosEventType.TELEPORT:
            return ChaosValidator._validate_teleport(board, event)
        if event.event_type == ChaosEventType.DOUBLE_MOVE:
            return ChaosValidator._validate_double_move(board, event)
        if event.event_type == ChaosEventType.PAWN_PROMOTION_BLOCK:
            return ChaosValidator._validate_pawn_promotion_block(board, event)
        if event.event_type == ChaosEventType.MIRROR_TURN:
            return ChaosValidator._validate_mirror_turn(board, event)
        return False

    @staticmethod
    def slippery_destination(
        board: chess.Board,
        move: chess.Move,
        event: ChaosEvent | None,
    ) -> int | None:
        if event is None or event.event_type != ChaosEventType.SLIPPERY_SQUARE:
            return None
        if event.slippery_square != move.to_square:
            return None
        return ChaosValidator.preview_slippery_destination(board, move)

    @staticmethod
    def preview_slippery_destination(board: chess.Board, move: chess.Move) -> int | None:
        delta_file = chess.square_file(move.to_square) - chess.square_file(move.from_square)
        delta_rank = chess.square_rank(move.to_square) - chess.square_rank(move.from_square)
        step_file = _sign(delta_file)
        step_rank = _sign(delta_rank)
        if step_file == 0 and step_rank == 0:
            return None

        next_file = chess.square_file(move.to_square) + step_file
        next_rank = chess.square_rank(move.to_square) + step_rank
        if not (0 <= next_file < 8 and 0 <= next_rank < 8):
            return None

        preview = board.copy(stack=False)
        preview.push(move)
        next_square = chess.square(next_file, next_rank)
        if preview.piece_at(next_square) is not None:
            return None

        try:
            apply_piece_shift(preview, move.to_square, next_square)
        except ValueError:
            return None

        if not preview.is_valid():
            return None

        return next_square

    @staticmethod
    def _validate_locked_squares(board: chess.Board, event: ChaosEvent) -> bool:
        squares = event.locked_squares
        if not 1 <= len(squares) <= 3:
            return False
        if len(set(squares)) != len(squares):
            return False

        moves = ChaosValidator.filter_moves(board, board.legal_moves, event)
        return bool(moves)

    @staticmethod
    def _validate_frozen_piece(board: chess.Board, event: ChaosEvent) -> bool:
        if event.frozen_square is None:
            return False

        piece = board.piece_at(event.frozen_square)
        if piece is None or piece.color != board.turn or piece.piece_type == chess.KING:
            return False

        moves = ChaosValidator.filter_moves(board, board.legal_moves, event)
        return bool(moves)

    @staticmethod
    def _validate_slippery_square(board: chess.Board, event: ChaosEvent) -> bool:
        if event.slippery_square is None:
            return False

        square = event.slippery_square
        if board.piece_at(square) is not None:
            return False

        for move in board.legal_moves:
            if move.to_square != square:
                continue
            if ChaosValidator.preview_slippery_destination(board, move) is not None:
                return True
        return False

    @staticmethod
    def _validate_gust(board: chess.Board, event: ChaosEvent) -> bool:
        if event.wind_direction not in (-1, 1):
            return False
        if not event.gust_shifts:
            return False

        preview = board.copy(stack=False)
        used_squares: set[int] = set()
        for shift in event.gust_shifts:
            if shift.from_square in used_squares or shift.to_square in used_squares:
                return False

            piece = preview.piece_at(shift.from_square)
            if piece is None or piece.color != shift.color or piece.piece_type != shift.piece_type:
                return False

            expected_file = chess.square_file(shift.from_square) + event.wind_direction
            if not (0 <= expected_file < 8):
                return False

            expected_square = chess.square(expected_file, chess.square_rank(shift.from_square))
            if expected_square != shift.to_square or preview.piece_at(shift.to_square) is not None:
                return False

            try:
                apply_piece_shift(preview, shift.from_square, shift.to_square)
            except ValueError:
                return False

            used_squares.add(shift.from_square)
            used_squares.add(shift.to_square)

        if not preview.is_valid():
            return False

        return bool(list(preview.legal_moves))


    @staticmethod
    def _validate_teleport(board: chess.Board, event: ChaosEvent) -> bool:
        squares = event.teleport_squares
        if squares is None:
            return False
        sq_a, sq_b = squares
        if sq_a == sq_b:
            return False
        piece_a = board.piece_at(sq_a)
        piece_b = board.piece_at(sq_b)
        if piece_a is None or piece_b is None:
            return False
        if piece_a.color != board.turn or piece_b.color != board.turn:
            return False
        if piece_a.piece_type == chess.KING or piece_b.piece_type == chess.KING:
            return False
        preview = board.copy(stack=False)
        preview.remove_piece_at(sq_a)
        preview.remove_piece_at(sq_b)
        preview.set_piece_at(sq_a, piece_b)
        preview.set_piece_at(sq_b, piece_a)
        preview.ep_square = None
        preview.castling_rights = preview.clean_castling_rights()
        return preview.is_valid() and bool(list(preview.legal_moves))

    @staticmethod
    def _validate_double_move(board: chess.Board, event: ChaosEvent) -> bool:
        return bool(list(board.legal_moves))

    @staticmethod
    def _validate_pawn_promotion_block(board: chess.Board, event: ChaosEvent) -> bool:
        has_promotion = False
        has_non_promotion = False
        for move in board.legal_moves:
            if move.promotion is not None:
                has_promotion = True
            else:
                has_non_promotion = True
            if has_promotion and has_non_promotion:
                break
        return has_promotion and has_non_promotion

    @staticmethod
    def _validate_mirror_turn(board: chess.Board, event: ChaosEvent) -> bool:
        sq = event.mirror_square
        if sq is None:
            return False
        piece = board.piece_at(sq)
        if piece is None:
            return False
        if piece.color == board.turn:
            return False
        if piece.piece_type == chess.KING:
            return False
        forward_dir = 1 if piece.color == chess.WHITE else -1
        new_rank = chess.square_rank(sq) + forward_dir
        if not (0 <= new_rank < 8):
            return False
        if piece.piece_type == chess.PAWN:
            back_rank = 7 if piece.color == chess.WHITE else 0
            if new_rank == back_rank:
                return False
        to_square = chess.square(chess.square_file(sq), new_rank)
        if board.piece_at(to_square) is not None:
            return False
        preview = board.copy(stack=False)
        apply_piece_shift(preview, sq, to_square)
        return preview.is_valid()


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0
