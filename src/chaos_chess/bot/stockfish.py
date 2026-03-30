from __future__ import annotations

from pathlib import Path

import chess
import chess.engine

from chaos_chess.bot.base import BotStrategy, BotUnavailableError


class StockfishBot(BotStrategy):
    """Bot backed by a local Stockfish UCI engine."""

    def __init__(
        self,
        color: chess.Color,
        engine_path: str,
        think_time_seconds: float = 0.2,
    ) -> None:
        self.color = color
        self.engine_path = str(Path(engine_path).expanduser())
        self.think_time_seconds = think_time_seconds
        self._engine: chess.engine.SimpleEngine | None = None

        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
        except (FileNotFoundError, OSError, chess.engine.EngineError) as exc:
            raise BotUnavailableError(
                f"Unable to start Stockfish from '{self.engine_path}'."
            ) from exc

    @property
    def name(self) -> str:
        return "Stockfish"

    def choose_move(
        self,
        board: chess.Board,
        legal_moves: list[chess.Move] | None = None,
    ) -> chess.Move:
        if self._engine is None:
            raise BotUnavailableError("Stockfish is not running.")

        try:
            result = self._engine.play(
                board,
                chess.engine.Limit(time=self.think_time_seconds),
                root_moves=legal_moves,
            )
        except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError) as exc:
            self.close()
            raise BotUnavailableError("Stockfish failed while choosing a move.") from exc

        if result.move is None:
            raise BotUnavailableError("Stockfish returned no move.")
        return result.move

    def close(self) -> None:
        if self._engine is None:
            return

        try:
            self._engine.quit()
        except chess.engine.EngineTerminatedError:
            pass
        finally:
            self._engine = None
