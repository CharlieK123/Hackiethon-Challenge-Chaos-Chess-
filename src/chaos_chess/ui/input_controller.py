from __future__ import annotations

from dataclasses import dataclass

import pygame

from chaos_chess.game.types import PromotionPrompt
from chaos_chess.ui.board_renderer import BoardRenderer
from chaos_chess.ui.hud_renderer import HudRenderer, HudViewState


@dataclass(slots=True, frozen=True)
class InputAction:
    kind: str
    square: int | None = None
    promotion_piece: int | None = None


class InputController:
    def __init__(self, board_renderer: BoardRenderer, hud_renderer: HudRenderer) -> None:
        self.board_renderer = board_renderer
        self.hud_renderer = hud_renderer

    def gather_actions(
        self,
        events: list[pygame.event.Event],
        pending_promotion: PromotionPrompt | None,
        hud_view_state: HudViewState,
    ) -> list[InputAction]:
        actions: list[InputAction] = []
        for event in events:
            if event.type == pygame.QUIT:
                actions.append(InputAction(kind="quit"))
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    actions.append(InputAction(kind="restart"))
                elif event.key == pygame.K_p:
                    actions.append(InputAction(kind="toggle_mode"))
                elif event.key == pygame.K_c:
                    actions.append(InputAction(kind="toggle_chaos"))
                elif event.key == pygame.K_d:
                    actions.append(InputAction(kind="toggle_claude"))
                elif event.key == pygame.K_f:
                    actions.append(InputAction(kind="speed_up"))
                elif event.key == pygame.K_g:
                    actions.append(InputAction(kind="speed_down"))
                continue

            if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
                continue

            if pending_promotion is not None:
                promotion_piece = self.board_renderer.promotion_piece_at_position(
                    event.pos,
                    pending_promotion,
                )
                if promotion_piece is not None:
                    actions.append(
                        InputAction(kind="promotion", promotion_piece=promotion_piece)
                    )
                    continue

            button_kind = self.hud_renderer.button_at_position(event.pos, hud_view_state)
            if button_kind is not None:
                actions.append(InputAction(kind=button_kind))
                continue

            square = self.board_renderer.square_at_position(event.pos)
            if square is not None:
                actions.append(InputAction(kind="board_click", square=square))

        return actions
