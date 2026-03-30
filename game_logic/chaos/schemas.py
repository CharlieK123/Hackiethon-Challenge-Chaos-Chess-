from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypedDict

import chess

from chaos_chess.chaos.models import ChaosEvent, ChaosEventType


class RawGustShift(TypedDict):
    from_square: str
    to_square: str
    piece_type: str
    color: str


class RawGustParameters(TypedDict):
    direction: Literal["left", "right"]
    targets: Literal["non_king_pieces"]
    shifts: list[RawGustShift]


class RawLockedSquaresParameters(TypedDict):
    squares: list[str]


class RawFrozenPieceParameters(TypedDict):
    square: str
    piece_type: str
    color: str


class RawSlipperySquareParameters(TypedDict):
    square: str


class RawTeleportParameters(TypedDict):
    square_a: str
    square_b: str


class RawMirrorTurnParameters(TypedDict):
    square: str


class RawChaosEvent(TypedDict):
    event_type: str
    description: str
    duration_turns: int
    parameters: dict[str, object]


PIECE_TYPE_NAMES = {
    "pawn": chess.PAWN,
    "knight": chess.KNIGHT,
    "bishop": chess.BISHOP,
    "rook": chess.ROOK,
    "queen": chess.QUEEN,
    "king": chess.KING,
}

COLOR_NAMES = {
    "white": chess.WHITE,
    "black": chess.BLACK,
}


