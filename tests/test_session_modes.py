from __future__ import annotations

import chess

from chaos_chess.chaos.director import ChaosDirector, ChaosDirectorConfig
from chaos_chess.game.session import GameSession
from chaos_chess.game.types import GameMode


def test_local_pvp_mode_allows_both_players_to_move() -> None:
    session = GameSession(
        bot=None,
        chaos_director=ChaosDirector(config=ChaosDirectorConfig(mode="disabled")),
        mode=GameMode.LOCAL_PVP,
    )

    session.handle_board_click(chess.E2)
    session.handle_board_click(chess.E4)
    session.handle_board_click(chess.E7)
    session.handle_board_click(chess.E5)

    assert session.state.board.piece_at(chess.E4) is not None
    assert session.state.board.piece_at(chess.E5) is not None
    assert session.state.board.turn == chess.WHITE
    assert session.move_rows() == [" 1. e4       e5"]

    session.close()
