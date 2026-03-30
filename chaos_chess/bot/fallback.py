from __future__ import annotations

import random

import chess

from chaos_chess.bot.base import BotStrategy
from chaos_chess.bot.evaluation import material_score


class MaterialFallbackBot(BotStrategy):
    """One-ply bot with material scoring and light randomness."""

    def __init__(
        self,
        color: chess.Color,
        randomness: float = 18.0,
        seed: int | None = None,
    ) -> None:
        self.color = color
        self.randomness = randomness
        self._rng = random.Random(seed)

    @property
    def name(self) -> str:
        return "Simple Bot"

    def choose_move(
        self,
        board: chess.Board,
        legal_moves: list[chess.Move] | None = None,
    ) -> chess.Move:
        legal_moves = list(legal_moves) if legal_moves is not None else list(board.legal_moves)
        if not legal_moves:
            raise ValueError("Bot was asked to move in a finished position.")

        best_score: float | None = None
        best_moves: list[chess.Move] = []

        for move in legal_moves:
            board.push(move)
            if board.is_checkmate():
                score = 1_000_000.0
            elif board.is_stalemate():
                score = 0.0
            else:
                score = float(material_score(board, self.color))
                if board.is_check():
                    score += 25.0

            board.pop()
            score += self._rng.uniform(-self.randomness, self.randomness)

            if best_score is None or score > best_score:
                best_score = score
                best_moves = [move]
            elif score == best_score:
                best_moves.append(move)

        return self._rng.choice(best_moves)