class ChaosSchemaValidator:
    """Validate JSON-like event payloads and normalize them into structured events."""

    REQUIRED_KEYS = {"event_type", "description", "duration_turns", "parameters"}

    @classmethod
    def validate(cls, payload: Mapping[str, object]) -> ChaosEvent | None:
        try:
            return cls._parse(payload)
        except (TypeError, ValueError, KeyError):
            return None

    @classmethod
    def _parse(cls, payload: Mapping[str, object]) -> ChaosEvent:
        if set(payload.keys()) != cls.REQUIRED_KEYS:
            raise ValueError("Unexpected event keys.")

        raw_event_type = cls._require_string(payload, "event_type")
        description = cls._require_string(payload, "description")
        duration_turns = cls._require_int(payload, "duration_turns")
        if duration_turns < 1:
            raise ValueError("duration_turns must be positive.")

        event_type = ChaosEventType(raw_event_type)
        parameters = cls._require_mapping(payload, "parameters")
        normalized_parameters = cls._validate_parameters(event_type, parameters)

        return ChaosEvent(
            event_type=event_type,
            description=description,
            duration_turns=duration_turns,
            parameters=normalized_parameters,
        )

    @classmethod
    def _validate_parameters(
        cls,
        event_type: ChaosEventType,
        parameters: Mapping[str, object],
    ) -> dict[str, object]:
        if event_type == ChaosEventType.GUST_OF_WIND:
            return cls._validate_gust_parameters(parameters)
        if event_type == ChaosEventType.LOCKED_SQUARES:
            return cls._validate_locked_squares_parameters(parameters)
        if event_type == ChaosEventType.FROZEN_PIECE:
            return cls._validate_frozen_piece_parameters(parameters)
        if event_type == ChaosEventType.SLIPPERY_SQUARE:
            return cls._validate_slippery_square_parameters(parameters)
        if event_type == ChaosEventType.TELEPORT:
            return cls._validate_teleport_parameters(parameters)
        if event_type == ChaosEventType.DOUBLE_MOVE:
            return cls._validate_double_move_parameters(parameters)
        if event_type == ChaosEventType.PAWN_PROMOTION_BLOCK:
            return cls._validate_pawn_promotion_block_parameters(parameters)
        if event_type == ChaosEventType.MIRROR_TURN:
            return cls._validate_mirror_turn_parameters(parameters)
        raise ValueError("Unsupported chaos event type.")

    @classmethod
    def _validate_gust_parameters(cls, parameters: Mapping[str, object]) -> dict[str, object]:
        cls._require_exact_keys(parameters, {"direction", "targets", "shifts"})
        direction = cls._require_string(parameters, "direction")
        targets = cls._require_string(parameters, "targets")
        shifts = cls._require_list(parameters, "shifts")

        if direction not in {"left", "right"}:
            raise ValueError("Invalid gust direction.")
        if targets != "non_king_pieces":
            raise ValueError("Invalid gust target selector.")
        if not shifts:
            raise ValueError("Gust requires at least one shift.")

        normalized_shifts: list[dict[str, str]] = []
        for raw_shift in shifts:
            if not isinstance(raw_shift, Mapping):
                raise ValueError("Invalid shift payload.")
            cls._require_exact_keys(raw_shift, {"from_square", "to_square", "piece_type", "color"})
            from_square = cls._require_square_name(raw_shift, "from_square")
            to_square = cls._require_square_name(raw_shift, "to_square")
            piece_type = cls._require_piece_name(raw_shift, "piece_type")
            color = cls._require_color_name(raw_shift, "color")
            normalized_shifts.append(
                {
                    "from_square": from_square,
                    "to_square": to_square,
                    "piece_type": piece_type,
                    "color": color,
                }
            )

        return {
            "direction": direction,
            "targets": targets,
            "shifts": normalized_shifts,
        }

    @classmethod
    def _validate_locked_squares_parameters(
        cls,
        parameters: Mapping[str, object],
    ) -> dict[str, object]:
        cls._require_exact_keys(parameters, {"squares"})
        raw_squares = cls._require_list(parameters, "squares")
        if not 1 <= len(raw_squares) <= 3:
            raise ValueError("Locked squares event must have 1 to 3 squares.")

        squares = [cls._coerce_square_name(value) for value in raw_squares]
        if len(set(squares)) != len(squares):
            raise ValueError("Locked squares must be unique.")
        return {"squares": squares}

    @classmethod
    def _validate_frozen_piece_parameters(
        cls,
        parameters: Mapping[str, object],
    ) -> dict[str, object]:
        cls._require_exact_keys(parameters, {"square", "piece_type", "color"})
        return {
            "square": cls._require_square_name(parameters, "square"),
            "piece_type": cls._require_piece_name(parameters, "piece_type"),
            "color": cls._require_color_name(parameters, "color"),
        }

    @classmethod
    def _validate_slippery_square_parameters(
        cls,
        parameters: Mapping[str, object],
    ) -> dict[str, object]:
        cls._require_exact_keys(parameters, {"square"})
        return {"square": cls._require_square_name(parameters, "square")}

    @classmethod
    def _validate_teleport_parameters(
        cls,
        parameters: Mapping[str, object],
    ) -> dict[str, object]:
        cls._require_exact_keys(parameters, {"square_a", "square_b"})
        sq_a = cls._require_square_name(parameters, "square_a")
        sq_b = cls._require_square_name(parameters, "square_b")
        if sq_a == sq_b:
            raise ValueError("Teleport squares must be different.")
        return {"square_a": sq_a, "square_b": sq_b}

    @classmethod
    def _validate_double_move_parameters(
        cls,
        parameters: Mapping[str, object],
    ) -> dict[str, object]:
        cls._require_exact_keys(parameters, set())
        return {}

    @classmethod
    def _validate_pawn_promotion_block_parameters(
        cls,
        parameters: Mapping[str, object],
    ) -> dict[str, object]:
        cls._require_exact_keys(parameters, set())
        return {}

    @classmethod
    def _validate_mirror_turn_parameters(
        cls,
        parameters: Mapping[str, object],
    ) -> dict[str, object]:
        cls._require_exact_keys(parameters, {"square"})
        return {"square": cls._require_square_name(parameters, "square")}

    @staticmethod
    def _require_exact_keys(parameters: Mapping[str, object], expected_keys: set[str]) -> None:
        if set(parameters.keys()) != expected_keys:
            raise ValueError("Unexpected parameter keys.")

    @staticmethod
    def _require_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
        value = payload.get(key)
        if not isinstance(value, Mapping):
            raise TypeError(f"{key} must be an object.")
        return value

    @staticmethod
    def _require_list(payload: Mapping[str, object], key: str) -> list[object]:
        value = payload.get(key)
        if not isinstance(value, list):
            raise TypeError(f"{key} must be a list.")
        return value

    @staticmethod
    def _require_string(payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"{key} must be a non-empty string.")
        return value.strip()

    @staticmethod
    def _require_int(payload: Mapping[str, object], key: str) -> int:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{key} must be an integer.")
        return value

    @classmethod
    def _require_square_name(cls, payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        return cls._coerce_square_name(value)

    @classmethod
    def _require_piece_name(cls, payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str):
            raise TypeError(f"{key} must be a string.")
        normalized = value.strip().lower()
        if normalized not in PIECE_TYPE_NAMES:
            raise ValueError("Invalid piece_type.")
        return normalized

    @classmethod
    def _require_color_name(cls, payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str):
            raise TypeError(f"{key} must be a string.")
        normalized = value.strip().lower()
        if normalized not in COLOR_NAMES:
            raise ValueError("Invalid color.")
        return normalized

    @staticmethod
    def _coerce_square_name(value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("Square must be a string.")
        normalized = value.strip().lower()
        chess.parse_square(normalized)
        return normalized
