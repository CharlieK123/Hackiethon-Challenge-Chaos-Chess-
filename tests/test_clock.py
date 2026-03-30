from __future__ import annotations

import chess

from chaos_chess.game.clock import ChessClock


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_clock_counts_down_active_side_only() -> None:
    fake_time = FakeTime()
    clock = ChessClock(initial_time_ms=1_000, time_source=fake_time)

    clock.resume(chess.WHITE)
    fake_time.advance(0.25)
    clock.update()

    assert clock.remaining_ms(chess.WHITE) == 750
    assert clock.remaining_ms(chess.BLACK) == 1_000


def test_clock_switches_turns() -> None:
    fake_time = FakeTime()
    clock = ChessClock(initial_time_ms=1_000, time_source=fake_time)

    clock.resume(chess.WHITE)
    fake_time.advance(0.2)
    clock.switch_turn(chess.BLACK)
    fake_time.advance(0.1)
    clock.update()

    assert clock.remaining_ms(chess.WHITE) == 800
    assert clock.remaining_ms(chess.BLACK) == 900
