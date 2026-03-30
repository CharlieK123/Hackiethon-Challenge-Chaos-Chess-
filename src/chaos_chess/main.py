from __future__ import annotations

import pygame

from chaos_chess.config import WINDOW_HEIGHT, WINDOW_TITLE, WINDOW_WIDTH
from chaos_chess.ui.lobby_scene import LobbyScene


def main() -> int:
    pygame.init()
    pygame.font.init()
    pygame.display.set_caption(WINDOW_TITLE)
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))

    # Import here so GameScene re-uses the already-initialised display.
    from chaos_chess.ui.game_scene import GameScene

    while True:
        lobby = LobbyScene()
        lobby_result = lobby.run(screen)

        if lobby_result is None:
            break

        scene = GameScene(lobby_result=lobby_result)
        result = scene.run()

        if result != "lobby":
            break

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
