from __future__ import annotations

import time

import chess
import pygame

from chaos_chess.bot.base import BotConfig, BotMode
from chaos_chess.bot.factory import bot_config_from_values, create_bot
from chaos_chess.chaos.claude_provider import ClaudeChaosProvider
from chaos_chess.chaos.director import ChaosDirector, ChaosDirectorConfig
from chaos_chess.config import (
    ANTHROPIC_API_KEY,
    BACKGROUND_COLOR,
    BOT_COLOR,
    BOT_MODE,
    CHAOS_DIRECTOR_MAX_TOKENS,
    CHAOS_DIRECTOR_MODEL,
    CHAOS_DIRECTOR_MODE,
    CHAOS_DIRECTOR_TIMEOUT_SECONDS,
    FALLBACK_BOT_RANDOMNESS,
    FPS,
    INITIAL_TIME_MS,
    STOCKFISH_PATH,
    STOCKFISH_THINK_TIME_SECONDS,
    WINDOW_HEIGHT,
    WINDOW_TITLE,
    WINDOW_WIDTH,
)
from chaos_chess.game.session import GameSession
from chaos_chess.game.types import GameMode, GamePhase
from chaos_chess.ui.board_renderer import BoardRenderer
from chaos_chess.ui.hud_renderer import HudRenderer, HudViewState
from chaos_chess.ui.input_controller import InputAction, InputController
from chaos_chess.ui.lobby_scene import LobbyResult


# Speed presets for Bot vs Bot mode (seconds between auto-moves).
_AUTO_BOT_SPEEDS = [0.8, 0.45, 0.15, 0.05]
_AUTO_BOT_SPEED_DEFAULT = 1  # index into _AUTO_BOT_SPEEDS


