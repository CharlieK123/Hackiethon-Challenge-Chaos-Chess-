from __future__ import annotations

import chess

from chaos_chess.chaos.personality import ChaosDirectorPersonality, _material_balance
from chaos_chess.chaos.schemas import ChaosSchemaValidator


def _make_event(event_type: str = "frozen_piece"):
    payload = {
        "frozen_piece": {
            "event_type": "frozen_piece",
            "description": "Frozen piece: the knight on g1 cannot move this turn.",
            "duration_turns": 1,
            "parameters": {"square": "g1", "piece_type": "knight", "color": "white"},
        },
        "locked_squares": {
            "event_type": "locked_squares",
            "description": "Locked squares: e4.",
            "duration_turns": 1,
            "parameters": {"squares": ["e4"]},
        },
        "gust_of_wind": {
            "event_type": "gust_of_wind",
            "description": "Gust of wind.",
            "duration_turns": 1,
            "parameters": {
                "direction": "left",
                "targets": "non_king_pieces",
                "shifts": [{"from_square": "b2", "to_square": "a2", "piece_type": "pawn", "color": "white"}],
            },
        },
    }[event_type]
    event = ChaosSchemaValidator.validate(payload)
    assert event is not None
    return event


# ---------------------------------------------------------------------------
# dominant_color
# ---------------------------------------------------------------------------


def test_dominant_color_balanced_when_no_history() -> None:
    p = ChaosDirectorPersonality()
    assert p.dominant_color == "balanced"


def test_dominant_color_balanced_when_fewer_than_three_samples() -> None:
    p = ChaosDirectorPersonality(material_history=[500, 600])
    assert p.dominant_color == "balanced"


def test_dominant_color_white_when_consistently_ahead() -> None:
    p = ChaosDirectorPersonality(material_history=[200, 300, 250, 400, 350, 300])
    assert p.dominant_color == "white"


def test_dominant_color_black_when_consistently_ahead() -> None:
    p = ChaosDirectorPersonality(material_history=[-200, -350, -100, -400, -250, -300])
    assert p.dominant_color == "black"


def test_dominant_color_balanced_when_mixed() -> None:
    p = ChaosDirectorPersonality(material_history=[300, -300, 100, -100, 50, -50])
    assert p.dominant_color == "balanced"


def test_dominant_color_uses_only_last_six_turns() -> None:
    # Many early turns where black led, but last 6 turns white is ahead.
    early = [-500] * 20
    recent = [200, 250, 300, 350, 400, 450]
    p = ChaosDirectorPersonality(material_history=early + recent)
    assert p.dominant_color == "white"


# ---------------------------------------------------------------------------
# to_prompt_context
# ---------------------------------------------------------------------------


def test_to_prompt_context_includes_turn_count() -> None:
    p = ChaosDirectorPersonality(turn_count=14)
    ctx = p.to_prompt_context()
    assert "Turn 14." in ctx


def test_to_prompt_context_mentions_no_events_when_empty() -> None:
    p = ChaosDirectorPersonality(turn_count=3)
    ctx = p.to_prompt_context()
    assert "No chaos events have fired yet." in ctx


def test_to_prompt_context_lists_fired_events() -> None:
    p = ChaosDirectorPersonality(turn_count=12)
    p.record_event(_make_event("frozen_piece"))
    p.record_event(_make_event("locked_squares"))
    ctx = p.to_prompt_context()
    assert "frozen_piece" in ctx
    assert "locked_squares" in ctx


def test_to_prompt_context_escalate_when_one_sided() -> None:
    p = ChaosDirectorPersonality(
        material_history=[300, 400, 350, 500, 450, 400],
        turn_count=10,
    )
    ctx = p.to_prompt_context()
    assert "Escalate disruption" in ctx


def test_to_prompt_context_subtle_pressure_when_balanced() -> None:
    p = ChaosDirectorPersonality(
        material_history=[10, -20, 30, -10, 5, -5],
        turn_count=6,
    )
    ctx = p.to_prompt_context()
    assert "subtle pressure" in ctx


# ---------------------------------------------------------------------------
# record_turn and record_event
# ---------------------------------------------------------------------------


def test_record_turn_updates_turn_count_and_material_history() -> None:
    board = chess.Board()
    p = ChaosDirectorPersonality()
    p.record_turn(board)
    assert p.turn_count == 1
    assert len(p.material_history) == 1
    assert p.material_history[0] == 0  # opening position is balanced


def test_material_balance_starting_position() -> None:
    board = chess.Board()
    assert _material_balance(board) == 0


def test_material_balance_reflects_captured_queen() -> None:
    board = chess.Board()
    board.remove_piece_at(chess.D1)  # remove white queen
    assert _material_balance(board) == -900


def test_record_event_stores_event_info() -> None:
    p = ChaosDirectorPersonality(turn_count=7)
    event = _make_event("frozen_piece")
    p.record_event(event)
    assert len(p.events_fired) == 1
    assert p.events_fired[0]["event_type"] == "frozen_piece"
    assert p.events_fired[0]["turn"] == 7
