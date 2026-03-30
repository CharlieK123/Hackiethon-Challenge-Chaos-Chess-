from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import chess

if TYPE_CHECKING:
    from chaos_chess.chaos.models import ChaosEvent

_PIECE_VALUES: dict[int, int] = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 300,
    chess.ROOK: 500,
    chess.QUEEN: 900,
}

_WINDOW = 6  # turns of material history used for dominance analysis


def _material_balance(board: chess.Board) -> int:
    """White material minus black material in centipawns (kings excluded)."""
    total = 0
    for piece_type, value in _PIECE_VALUES.items():
        total += len(board.pieces(piece_type, chess.WHITE)) * value
        total -= len(board.pieces(piece_type, chess.BLACK)) * value
    return total


@dataclass
class ChaosDirectorPersonality:
    """Tracks game-wide history so Claude can make contextually aware decisions."""

    events_fired: list[dict] = field(default_factory=list)
    material_history: list[int] = field(default_factory=list)
    turn_count: int = 0

    @property
    def dominant_color(self) -> str:
        """Returns 'white', 'black', or 'balanced' based on recent material trend."""
        recent = self.material_history[-_WINDOW:]
        if len(recent) < 3:
            return "balanced"
        avg = sum(recent) / len(recent)
        if avg > 50:
            return "white"
        if avg < -50:
            return "black"
        return "balanced"

    def record_turn(self, board: chess.Board) -> None:
        """Call once per turn to update material history and turn counter."""
        self.turn_count += 1
        self.material_history.append(_material_balance(board))

    def record_event(self, event: ChaosEvent) -> None:
        """Call when a chaos event is applied to the board."""
        self.events_fired.append({
            "event_type": event.event_type.value,
            "description": event.description,
            "turn": self.turn_count,
        })

    def to_prompt_context(self) -> str:
        """Returns a formatted summary for inclusion in the Claude user prompt."""
        parts: list[str] = [f"Turn {self.turn_count}."]

        recent = self.material_history[-_WINDOW:]
        if len(recent) >= 3:
            avg = sum(recent) / len(recent)
            avg_pawns = avg / 100.0
            dominant = self.dominant_color
            if dominant != "balanced":
                dominant_count = sum(
                    1 for m in recent if (m > 50 if dominant == "white" else m < -50)
                )
                sign = "+" if avg_pawns > 0 else ""
                parts.append(
                    f"{dominant.capitalize()} has been dominant for {dominant_count} of the last "
                    f"{len(recent)} turns (avg {sign}{avg_pawns:.1f} material)."
                )
            else:
                parts.append("The game is balanced.")

        if self.events_fired:
            recent_events = self.events_fired[-5:]
            event_list = ", ".join(
                f"{e['event_type']} (turn {e['turn']})" for e in recent_events
            )
            parts.append(f"Previous chaos events: {event_list}.")
        else:
            parts.append("No chaos events have fired yet.")

        dominant = self.dominant_color
        if dominant != "balanced":
            parts.append("The game has been one-sided. Escalate disruption.")
        else:
            parts.append("The game is competitive. Add subtle pressure.")

        return " ".join(parts)
