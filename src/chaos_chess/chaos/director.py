from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import random

import chess

from chaos_chess.chaos.applier import apply_gust, apply_teleport
from chaos_chess.chaos.engine import LocalChaosProvider
from chaos_chess.chaos.models import ChaosEvent, ChaosEventType
from chaos_chess.chaos.personality import ChaosDirectorPersonality
from chaos_chess.chaos.provider import ChaosEventProvider
from chaos_chess.chaos.validator import ChaosValidator
from chaos_chess.game.state import GameState

CHAOS_INTERVAL_MIN = 3
CHAOS_INTERVAL_MAX = 5


@dataclass(slots=True, frozen=True)
class ChaosDirectorConfig:
    mode: str = "hybrid"
    seed: int | None = None
    frequency_preset: str = "normal"  # "calm", "normal", or "mayhem"


@dataclass(slots=True, frozen=True)
class _ResolvedChaosEvent:
    event: ChaosEvent | None
    warning: str | None
    source: str


@dataclass(slots=True)
class _PendingChaosRequest:
    future: Future[_ResolvedChaosEvent]
    revision: int


class ChaosDirector:
    """Coordinates event timing, async Claude requests, and local fallback."""

    def __init__(
        self,
        *,
        local_provider: ChaosEventProvider | None = None,
        remote_provider: ChaosEventProvider | None = None,
        config: ChaosDirectorConfig | None = None,
    ) -> None:
        self._config = config or ChaosDirectorConfig()
        self._mode = self._normalize_mode(self._config.mode)
        self._local_provider = local_provider or LocalChaosProvider(seed=self._config.seed)
        self._remote_provider = remote_provider
        self._rng = random.Random(self._config.seed)
        self._current_pressure: float = 0.0
        self._personality = ChaosDirectorPersonality()
        self._turns_until_next_event = self._roll_interval()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chaos-director")
        self._pending_request: _PendingChaosRequest | None = None

    @property
    def turns_until_next_event(self) -> int:
        return self._turns_until_next_event

    @property
    def is_pending(self) -> bool:
        return self._pending_request is not None

    @property
    def is_enabled(self) -> bool:
        return self._mode != "disabled"

    @property
    def is_remote_enabled(self) -> bool:
        return self._mode == "hybrid"

    @property
    def is_remote_available(self) -> bool:
        return self._remote_provider is not None and self._remote_provider.is_configured()

    @property
    def chaos_level(self) -> int:
        """Integer 1–4 mapped from current clock pressure."""
        p = self._current_pressure
        if p > 0.8:
            return 4
        if p > 0.6:
            return 3
        if p >= 0.3:
            return 2
        return 1

    def filtered_legal_moves(
        self,
        board: chess.Board,
        active_event: ChaosEvent | None,
    ) -> list[chess.Move]:
        return ChaosValidator.filter_moves(board, board.legal_moves, active_event)

    def slippery_destination(
        self,
        board: chess.Board,
        move: chess.Move,
        active_event: ChaosEvent | None,
    ) -> int | None:
        return ChaosValidator.slippery_destination(board, move, active_event)

    def mirror_square(self, active_event: ChaosEvent | None) -> int | None:
        if active_event is None or active_event.event_type != ChaosEventType.MIRROR_TURN:
            return None
        return active_event.mirror_square

    def complete_turn(self, state: GameState, clock=None) -> bool:
        """Advance one turn. Pass the ChessClock to enable pressure-based escalation."""
        self._expire_active_event(state)

        # Update personality and pressure every turn regardless of event timing.
        self._personality.record_turn(state.board)
        self._current_pressure = self._clock_pressure(clock)

        if not self.is_enabled:
            return False

        if state.result is not None or state.active_event is not None:
            return False

        self._turns_until_next_event -= 1
        if self._turns_until_next_event > 0:
            return False

        self._turns_until_next_event = self._roll_interval()

        # Push current context to providers before any generation.
        self._local_provider.set_context(chaos_level=self.chaos_level)
        if self._remote_provider is not None:
            self._remote_provider.set_context(
                personality=self._personality,
                chaos_level=self.chaos_level,
            )

        if not self._should_request_remote():
            self._apply_resolution(
                state,
                self._generate_local_resolution(state.board.copy(stack=False)),
            )
            return False

        board_snapshot = state.board.copy(stack=False)
        self._pending_request = _PendingChaosRequest(
            future=self._executor.submit(self._resolve_event, board_snapshot),
            revision=state.revision,
        )
        return True

    def poll(self, state: GameState) -> bool:
        request = self._pending_request
        if request is None or not request.future.done():
            return False

        self._pending_request = None
        if request.revision != state.revision:
            resolution = self._generate_local_resolution(
                state.board.copy(stack=False),
                warning="Chaos Director result arrived for an outdated position. Using local chaos instead.",
            )
            self._apply_resolution(state, resolution)
            return True

        try:
            resolution = request.future.result()
        except Exception:
            resolution = self._generate_local_resolution(
                state.board.copy(stack=False),
                warning="Claude Chaos Director failed unexpectedly. Using local chaos instead.",
            )

        self._apply_resolution(state, resolution)
        return True

    def record_message(self, state: GameState, message: str) -> None:
        self._append_log(state, message)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _resolve_event(self, board: chess.Board) -> _ResolvedChaosEvent:
        warning: str | None = None
        if self._should_request_remote():
            remote_response = self._remote_provider.generate_event(board)  # type: ignore[union-attr]
            if remote_response.event is not None:
                return _ResolvedChaosEvent(
                    event=remote_response.event,
                    warning=remote_response.warning,
                    source="claude",
                )
            warning = remote_response.warning

        return self._generate_local_resolution(board, warning=warning)

    def _generate_local_resolution(
        self,
        board: chess.Board,
        warning: str | None = None,
    ) -> _ResolvedChaosEvent:
        response = self._local_provider.generate_event(board)
        return _ResolvedChaosEvent(
            event=response.event,
            warning=warning or response.warning,
            source="local",
        )

    def _apply_resolution(self, state: GameState, resolution: _ResolvedChaosEvent) -> None:
        if resolution.warning:
            self._append_log(state, resolution.warning)

        if resolution.event is None:
            self._append_log(state, "The chaos fizzles out this turn.")
            return

        state.active_event = resolution.event
        state.active_event_turns_remaining = resolution.event.duration_turns
        if resolution.event.event_type == ChaosEventType.GUST_OF_WIND:
            apply_gust(state.board, resolution.event)
        elif resolution.event.event_type == ChaosEventType.TELEPORT:
            apply_teleport(state.board, resolution.event)
        elif resolution.event.event_type == ChaosEventType.DOUBLE_MOVE:
            state.double_move_remaining = 2
        self._personality.record_event(resolution.event)
        self._append_log(state, resolution.event.description)

    def _expire_active_event(self, state: GameState) -> None:
        if state.active_event is None:
            return

        state.active_event_turns_remaining = max(0, state.active_event_turns_remaining - 1)
        if state.active_event_turns_remaining <= 0:
            state.active_event = None

    def _append_log(self, state: GameState, message: str) -> None:
        state.chaos_log.append(message)

    def _should_request_remote(self) -> bool:
        return (
            self._mode == "hybrid"
            and self._remote_provider is not None
            and self._remote_provider.is_configured()
        )

    def _clock_pressure(self, clock) -> float:
        """Returns 0.0 (calm) to 1.0 (critical) based on how little time remains."""
        if clock is None:
            return 0.0
        try:
            white_ms = clock.remaining_ms(chess.WHITE)
            black_ms = clock.remaining_ms(chess.BLACK)
            initial = clock.initial_time_ms
        except Exception:
            return 0.0
        if initial <= 0:
            return 0.0
        min_remaining = min(white_ms, black_ms)
        if min_remaining / initial > 0.8:
            return 0.0
        return max(0.0, min(1.0, 1.0 - min_remaining / initial))

    def _roll_interval(self) -> int:
        from chaos_chess.config import CHAOS_FREQUENCY_RANGES
        base_min, base_max = CHAOS_FREQUENCY_RANGES.get(
            self._config.frequency_preset, CHAOS_FREQUENCY_RANGES["normal"]
        )
        p = self._current_pressure
        if p > 0.8:
            adj = -2
        elif p > 0.6:
            adj = -1
        elif p >= 0.3:
            adj = 0
        else:
            adj = 1
        lo = max(1, base_min + adj)
        hi = max(lo, base_max + adj)
        return self._rng.randint(lo, hi)

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized == "disabled":
            return "disabled"
        if normalized == "local":
            return "local"
        return "hybrid"
