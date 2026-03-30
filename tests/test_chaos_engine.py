from __future__ import annotations

import chess

from chaos_chess.chaos.applier import apply_gust, apply_slippery_follow
from chaos_chess.chaos.director import ChaosDirector, ChaosDirectorConfig
from chaos_chess.chaos.models import ChaosEventType
from chaos_chess.chaos.schemas import ChaosSchemaValidator
from chaos_chess.chaos.validator import ChaosValidator
from chaos_chess.game.move_resolver import MoveResolver
from chaos_chess.game.state import GameState


def test_locked_squares_remove_blocked_targets() -> None:
    board = chess.Board()
    event = ChaosSchemaValidator.validate(
        {
            "event_type": ChaosEventType.LOCKED_SQUARES.value,
            "description": "Locked squares: e4.",
            "duration_turns": 1,
            "parameters": {"squares": ["e4"]},
        }
    )
    resolver = MoveResolver()

    assert event is not None
    targets = resolver.legal_targets_for_square(board, chess.E2, event)

    assert chess.E4 not in targets


def test_frozen_piece_removes_moves_from_that_square() -> None:
    board = chess.Board()
    event = ChaosSchemaValidator.validate(
        {
            "event_type": ChaosEventType.FROZEN_PIECE.value,
            "description": "Frozen piece: knight on g1.",
            "duration_turns": 1,
            "parameters": {
                "square": "g1",
                "piece_type": "knight",
                "color": "white",
            },
        }
    )
    resolver = MoveResolver()

    assert event is not None
    moves = resolver.legal_moves_for_square(board, chess.G1, event)

    assert moves == []


def test_slippery_square_slides_piece_one_more_square() -> None:
    board = chess.Board("4k3/8/8/8/8/8/4R3/4K3 w - - 0 1")
    move = chess.Move.from_uci("e2e4")
    event = ChaosSchemaValidator.validate(
        {
            "event_type": ChaosEventType.SLIPPERY_SQUARE.value,
            "description": "Slippery square: e4.",
            "duration_turns": 1,
            "parameters": {"square": "e4"},
        }
    )

    assert event is not None
    destination = ChaosValidator.slippery_destination(board, move, event)
    assert destination == chess.E5

    board.push(move)
    apply_slippery_follow(board, chess.E4, destination)

    piece = board.piece_at(chess.E5)
    assert piece is not None
    assert piece.piece_type == chess.ROOK
    assert board.piece_at(chess.E4) is None


def test_gust_of_wind_moves_pieces_sideways() -> None:
    board = chess.Board("4k3/8/8/3r4/3R4/8/8/4K3 w - - 0 1")
    event = ChaosSchemaValidator.validate(
        {
            "event_type": ChaosEventType.GUST_OF_WIND.value,
            "description": "A gust pushes pieces right.",
            "duration_turns": 1,
            "parameters": {
                "direction": "right",
                "targets": "non_king_pieces",
                "shifts": [
                    {
                        "from_square": "d4",
                        "to_square": "e4",
                        "piece_type": "rook",
                        "color": "white",
                    },
                    {
                        "from_square": "d5",
                        "to_square": "e5",
                        "piece_type": "rook",
                        "color": "black",
                    },
                ],
            },
        }
    )

    assert event is not None
    assert ChaosValidator.validate_event(board, event)

    apply_gust(board, event)

    assert board.piece_at(chess.E4) is not None
    assert board.piece_at(chess.E5) is not None
    assert board.piece_at(chess.D4) is None
    assert board.piece_at(chess.D5) is None


def test_local_chaos_director_triggers_event_when_counter_expires() -> None:
    director = ChaosDirector(config=ChaosDirectorConfig(mode="local", seed=7))
    director._turns_until_next_event = 1
    state = GameState()

    pending = director.complete_turn(state)

    assert pending is False
    assert state.active_event is not None
    assert state.active_event_turns_remaining == 1
    assert state.chaos_log


def test_invalid_schema_payload_is_rejected_safely() -> None:
    event = ChaosSchemaValidator.validate(
        {
            "event_type": ChaosEventType.LOCKED_SQUARES.value,
            "description": "Bad locked squares.",
            "duration_turns": 1,
            "parameters": {"squares": ["e4", "e4"]},
        }
    )

    assert event is None
