from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import chess

from chaos_chess.chaos.models import ChaosEvent
from chaos_chess.game.types import GamePhase, GameResult, PromotionPrompt


@dataclass(slots=True)
class GameState:
    """Mutable match state shared across the UI and session layer."""

    board: chess.Board = field(default_factory=chess.Board)
    phase: GamePhase = GamePhase.HUMAN_TURN
    selected_square: int | None = None
    legal_targets: set[int] = field(default_factory=set)
    last_move_from: int | None = None
    last_move_to: int | None = None
    pending_promotion: PromotionPrompt | None = None
    move_history: list[str] = field(default_factory=list)
    active_event: ChaosEvent | None = None
    active_event_turns_remaining: int = 0
    chaos_log: deque[str] = field(default_factory=lambda: deque(maxlen=8))
    result: GameResult | None = None
    revision: int = 0
    double_move_remaining: int = 0

    def clear_selection(self) -> None:
        self.selected_square = None
        self.legal_targets.clear()
