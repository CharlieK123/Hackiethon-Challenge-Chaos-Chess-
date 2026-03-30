from __future__ import annotations

import time

import chess

from chaos_chess.chaos.applier import apply_slippery_follow
from chaos_chess.chaos.director import ChaosDirector
from chaos_chess.bot.base import BotStrategy
from chaos_chess.config import (
    BOT_COLOR,
    BOT_MOVE_DELAY_SECONDS,
    HUMAN_COLOR,
    INITIAL_TIME_MS,
)
from chaos_chess.game.clock import ChessClock
from chaos_chess.game.move_resolver import MoveResolver
from chaos_chess.game.state import GameState
from chaos_chess.game.types import GameMode, GamePhase, GameResult, PromotionPrompt


def color_name(color: chess.Color) -> str:
    return "White" if color == chess.WHITE else "Black"


class GameSession:
    """Owns match state, clocks, bot turns, and move application."""

    def __init__(
        self,
        bot: BotStrategy | None,
        chaos_director: ChaosDirector,
        mode: GameMode = GameMode.HUMAN_VS_BOT,
        human_color: chess.Color = HUMAN_COLOR,
        bot_color: chess.Color | None = BOT_COLOR,
        initial_time_ms: int = INITIAL_TIME_MS,
        bot_delay_seconds: float = BOT_MOVE_DELAY_SECONDS,
    ) -> None:
        self.state = GameState()
        self.mode = mode
        self.human_color = human_color
        self.bot_color = bot_color if mode == GameMode.HUMAN_VS_BOT else None
        self.move_resolver = MoveResolver()
        self.clock = ChessClock(initial_time_ms)
        self.bot = bot
        self.chaos_director = chaos_director
        self.bot_delay_seconds = bot_delay_seconds
        self._bot_move_due_at: float | None = None

        self._set_phase_from_turn()
        self.clock.resume(self.state.board.turn)
        self._schedule_bot_if_needed()

    @property
    def bot_name(self) -> str:
        if self.bot is None:
            return "Player 2"
        return self.bot.name

    @property
    def is_local_multiplayer(self) -> bool:
        return self.mode == GameMode.LOCAL_PVP

    def mode_label(self) -> str:
        return "Vs Friend" if self.is_local_multiplayer else "Vs Bot"

    def player_label(self, color: chess.Color) -> str:
        if self.is_local_multiplayer:
            return "Player 1" if color == chess.WHITE else "Player 2"
        if color == self.human_color:
            return "You"
        return self.bot_name

    @property
    def active_event_title(self) -> str:
        if self.state.phase == GamePhase.CHAOS_PENDING:
            return "Chaos Director"
        if not self.chaos_director.is_enabled:
            return "Chaos Disabled"
        if self.state.active_event is None:
            return "No Active Event"
        return self.state.active_event.title

    @property
    def active_event_description(self) -> str:
        if self.state.phase == GamePhase.CHAOS_PENDING:
            return "Claude is selecting the next event. The clocks are paused until chaos resolves."
        if not self.chaos_director.is_enabled:
            return "Chaos events are turned off for this game."
        if self.state.active_event is None:
            turns = self.chaos_director.turns_until_next_event
            suffix = "turn" if turns == 1 else "turns"
            return f"The board is calm for now. Next chaos event in about {turns} {suffix}."
        if self.state.active_event_turns_remaining > 1:
            return (
                f"{self.state.active_event.description} "
                f"({self.state.active_event_turns_remaining} turns remaining)"
            )
        return self.state.active_event.description

    def chaos_log_rows(self) -> list[str]:
        return list(self.state.chaos_log)

    def close(self) -> None:
        if self.bot is not None:
            self.bot.close()
        self.chaos_director.shutdown()

    def update(self) -> None:
        if self.state.result is not None:
            return

        if self.state.phase == GamePhase.CHAOS_PENDING:
            if self.chaos_director.poll(self.state):
                if self._resolve_finished_position():
                    return
                self.clock.resume(self.state.board.turn)
                self._set_phase_from_turn()
                self._schedule_bot_if_needed()
            return

        self.clock.update()
        self._check_timeout()
        if self.state.result is not None:
            return

        if self.state.pending_promotion is not None:
            self.state.phase = GamePhase.PROMOTION_PENDING
            return

        self._set_phase_from_turn()
        if self.state.phase == GamePhase.BOT_TURN:
            self._maybe_play_bot_move()

    def handle_board_click(self, square: int) -> None:
        if self.state.result is not None:
            return
        if self.state.pending_promotion is not None:
            return
        if self.state.phase == GamePhase.CHAOS_PENDING:
            return
        if not self.is_local_multiplayer and self.state.board.turn != self.human_color:
            return

        board = self.state.board
        selected = self.state.selected_square
        piece = board.piece_at(square)

        if selected == square:
            self.state.clear_selection()
            return

        if selected is not None and square in self.state.legal_targets:
            matching_moves = self.move_resolver.matching_moves(
                board,
                selected,
                square,
                self.state.active_event,
            )
            if len(matching_moves) == 1:
                self._apply_move(matching_moves[0])
                return
            if matching_moves:
                self._open_promotion_prompt(selected, square, matching_moves)
                return

        if piece is not None and piece.color == board.turn:
            self._select_square(square)
            return

        self.state.clear_selection()

    def handle_promotion_choice(self, piece_type: int) -> None:
        prompt = self.state.pending_promotion
        if prompt is None:
            return

        move = prompt.options.get(piece_type)
        if move is None:
            return

        self._apply_move(move)

    def formatted_clock(self, color: chess.Color) -> str:
        total_ms = self.clock.remaining_ms(color)
        total_seconds = max(0, total_ms // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def status_text(self) -> str:
        if self.state.result is not None:
            return f"{self.state.result.message} Press R or click Restart to play again."

        if self.state.pending_promotion is not None:
            return "Choose a promotion piece for your pawn."

        if self.state.phase == GamePhase.CHAOS_PENDING:
            return "Chaos Director is selecting the next event. Both clocks are paused."

        turn = color_name(self.state.board.turn)
        current_player = self.player_label(self.state.board.turn)
        if self.bot_color is not None and self.state.board.turn == self.bot_color:
            text = f"{turn} to move. {current_player} is thinking."
        else:
            text = f"{turn} to move. {current_player}'s turn."

        if self.state.board.is_check():
            text += f" {turn} is in check."
        return text

    def status_detail_text(self) -> str:
        if self.state.result is not None:
            return "Use the side-panel controls to restart or change the chaos settings."

        if self.state.pending_promotion is not None:
            return "Select Queen, Rook, Bishop, or Knight from the promotion panel."

        if self.state.phase == GamePhase.CHAOS_PENDING:
            return "The next player clock will resume after the event is validated."

        if self.is_local_multiplayer:
            return "Pass the laptop to the other player after each move."

        if self.state.board.turn == self.human_color:
            return "Click a piece to see its legal moves."

        return f"{self.bot.name} only chooses chess moves. Chaos is handled separately."

    def move_rows(self) -> list[str]:
        rows: list[str] = []
        for index in range(0, len(self.state.move_history), 2):
            move_number = index // 2 + 1
            white_move = self.state.move_history[index]
            black_move = self.state.move_history[index + 1] if index + 1 < len(self.state.move_history) else ""
            rows.append(f"{move_number:>2}. {white_move:<8} {black_move}".rstrip())
        return rows

    def _select_square(self, square: int) -> None:
        self.state.selected_square = square
        self.state.legal_targets = self.move_resolver.legal_targets_for_square(
            self.state.board,
            square,
            self.state.active_event,
        )

    def _open_promotion_prompt(
        self,
        from_square: int,
        to_square: int,
        matching_moves: list[chess.Move],
    ) -> None:
        options = {move.promotion: move for move in matching_moves if move.promotion is not None}
        if not options:
            return

        self.state.pending_promotion = PromotionPrompt(
            from_square=from_square,
            to_square=to_square,
            options=options,
        )
        self.state.phase = GamePhase.PROMOTION_PENDING

    def _apply_move(self, move: chess.Move) -> None:
        san = self.move_resolver.san(self.state.board, move)
        slip_destination = self.chaos_director.slippery_destination(
            self.state.board,
            move,
            self.state.active_event,
        )
        self.state.board.push(move)
        if slip_destination is not None:
            message = apply_slippery_follow(self.state.board, move.to_square, slip_destination)
            self.chaos_director.record_message(self.state, message)

        self.state.move_history.append(san)
        self.state.last_move_from = move.from_square
        self.state.last_move_to = slip_destination if slip_destination is not None else move.to_square
        self.state.revision += 1
        self.state.pending_promotion = None
        self.state.clear_selection()
        self._bot_move_due_at = None
        self.clock.pause()

        if self._resolve_finished_position():
            return

        if self.chaos_director.complete_turn(self.state, self.clock):
            self.state.phase = GamePhase.CHAOS_PENDING
            return

        if self._resolve_finished_position():
            return

        self.clock.resume(self.state.board.turn)
        self._set_phase_from_turn()
        self._schedule_bot_if_needed()

    def _resolve_finished_position(self) -> bool:
        board = self.state.board
        if board.is_checkmate():
            winner = not board.turn
            self.state.result = GameResult(
                winner=winner,
                reason="checkmate",
                message=f"{color_name(winner)} wins by checkmate.",
            )
        elif board.is_stalemate():
            self.state.result = GameResult(
                winner=None,
                reason="stalemate",
                message="Draw by stalemate. No legal moves remain.",
            )

        if self.state.result is None:
            return False

        self.clock.pause()
        self.state.phase = GamePhase.GAME_OVER
        return True

    def _check_timeout(self) -> None:
        flagged = self.clock.flagged_color()
        if flagged is None:
            return

        winner = not flagged
        self.state.result = GameResult(
            winner=winner,
            reason="timeout",
            message=f"{color_name(winner)} wins on time.",
        )
        self.clock.pause()
        self.state.phase = GamePhase.GAME_OVER

    def _set_phase_from_turn(self) -> None:
        if self.state.result is not None:
            self.state.phase = GamePhase.GAME_OVER
        elif self.state.pending_promotion is not None:
            self.state.phase = GamePhase.PROMOTION_PENDING
        elif self.bot is not None and self.bot_color is not None and self.state.board.turn == self.bot_color:
            self.state.phase = GamePhase.BOT_TURN
        else:
            self.state.phase = GamePhase.HUMAN_TURN

    def _schedule_bot_if_needed(self) -> None:
        if self.bot is None or self.bot_color is None:
            self._bot_move_due_at = None
            return
        if self.state.result is not None or self.state.pending_promotion is not None:
            return
        if self.state.board.turn == self.bot_color:
            self._bot_move_due_at = time.monotonic() + self.bot_delay_seconds
        else:
            self._bot_move_due_at = None

    def _maybe_play_bot_move(self) -> None:
        if self.bot is None:
            return
        if self._bot_move_due_at is None or time.monotonic() < self._bot_move_due_at:
            return

        board_copy = self.state.board.copy(stack=False)
        legal_moves = self.move_resolver.legal_moves(board_copy, self.state.active_event)
        move = self.bot.choose_move(board_copy, legal_moves)
        self._apply_move(move)
