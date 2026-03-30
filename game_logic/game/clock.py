from __future__ import annotations

import time
from collections.abc import Callable

import chess


class ChessClock:
    """Simple 5+0 style chess clock driven by a monotonic time source."""

    def __init__(
        self,
        initial_time_ms: int,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        self._time_source = time_source or time.monotonic
        self._initial_time_ms = initial_time_ms
        self._remaining_ms = {
            chess.WHITE: initial_time_ms,
            chess.BLACK: initial_time_ms,
        }
        self._active_color: chess.Color | None = None
        self._last_tick: float | None = None
        self._running = False

    def resume(self, active_color: chess.Color) -> None:
        if self._running:
            return
        self._active_color = active_color
        self._last_tick = self._time_source()
        self._running = True

    def pause(self) -> None:
        if not self._running:
            return
        self.update()
        self._running = False
        self._last_tick = None

    def switch_turn(self, active_color: chess.Color) -> None:
        self.update()
        self._active_color = active_color
        self._last_tick = self._time_source()
        self._running = True

    def update(self) -> None:
        if not self._running or self._active_color is None or self._last_tick is None:
            return

        now = self._time_source()
        elapsed_ms = int((now - self._last_tick) * 1000)
        if elapsed_ms <= 0:
            return

        remaining = self._remaining_ms[self._active_color] - elapsed_ms
        self._remaining_ms[self._active_color] = max(0, remaining)
        self._last_tick = now

    @property
    def initial_time_ms(self) -> int:
        return self._initial_time_ms

    def remaining_ms(self, color: chess.Color) -> int:
        return self._remaining_ms[color]

    def flagged_color(self) -> chess.Color | None:
        for color in (chess.WHITE, chess.BLACK):
            if self._remaining_ms[color] <= 0:
                return color
        return None

    @property
    def active_color(self) -> chess.Color | None:
        return self._active_color
