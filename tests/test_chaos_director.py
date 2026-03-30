from __future__ import annotations

import time

import chess

from chaos_chess.chaos.claude_provider import ClaudeChaosProvider
from chaos_chess.chaos.director import ChaosDirector, ChaosDirectorConfig
from chaos_chess.chaos.provider import ChaosEventProvider, ChaosProviderResponse
from chaos_chess.chaos.schemas import ChaosSchemaValidator
from chaos_chess.game.state import GameState


class FakeRemoteProvider(ChaosEventProvider):
    def __init__(self, response: ChaosProviderResponse, configured: bool = True) -> None:
        self._response = response
        self._configured = configured

    @property
    def name(self) -> str:
        return "Fake Remote"

    def is_configured(self) -> bool:
        return self._configured

    def generate_event(self, board: chess.Board) -> ChaosProviderResponse:
        return self._response


class FakeLocalProvider(ChaosEventProvider):
    def __init__(self, response: ChaosProviderResponse) -> None:
        self._response = response

    @property
    def name(self) -> str:
        return "Fake Local"

    def generate_event(self, board: chess.Board) -> ChaosProviderResponse:
        return self._response


def test_claude_provider_is_disabled_without_api_key() -> None:
    provider = ClaudeChaosProvider(
        api_key=None,
        model="claude-sonnet-4-6",
        timeout_seconds=8.0,
        max_tokens=500,
    )

    assert provider.is_configured() is False
    assert provider.generate_event(chess.Board()).event is None


def test_director_uses_local_immediately_when_remote_is_not_configured() -> None:
    local_event = ChaosSchemaValidator.validate(
        {
            "event_type": "locked_squares",
            "description": "Locked squares: e4.",
            "duration_turns": 1,
            "parameters": {"squares": ["e4"]},
        }
    )
    assert local_event is not None

    director = ChaosDirector(
        local_provider=FakeLocalProvider(ChaosProviderResponse(event=local_event)),
        remote_provider=FakeRemoteProvider(ChaosProviderResponse(event=None), configured=False),
        config=ChaosDirectorConfig(mode="hybrid"),
    )
    director._turns_until_next_event = 1
    state = GameState()

    pending = director.complete_turn(state)

    assert pending is False
    assert state.active_event == local_event
    assert state.chaos_log[-1] == local_event.description
    director.shutdown()


def test_director_disabled_mode_skips_event_generation() -> None:
    local_event = ChaosSchemaValidator.validate(
        {
            "event_type": "locked_squares",
            "description": "Locked squares: e4.",
            "duration_turns": 1,
            "parameters": {"squares": ["e4"]},
        }
    )
    assert local_event is not None

    director = ChaosDirector(
        local_provider=FakeLocalProvider(ChaosProviderResponse(event=local_event)),
        config=ChaosDirectorConfig(mode="disabled"),
    )
    director._turns_until_next_event = 1
    state = GameState()

    pending = director.complete_turn(state)

    assert pending is False
    assert state.active_event is None
    assert list(state.chaos_log) == []
    director.shutdown()


def test_director_falls_back_to_local_after_remote_failure() -> None:
    local_event = ChaosSchemaValidator.validate(
        {
            "event_type": "frozen_piece",
            "description": "Frozen piece: the knight on g1 cannot move this turn.",
            "duration_turns": 1,
            "parameters": {
                "square": "g1",
                "piece_type": "knight",
                "color": "white",
            },
        }
    )
    assert local_event is not None

    director = ChaosDirector(
        local_provider=FakeLocalProvider(ChaosProviderResponse(event=local_event)),
        remote_provider=FakeRemoteProvider(
            ChaosProviderResponse(
                event=None,
                warning="Claude proposed an invalid chaos event. Using local chaos instead.",
            ),
        ),
        config=ChaosDirectorConfig(mode="hybrid"),
    )
    director._turns_until_next_event = 1
    state = GameState()

    pending = director.complete_turn(state)

    assert pending is True

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if director.poll(state):
            break
        time.sleep(0.01)
    else:
        raise AssertionError("Chaos director did not resolve the pending request in time.")

    assert state.active_event == local_event
    assert any("local chaos instead" in entry for entry in state.chaos_log)
    assert state.chaos_log[-1] == local_event.description
    director.shutdown()
