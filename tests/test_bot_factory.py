from __future__ import annotations

import chess

from chaos_chess.bot.base import BotMode
from chaos_chess.bot.factory import bot_config_from_values, create_bot


def test_bot_factory_returns_simple_bot_when_requested() -> None:
    config = bot_config_from_values(mode=BotMode.SIMPLE, seed=5)

    bot = create_bot(chess.BLACK, config)

    assert bot.name == "Simple Bot"
    bot.close()


def test_bot_factory_falls_back_when_stockfish_path_is_missing() -> None:
    config = bot_config_from_values(
        mode=BotMode.STOCKFISH,
        stockfish_path="C:/definitely-missing/stockfish.exe",
        seed=5,
    )

    bot = create_bot(chess.BLACK, config)

    assert bot.name == "Simple Bot"
    bot.close()
