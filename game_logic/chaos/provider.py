from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import chess

from chaos_chess.chaos.models import ChaosEvent


@dataclass(slots=True, frozen=True)
class ChaosProviderResponse:
    event: ChaosEvent | None
    warning: str | None = None


class ChaosEventProvider(ABC):
    """Abstract provider for locally or remotely generated chaos events."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    def is_configured(self) -> bool:
        return True

    def set_context(self, *, personality: object = None, chaos_level: int = 1) -> None:
        """Update provider context before the next generate_event call. No-op by default."""

    @abstractmethod
    def generate_event(self, board: chess.Board) -> ChaosProviderResponse:
        raise NotImplementedError