class GameScene:
    def __init__(self, lobby_result: LobbyResult | None = None) -> None:
        self.screen = pygame.display.get_surface() or pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.frame_clock = pygame.time.Clock()
        self.board_renderer = BoardRenderer()
        self.hud_renderer = HudRenderer()
        self.input_controller = InputController(self.board_renderer, self.hud_renderer)

        self._lobby_result = lobby_result

        if lobby_result is not None:
            self.chaos_enabled = lobby_result.chaos_mode != "disabled"
            self.claude_enabled = lobby_result.chaos_mode == "hybrid"
            self.game_mode     = lobby_result.mode
        else:
            self.chaos_enabled = CHAOS_DIRECTOR_MODE != "disabled"
            self.claude_enabled = CHAOS_DIRECTOR_MODE == "hybrid"
            self.game_mode     = GameMode.HUMAN_VS_BOT

        self.claude_available = False

        # Bot vs Bot state
        self._auto_bots: dict[chess.Color, object] = {}
        self._auto_bot_speed_idx: int = _AUTO_BOT_SPEED_DEFAULT
        self._auto_bot_move_due: float = 0.0

        self.session = self._create_session()

    def run(self) -> str | None:
        """Run the game loop. Returns 'lobby' if the player wants to return to the lobby."""
        self._return_to_lobby = False
        try:
            running = True
            while running:
                self.frame_clock.tick(FPS)
                events = pygame.event.get()
                hud_view_state = self._hud_view_state()
                actions = self.input_controller.gather_actions(
                    events,
                    self.session.state.pending_promotion,
                    hud_view_state,
                )

                for action in actions:
                    if self._handle_action(action):
                        running = False
                        break

                self.session.update()
                self._maybe_auto_play()
                self._render()
        finally:
            self._close_auto_bots()
            self.session.close()

        return "lobby" if self._return_to_lobby else None

    def _handle_action(self, action: InputAction) -> bool:
        if action.kind == "quit":
            return True

        if action.kind == "restart":
            self._return_to_lobby = True
            return True

        if action.kind == "toggle_mode":
            self.game_mode = (
                GameMode.LOCAL_PVP
                if self.game_mode == GameMode.HUMAN_VS_BOT
                else GameMode.HUMAN_VS_BOT
            )
            note = "Local two-player mode enabled." if self.game_mode == GameMode.LOCAL_PVP else "Bot mode enabled."
            self._restart_session(note)
            return False

        if action.kind == "toggle_chaos":
            self.chaos_enabled = not self.chaos_enabled
            note = "Chaos events enabled." if self.chaos_enabled else "Chaos events disabled for this game."
            self._restart_session(note)
            return False

        if action.kind == "toggle_claude":
            if not self.claude_available:
                return False
            self.claude_enabled = not self.claude_enabled
            if self.claude_enabled:
                self.chaos_enabled = True
                note = "Claude Chaos Director enabled."
            else:
                note = "Claude Chaos Director disabled. Local chaos remains available."
            self._restart_session(note)
            return False

        if action.kind == "speed_up" and self.game_mode == GameMode.BOT_VS_BOT:
            self._auto_bot_speed_idx = min(self._auto_bot_speed_idx + 1, len(_AUTO_BOT_SPEEDS) - 1)
            return False

        if action.kind == "speed_down" and self.game_mode == GameMode.BOT_VS_BOT:
            self._auto_bot_speed_idx = max(self._auto_bot_speed_idx - 1, 0)
            return False

        if action.kind == "promotion" and action.promotion_piece is not None:
            self.session.handle_promotion_choice(action.promotion_piece)
            return False

        if action.kind == "board_click" and action.square is not None:
            if self.game_mode != GameMode.BOT_VS_BOT:
                self.session.handle_board_click(action.square)
            return False

        return False

    def _render(self) -> None:
        self.screen.fill(BACKGROUND_COLOR)
        self.board_renderer.draw(self.screen, self.session.state)
        self.hud_renderer.draw(self.screen, self.session, self._hud_view_state())
        pygame.display.flip()

    def _create_session(self, note: str | None = None) -> GameSession:
        lobby = self._lobby_result

        # --- time ---
        initial_time_ms = lobby.initial_time_ms if lobby is not None else INITIAL_TIME_MS

        # --- bot difficulty ---
        if lobby is not None:
            bot_cfg = self._bot_config_from_difficulty(lobby.bot_difficulty)
        else:
            bot_cfg = bot_config_from_values(
                mode=BOT_MODE,
                stockfish_path=STOCKFISH_PATH,
                stockfish_think_time_seconds=STOCKFISH_THINK_TIME_SECONDS,
                fallback_randomness=FALLBACK_BOT_RANDOMNESS,
            )

        # --- chaos provider ---
        custom_prompt = lobby.custom_chaos_prompt if lobby is not None else ""
        claude_provider = ClaudeChaosProvider(
            api_key=ANTHROPIC_API_KEY,
            model=CHAOS_DIRECTOR_MODEL,
            timeout_seconds=CHAOS_DIRECTOR_TIMEOUT_SECONDS,
            max_tokens=CHAOS_DIRECTOR_MAX_TOKENS,
            custom_chaos_prompt=custom_prompt,
        )
        self.claude_available = claude_provider.is_configured()

        # --- chaos director ---
        frequency_preset = lobby.chaos_frequency if lobby is not None else "normal"
        director_mode    = self._chaos_director_mode()
        director = ChaosDirector(
            remote_provider=claude_provider,
            config=ChaosDirectorConfig(mode=director_mode, frequency_preset=frequency_preset),
        )

        # --- bots ---
        self._close_auto_bots()
        session_mode: GameMode
        main_bot = None

        if self.game_mode == GameMode.BOT_VS_BOT:
            session_mode = GameMode.LOCAL_PVP
            self._auto_bots = {
                chess.WHITE: create_bot(chess.WHITE, bot_cfg),
                chess.BLACK: create_bot(chess.BLACK, bot_cfg),
            }
            self._auto_bot_move_due = time.monotonic() + _AUTO_BOT_SPEEDS[self._auto_bot_speed_idx]
        elif self.game_mode == GameMode.HUMAN_VS_BOT:
            session_mode = GameMode.HUMAN_VS_BOT
            main_bot = create_bot(BOT_COLOR, bot_cfg)
        else:
            session_mode = GameMode.LOCAL_PVP

        session = GameSession(
            bot=main_bot,
            chaos_director=director,
            mode=session_mode,
            initial_time_ms=initial_time_ms,
        )
        if note:
            session.chaos_director.record_message(session.state, note)
        return session

    def _restart_session(self, note: str | None = None) -> None:
        self.session.close()
        self.session = self._create_session(note)

    def _close_auto_bots(self) -> None:
        for bot in self._auto_bots.values():
            try:
                bot.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._auto_bots = {}

    # ------------------------------------------------------------------
    # Bot vs Bot auto-play
    # ------------------------------------------------------------------

    def _maybe_auto_play(self) -> None:
        if self.game_mode != GameMode.BOT_VS_BOT:
            return
        if self.session.state.result is not None:
            return
        if self.session.state.phase != GamePhase.HUMAN_TURN:
            return
        if time.monotonic() < self._auto_bot_move_due:
            return

        board_copy = self.session.state.board.copy(stack=False)
        turn = board_copy.turn
        bot = self._auto_bots.get(turn)
        if bot is None:
            return

        legal_moves = self.session.move_resolver.legal_moves(
            board_copy, self.session.state.active_event
        )
        if not legal_moves:
            return

        move = bot.choose_move(board_copy, legal_moves)  # type: ignore[attr-defined]
        self.session.handle_board_click(move.from_square)
        if move.to_square in self.session.state.legal_targets:
            self.session.handle_board_click(move.to_square)
            if self.session.state.pending_promotion is not None:
                self.session.handle_promotion_choice(chess.QUEEN)

        self._auto_bot_move_due = time.monotonic() + _AUTO_BOT_SPEEDS[self._auto_bot_speed_idx]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _chaos_director_mode(self) -> str:
        if not self.chaos_enabled:
            return "disabled"
        if self.claude_enabled and self.claude_available:
            return "hybrid"
        return "local"

    def _hud_view_state(self) -> HudViewState:
        return HudViewState(
            game_mode=self.game_mode if self.game_mode != GameMode.BOT_VS_BOT else GameMode.LOCAL_PVP,
            chaos_enabled=self.chaos_enabled,
            claude_enabled=self.claude_enabled and self.claude_available and self.chaos_enabled,
            claude_available=self.claude_available,
        )

    @staticmethod
    def _bot_config_from_difficulty(difficulty: str) -> BotConfig:
        if difficulty == "stockfish_easy":
            return BotConfig(mode=BotMode.STOCKFISH, stockfish_think_time_seconds=0.1)
        if difficulty == "stockfish_hard":
            return BotConfig(mode=BotMode.STOCKFISH, stockfish_think_time_seconds=1.0)
        return BotConfig(mode=BotMode.SIMPLE)
