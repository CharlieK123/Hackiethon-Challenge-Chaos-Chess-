from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

import chess


class BotUnavailableError(RuntimeError):
    """Raised when a bot backend cannot provide a move."""


class BotMode(str, Enum):
    AUTO = "auto"
    SIMPLE = "simple"
    STOCKFISH = "stockfish"

    @classmethod
    def parse(cls, value: str | None) -> "BotMode":
        if value is None:
            return cls.AUTO

        normalized = value.strip().lower()
        for mode in cls:
            if mode.value == normalized:
                return mode
        return cls.AUTO


@dataclass(slots=True, frozen=True)
class BotConfig:
    mode: BotMode = BotMode.AUTO
    stockfish_path: str | None = None
    stockfish_think_time_seconds: float = 0.2
    fallback_randomness: float = 18.0
    seed: int | None = None


class BotStrategy(ABC):
    """Abstract interface for pluggable chess bots."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def choose_move(
        self,
        board: chess.Board,
        legal_moves: list[chess.Move] | None = None,
    ) -> chess.Move:
        raise NotImplementedError

    def close(self) -> None:
        """Release external resources, if the bot owns any."""
