from __future__ import annotations

import chess

from chaos_chess.bot.fallback import MaterialFallbackBot


def test_fallback_bot_prefers_forced_checkmate() -> None:
    board = chess.Board("4k3/4q3/8/8/8/8/4R3/4K3 w - - 0 1")
    bot = MaterialFallbackBot(color=chess.WHITE, randomness=0.0, seed=7)

    move = bot.choose_move(board)

    assert move == chess.Move.from_uci("e2e7")
