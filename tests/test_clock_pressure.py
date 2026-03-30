from __future__ import annotations

import chess

from chaos_chess.chaos.director import ChaosDirector, ChaosDirectorConfig
from chaos_chess.game.clock import ChessClock


def _make_clock(initial_ms: int, white_ms: int, black_ms: int) -> ChessClock:
    """Build a clock with specific remaining times using the time_source injection."""
    tick = [0.0]

    def time_source() -> float:
        return tick[0]

    clock = ChessClock(initial_ms, time_source=time_source)
    # Drain white time: resume for white, advance tick, pause.
    clock.resume(chess.WHITE)
    tick[0] = (initial_ms - white_ms) / 1000.0
    clock.update()
    clock.pause()
    # Drain black time.
    clock.resume(chess.BLACK)
    tick[0] += (initial_ms - black_ms) / 1000.0
    clock.update()
    clock.pause()
    return clock


def _make_director() -> ChaosDirector:
    return ChaosDirector(config=ChaosDirectorConfig(mode="local"))


# ---------------------------------------------------------------------------
# _clock_pressure
# ---------------------------------------------------------------------------


def test_clock_pressure_zero_when_no_clock() -> None:
    director = _make_director()
    assert director._clock_pressure(None) == 0.0


def test_clock_pressure_zero_when_both_players_above_80_percent() -> None:
    initial = 300_000  # 5 minutes
    clock = _make_clock(initial, white_ms=290_000, black_ms=280_000)
    director = _make_director()
    # min remaining is 280_000 / 300_000 = 93% → above 80% threshold
    assert director._clock_pressure(clock) == 0.0


def test_clock_pressure_nonzero_when_one_player_below_80_percent() -> None:
    initial = 300_000
    clock = _make_clock(initial, white_ms=200_000, black_ms=60_000)
    director = _make_director()
    # min remaining is 60_000 / 300_000 = 20% → pressure = 1 - 0.2 = 0.8
    pressure = director._clock_pressure(clock)
    assert abs(pressure - 0.8) < 0.01


def test_clock_pressure_high_when_nearly_flagged() -> None:
    initial = 300_000
    clock = _make_clock(initial, white_ms=5_000, black_ms=250_000)
    director = _make_director()
    # min remaining is 5_000 / 300_000 ≈ 1.7% → pressure ≈ 0.983
    pressure = director._clock_pressure(clock)
    assert pressure > 0.95


def test_clock_pressure_clamped_to_one() -> None:
    initial = 300_000
    # Simulate 0 ms remaining (would be caught by flagged logic in session, but pressure should clamp)
    clock = _make_clock(initial, white_ms=0, black_ms=150_000)
    director = _make_director()
    pressure = director._clock_pressure(clock)
    assert pressure <= 1.0
    assert pressure >= 0.0


# ---------------------------------------------------------------------------
# chaos_level property
# ---------------------------------------------------------------------------


def test_chaos_level_is_one_at_zero_pressure() -> None:
    director = _make_director()
    director._current_pressure = 0.0
    assert director.chaos_level == 1


def test_chaos_level_is_two_at_mid_pressure() -> None:
    director = _make_director()
    director._current_pressure = 0.45
    assert director.chaos_level == 2


def test_chaos_level_is_three_at_high_pressure() -> None:
    director = _make_director()
    director._current_pressure = 0.7
    assert director.chaos_level == 3


def test_chaos_level_is_four_at_critical_pressure() -> None:
    director = _make_director()
    director._current_pressure = 0.85
    assert director.chaos_level == 4


# ---------------------------------------------------------------------------
# _roll_interval produces shorter intervals under pressure
# ---------------------------------------------------------------------------


def test_roll_interval_shorter_at_high_pressure_than_calm() -> None:
    import random

    rng = random.Random(42)

    director_calm = ChaosDirector(config=ChaosDirectorConfig(mode="local", seed=42))
    director_calm._current_pressure = 0.0
    calm_intervals = [director_calm._roll_interval() for _ in range(50)]

    director_critical = ChaosDirector(config=ChaosDirectorConfig(mode="local", seed=42))
    director_critical._current_pressure = 0.9
    critical_intervals = [director_critical._roll_interval() for _ in range(50)]

    assert sum(critical_intervals) < sum(calm_intervals)
