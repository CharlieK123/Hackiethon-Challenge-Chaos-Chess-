from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import chess


class GamePhase(str, Enum):
    HUMAN_TURN = "human_turn"
    BOT_TURN = "bot_turn"
    CHAOS_PENDING = "chaos_pending"
    PROMOTION_PENDING = "promotion_pending"
    GAME_OVER = "game_over"


class GameMode(str, Enum):
    HUMAN_VS_BOT = "human_vs_bot"
    LOCAL_PVP = "local_pvp"
    BOT_VS_BOT = "bot_vs_bot"


@dataclass(slots=True, frozen=True)
class GameResult:
    winner: chess.Color | None
    reason: str
    message: str


@dataclass(slots=True)
class PromotionPrompt:
    from_square: int
    to_square: int
    options: dict[int, chess.Move]
