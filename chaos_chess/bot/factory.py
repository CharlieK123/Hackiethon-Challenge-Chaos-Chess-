from __future__ import annotations

import shutil
from pathlib import Path

import chess

from chaos_chess.bot.base import BotConfig, BotMode, BotStrategy, BotUnavailableError
from chaos_chess.bot.fallback import MaterialFallbackBot
from chaos_chess.bot.stockfish import StockfishBot


class FailoverBot(BotStrategy):
    """Uses a primary bot until it becomes unavailable, then falls back."""

    def __init__(self, primary: BotStrategy, fallback: BotStrategy) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_available = True

    @property
    def name(self) -> str:
        if self._primary_available:
            return self._primary.name
        return self._fallback.name

    def choose_move(
        self,
        board: chess.Board,
        legal_moves: list[chess.Move] | None = None,
    ) -> chess.Move:
        if self._primary_available:
            try:
                return self._primary.choose_move(board, legal_moves)
            except BotUnavailableError:
                self._primary_available = False
                self._primary.close()

        return self._fallback.choose_move(board, legal_moves)

    def close(self) -> None:
        self._primary.close()
        self._fallback.close()


def bot_config_from_values(
    *,
    mode: str | BotMode = BotMode.AUTO,
    stockfish_path: str | None = None,
    stockfish_think_time_seconds: float = 0.2,
    fallback_randomness: float = 18.0,
    seed: int | None = None,
) -> BotConfig:
    parsed_mode = mode if isinstance(mode, BotMode) else BotMode.parse(mode)
    return BotConfig(
        mode=parsed_mode,
        stockfish_path=stockfish_path,
        stockfish_think_time_seconds=stockfish_think_time_seconds,
        fallback_randomness=fallback_randomness,
        seed=seed,
    )


def create_bot(color: chess.Color, config: BotConfig | None = None) -> BotStrategy:
    config = config or BotConfig()
    fallback = MaterialFallbackBot(
        color=color,
        randomness=config.fallback_randomness,
        seed=config.seed,
    )

    if config.mode == BotMode.SIMPLE:
        return fallback

    engine_path = resolve_stockfish_path(config)
    if engine_path is None:
        return fallback

    try:
        stockfish_bot = StockfishBot(
            color=color,
            engine_path=engine_path,
            think_time_seconds=config.stockfish_think_time_seconds,
        )
    except BotUnavailableError:
        return fallback

    return FailoverBot(primary=stockfish_bot, fallback=fallback)


def resolve_stockfish_path(config: BotConfig) -> str | None:
    explicit_path = _normalized_path(config.stockfish_path)
    if explicit_path is not None:
        return explicit_path

    for command_name in ("stockfish", "stockfish.exe"):
        discovered_path = shutil.which(command_name)
        if discovered_path:
            return discovered_path

    return None


def _normalized_path(path_value: str | None) -> str | None:
    if path_value is None:
        return None

    expanded_path = Path(path_value).expanduser()
    if expanded_path.exists():
        return str(expanded_path)

    return None
