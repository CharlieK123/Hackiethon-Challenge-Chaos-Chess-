from __future__ import annotations

import random

import chess

from chaos_chess.chaos.candidates import (
    build_gust_payload,
    frozen_piece_candidates,
    gust_shift_candidates,
    locked_square_candidates,
    slippery_square_candidates,
)
from chaos_chess.chaos.models import ChaosEventType
from chaos_chess.chaos.provider import ChaosEventProvider, ChaosProviderResponse
from chaos_chess.chaos.validator import ChaosValidator

# Locked-squares count ranges per chaos level.
_LOCKED_MIN = {1: 1, 2: 1, 3: 2, 4: 3}
_LOCKED_MAX = {1: 2, 2: 3, 3: 4, 4: 5}


class LocalChaosProvider(ChaosEventProvider):
    """Generates locally validated chaos events for the next turn."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._chaos_level: int = 1

    @property
    def name(self) -> str:
        return "Local Chaos Engine"

    def set_context(self, *, personality: object = None, chaos_level: int = 1) -> None:
        self._chaos_level = max(1, min(4, chaos_level))

    def generate_event(self, board: chess.Board) -> ChaosProviderResponse:
        return ChaosProviderResponse(event=self._generate_event(board))

    def _generate_event(self, board: chess.Board):
        generators = [
            self._generate_gust_of_wind,
            self._generate_locked_squares,
            self._generate_frozen_piece,
            self._generate_slippery_square,
        ]

        for _ in range(24):
            generator = self._rng.choice(generators)
            payload = generator(board)
            if payload is None:
                continue

            event = ChaosValidator.validate_payload(board, payload)
            if event is not None:
                return event

        return None

    def _generate_locked_squares(self, board: chess.Board):
        destinations = locked_square_candidates(board)
        if not destinations:
            return None

        level = self._chaos_level
        min_count = _LOCKED_MIN[level]
        desired_max = _LOCKED_MAX[level]
        max_count = min(desired_max, len(destinations))
        if max_count < min_count:
            return None

        count = self._rng.randint(min_count, max_count)
        chosen = sorted(self._rng.sample(destinations, min(count, len(destinations))))
        return {
            "event_type": ChaosEventType.LOCKED_SQUARES.value,
            "description": (
                f"Locked squares: {', '.join(chess.square_name(square) for square in chosen)}. "
                "No move may land there this turn."
            ),
            "duration_turns": 1,
            "parameters": {
                "squares": [chess.square_name(square) for square in chosen],
            },
        }

    def _generate_frozen_piece(self, board: chess.Board):
        candidates = frozen_piece_candidates(board)
        if not candidates:
            return None

        # At level 3+, attempt to express intent for two-piece freeze. The schema
        # only supports one piece, so validation will reject the two-piece payload
        # and the retry loop falls back to another generator or a single-piece freeze.
        if self._chaos_level >= 3 and len(candidates) >= 2 and self._rng.random() < 0.5:
            # Two-piece payload — will not pass ChaosSchemaValidator (intentional fallback).
            first, second = self._rng.sample(candidates, 2)
            return {
                "event_type": ChaosEventType.FROZEN_PIECE.value,
                "description": (
                    f"Two pieces frozen: {first['piece_type']} on {first['square']} "
                    f"and {second['piece_type']} on {second['square']} cannot move this turn."
                ),
                "duration_turns": 1,
                "parameters": {
                    "square": first["square"],
                    "square2": second["square"],  # non-schema field — triggers validation rejection
                    "piece_type": first["piece_type"],
                    "color": first["color"],
                },
            }

        chosen = self._rng.choice(candidates)
        return {
            "event_type": ChaosEventType.FROZEN_PIECE.value,
            "description": (
                f"Frozen piece: the {chosen['piece_type']} on "
                f"{chosen['square']} cannot move this turn."
            ),
            "duration_turns": 1,
            "parameters": {
                "square": chosen["square"],
                "piece_type": chosen["piece_type"],
                "color": chosen["color"],
            },
        }

    def _generate_slippery_square(self, board: chess.Board):
        candidates = slippery_square_candidates(board)
        if not candidates:
            return None

        square = self._rng.choice(candidates)
        return {
            "event_type": ChaosEventType.SLIPPERY_SQUARE.value,
            "description": (
                f"Slippery square: {chess.square_name(square)}. "
                "A piece landing there slides one extra square in the same direction if clear."
            ),
            "duration_turns": 1,
            "parameters": {
                "square": chess.square_name(square),
            },
        }

    def _generate_gust_of_wind(self, board: chess.Board):
        level = self._chaos_level
        direction = self._rng.choice((-1, 1))
        chosen_shifts: list[dict[str, str]] = []
        colors = [chess.WHITE, chess.BLACK]
        self._rng.shuffle(colors)

        for color in colors:
            candidates = gust_shift_candidates(board, direction, color)
            if not candidates:
                continue
            if level >= 4:
                # All eligible pieces swept by the gust.
                chosen_shifts.extend(candidates)
            elif level >= 3:
                # Up to two pieces per side.
                sample_count = min(2, len(candidates))
                chosen_shifts.extend(self._rng.sample(candidates, sample_count))
            else:
                chosen_shifts.append(self._rng.choice(candidates))

        if not chosen_shifts:
            return None

        # Deduplicate by from_square (in case of overlapping candidates).
        seen: set[str] = set()
        unique_shifts: list[dict[str, str]] = []
        for shift in chosen_shifts:
            key = shift["from_square"]
            if key not in seen:
                seen.add(key)
                unique_shifts.append(shift)
        chosen_shifts = unique_shifts

        direction_name = "left" if direction == -1 else "right"
        moves_text = ", ".join(
            f"{shift['color'].capitalize()} {shift['piece_type']} "
            f"{shift['from_square']} -> {shift['to_square']}"
            for shift in chosen_shifts
        )
        return build_gust_payload(
            direction,
            chosen_shifts,
            description=f"Gust of wind: pieces are blown one square {direction_name}. {moves_text}.",
        )
