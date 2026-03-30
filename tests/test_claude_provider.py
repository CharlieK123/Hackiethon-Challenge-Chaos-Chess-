from __future__ import annotations

from types import SimpleNamespace

import anthropic
import chess

from chaos_chess.chaos.claude_provider import ClaudeChaosProvider


class FakeClient:
    def __init__(self, response) -> None:
        self.messages = SimpleNamespace(create=lambda **_: response)


def _make_provider() -> ClaudeChaosProvider:
    return ClaudeChaosProvider(
        api_key="test-key",
        model="claude-sonnet-4-6",
        timeout_seconds=8.0,
        max_tokens=500,
    )


def test_claude_provider_returns_warning_on_api_error(monkeypatch) -> None:
    provider = _make_provider()

    def _raise(**_):
        raise anthropic.APIConnectionError(request=None)  # type: ignore[arg-type]

    monkeypatch.setattr(provider, "_client", SimpleNamespace(messages=SimpleNamespace(create=_raise)))

    response = provider.generate_event(chess.Board())

    assert response.event is None
    assert response.warning == "Claude Chaos Director was unavailable. Using local chaos instead."


def test_claude_provider_rejects_invalid_event_payload(monkeypatch) -> None:
    invalid_payload_message = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="submit_chaos_event",
                input={
                    "event_type": "locked_squares",
                    "description": "Bad event.",
                    "duration_turns": 1,
                    "parameters": {"squares": ["e4", "e4"]},
                },
            )
        ]
    )
    provider = _make_provider()
    monkeypatch.setattr(provider, "_client", FakeClient(invalid_payload_message))

    response = provider.generate_event(chess.Board())

    assert response.event is None
    assert response.warning == "Claude proposed an invalid chaos event. Using local chaos instead."


# --- _extract_tool_payload unit tests ---


def _make_tool_block(*, name: str = "submit_chaos_event", input_data: object = None) -> SimpleNamespace:
    return SimpleNamespace(
        type="tool_use",
        name=name,
        input=input_data if input_data is not None else {"event_type": "slippery_square"},
    )


def test_extract_tool_payload_valid_tool_use_block() -> None:
    payload = {"event_type": "slippery_square", "description": "Watch your step.", "duration_turns": 1, "parameters": {"square": "e4"}}
    message = SimpleNamespace(content=[_make_tool_block(input_data=payload)])

    result = ClaudeChaosProvider._extract_tool_payload(message)

    assert result == payload


def test_extract_tool_payload_missing_content() -> None:
    message_no_attr = SimpleNamespace()
    assert ClaudeChaosProvider._extract_tool_payload(message_no_attr) is None

    message_none_content = SimpleNamespace(content=None)
    assert ClaudeChaosProvider._extract_tool_payload(message_none_content) is None

    message_empty = SimpleNamespace(content=[])
    assert ClaudeChaosProvider._extract_tool_payload(message_empty) is None


def test_extract_tool_payload_wrong_tool_name() -> None:
    message = SimpleNamespace(content=[_make_tool_block(name="other_tool")])

    result = ClaudeChaosProvider._extract_tool_payload(message)

    assert result is None


# --- generate_description fallback test ---


def test_generate_description_falls_back_to_original_on_error(monkeypatch) -> None:
    """If generate_description raises, the original event description must be kept."""
    valid_payload_message = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="submit_chaos_event",
                input={
                    "event_type": "slippery_square",
                    "description": "Slippery square: e4. A piece landing there slides one extra square.",
                    "duration_turns": 1,
                    "parameters": {"square": "e4"},
                },
            )
        ]
    )

    call_count = 0

    def _fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: the tool-use event selection — succeeds.
            return valid_payload_message
        # Second call: generate_description — raises an API error.
        raise anthropic.APIConnectionError(request=None)  # type: ignore[arg-type]

    provider = _make_provider()
    monkeypatch.setattr(provider, "_client", SimpleNamespace(messages=SimpleNamespace(create=_fake_create)))

    response = provider.generate_event(chess.Board())

    assert response.event is not None
    assert response.event.description == (
        "Slippery square: e4. A piece landing there slides one extra square."
    )
