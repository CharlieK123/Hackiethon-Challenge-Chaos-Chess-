from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import chess


class ChaosEventType(str, Enum):
    GUST_OF_WIND = "gust_of_wind"
    LOCKED_SQUARES = "locked_squares"
    FROZEN_PIECE = "frozen_piece"
    SLIPPERY_SQUARE = "slippery_square"
    TELEPORT = "teleport"
    DOUBLE_MOVE = "double_move"
    PAWN_PROMOTION_BLOCK = "pawn_promotion_block"
    MIRROR_TURN = "mirror_turn"


@dataclass(slots=True, frozen=True)
class PieceShift:
    from_square: int
    to_square: int
    piece_type: int
    color: chess.Color


@dataclass(slots=True, frozen=True)
class ChaosEvent:
    event_type: ChaosEventType
    description: str
    duration_turns: int
    parameters: dict[str, Any]

    @property
    def title(self) -> str:
        return {
            ChaosEventType.GUST_OF_WIND: "Gust of Wind",
            ChaosEventType.LOCKED_SQUARES: "Locked Squares",
            ChaosEventType.FROZEN_PIECE: "Frozen Piece",
            ChaosEventType.SLIPPERY_SQUARE: "Slippery Square",
            ChaosEventType.TELEPORT: "Teleport",
            ChaosEventType.DOUBLE_MOVE: "Double Move",
            ChaosEventType.PAWN_PROMOTION_BLOCK: "Promotion Block",
            ChaosEventType.MIRROR_TURN: "Mirror Turn",
        }[self.event_type]

    @property
    def locked_squares(self) -> tuple[int, ...]:
        if self.event_type != ChaosEventType.LOCKED_SQUARES:
            return ()
        squares = self.parameters.get("squares", [])
        if not isinstance(squares, list):
            return ()
        return tuple(chess.parse_square(square) for square in squares if isinstance(square, str))

    @property
    def frozen_square(self) -> int | None:
        if self.event_type != ChaosEventType.FROZEN_PIECE:
            return None
        square = self.parameters.get("square")
        if not isinstance(square, str):
            return None
        return chess.parse_square(square)

    @property
    def slippery_square(self) -> int | None:
        if self.event_type != ChaosEventType.SLIPPERY_SQUARE:
            return None
        square = self.parameters.get("square")
        if not isinstance(square, str):
            return None
        return chess.parse_square(square)

    @property
    def wind_direction(self) -> int | None:
        if self.event_type != ChaosEventType.GUST_OF_WIND:
            return None
        direction = self.parameters.get("direction")
        if direction == "left":
            return -1
        if direction == "right":
            return 1
        return None

    @property
    def gust_shifts(self) -> tuple[PieceShift, ...]:
        if self.event_type != ChaosEventType.GUST_OF_WIND:
            return ()
        raw_shifts = self.parameters.get("shifts", [])
        if not isinstance(raw_shifts, list):
            return ()

        piece_lookup = {
            "pawn": chess.PAWN,
            "knight": chess.KNIGHT,
            "bishop": chess.BISHOP,
            "rook": chess.ROOK,
            "queen": chess.QUEEN,
            "king": chess.KING,
        }
        color_lookup = {
            "white": chess.WHITE,
            "black": chess.BLACK,
        }

        shifts: list[PieceShift] = []
        for raw_shift in raw_shifts:
            if not isinstance(raw_shift, dict):
                continue
            from_square = raw_shift.get("from_square")
            to_square = raw_shift.get("to_square")
            piece_type = raw_shift.get("piece_type")
            color = raw_shift.get("color")
            if (
                not isinstance(from_square, str)
                or not isinstance(to_square, str)
                or not isinstance(piece_type, str)
                or not isinstance(color, str)
                or piece_type not in piece_lookup
                or color not in color_lookup
            ):
                continue
            shifts.append(
                PieceShift(
                    from_square=chess.parse_square(from_square),
                    to_square=chess.parse_square(to_square),
                    piece_type=piece_lookup[piece_type],
                    color=color_lookup[color],
                )
            )
        return tuple(shifts)

    @property
    def teleport_squares(self) -> tuple[int, int] | None:
        if self.event_type != ChaosEventType.TELEPORT:
            return None
        sq_a = self.parameters.get("square_a")
        sq_b = self.parameters.get("square_b")
        if not isinstance(sq_a, str) or not isinstance(sq_b, str):
            return None
        return chess.parse_square(sq_a), chess.parse_square(sq_b)

    @property
    def mirror_square(self) -> int | None:
        if self.event_type != ChaosEventType.MIRROR_TURN:
            return None
        square = self.parameters.get("square")
        if not isinstance(square, str):
            return None
        return chess.parse_square(square)
