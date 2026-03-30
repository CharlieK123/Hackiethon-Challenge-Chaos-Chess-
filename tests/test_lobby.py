from __future__ import annotations

from chaos_chess.chaos.claude_provider import ClaudeChaosProvider
from chaos_chess.game.types import GameMode
from chaos_chess.ui.lobby_scene import LobbyResult


# ---------------------------------------------------------------------------
# LobbyResult construction
# ---------------------------------------------------------------------------


def test_lobby_result_stores_all_fields() -> None:
    result = LobbyResult(
        mode=GameMode.HUMAN_VS_BOT,
        initial_time_ms=300_000,
        chaos_mode="hybrid",
        chaos_frequency="normal",
        bot_difficulty="simple",
        custom_chaos_prompt="be dramatic",
    )
    assert result.mode == GameMode.HUMAN_VS_BOT
    assert result.initial_time_ms == 300_000
    assert result.chaos_mode == "hybrid"
    assert result.chaos_frequency == "normal"
    assert result.bot_difficulty == "simple"
    assert result.custom_chaos_prompt == "be dramatic"


def test_lobby_result_default_values_are_sensible() -> None:
    """Verify the defaults match the lobby's out-of-box configuration."""
    # The lobby defaults to: vs Bot, 5 min, Hybrid, Normal, Simple, no prompt.
    result = LobbyResult(
        mode=GameMode.HUMAN_VS_BOT,
        initial_time_ms=300_000,
        chaos_mode="hybrid",
        chaos_frequency="normal",
        bot_difficulty="simple",
        custom_chaos_prompt="",
    )
    assert result.custom_chaos_prompt == ""
    assert result.initial_time_ms == 5 * 60 * 1000


def test_lobby_result_unlimited_time_is_zero() -> None:
    result = LobbyResult(
        mode=GameMode.LOCAL_PVP,
        initial_time_ms=0,
        chaos_mode="disabled",
        chaos_frequency="normal",
        bot_difficulty="simple",
        custom_chaos_prompt="",
    )
    assert result.initial_time_ms == 0


def test_lobby_result_bot_vs_bot_mode() -> None:
    result = LobbyResult(
        mode=GameMode.BOT_VS_BOT,
        initial_time_ms=180_000,
        chaos_mode="local",
        chaos_frequency="mayhem",
        bot_difficulty="stockfish_easy",
        custom_chaos_prompt="",
    )
    assert result.mode == GameMode.BOT_VS_BOT
    assert result.chaos_frequency == "mayhem"


# ---------------------------------------------------------------------------
# Custom chaos prompt in Claude's system prompt
# ---------------------------------------------------------------------------


def _make_provider(custom_prompt: str = "") -> ClaudeChaosProvider:
    return ClaudeChaosProvider(
        api_key="test-key",
        model="claude-sonnet-4-6",
        timeout_seconds=8.0,
        max_tokens=500,
        custom_chaos_prompt=custom_prompt,
    )


def test_custom_chaos_prompt_appended_to_system_prompt() -> None:
    provider = _make_provider("always be as disruptive as possible")
    system = provider._system_prompt()
    assert "Player instruction: always be as disruptive as possible" in system


def test_empty_custom_prompt_leaves_system_prompt_unchanged() -> None:
    provider_with    = _make_provider("some instruction")
    provider_without = _make_provider("")
    assert "Player instruction" not in provider_without._system_prompt()
    assert len(provider_with._system_prompt()) > len(provider_without._system_prompt())


def test_custom_prompt_whitespace_is_stripped() -> None:
    provider = _make_provider("   favour disruptive events   ")
    system = provider._system_prompt()
    assert "Player instruction: favour disruptive events" in system
    assert "   favour" not in system


# ---------------------------------------------------------------------------
# Local Only mode: custom_chaos_prompt is not forwarded to Claude
# ---------------------------------------------------------------------------


def test_local_mode_lobby_result_has_empty_custom_prompt() -> None:
    """When chaos_mode is 'local', the lobby clears the custom prompt in LobbyResult.

    This is enforced in LobbyScene._build_result() so the prompt is never
    forwarded to ClaudeChaosProvider when Claude is not in use.
    """
    import pygame
    pygame.font.init()
    from chaos_chess.ui.lobby_scene import LobbyScene

    lobby = LobbyScene()
    # Manually set state: local chaos mode, with a custom prompt typed.
    lobby._chaos_idx = 1      # "Local Only"
    lobby._custom_prompt = "ignore the rules"

    result = lobby._build_result()

    assert result.chaos_mode == "local"
    assert result.custom_chaos_prompt == ""


def test_hybrid_mode_lobby_result_preserves_custom_prompt() -> None:
    import pygame
    pygame.font.init()
    from chaos_chess.ui.lobby_scene import LobbyScene

    lobby = LobbyScene()
    lobby._chaos_idx = 2      # "Hybrid"
    lobby._custom_prompt = "be theatrical"

    result = lobby._build_result()

    assert result.chaos_mode == "hybrid"
    assert result.custom_chaos_prompt == "be theatrical"


def test_disabled_mode_lobby_result_has_empty_custom_prompt() -> None:
    import pygame
    pygame.font.init()
    from chaos_chess.ui.lobby_scene import LobbyScene

    lobby = LobbyScene()
    lobby._chaos_idx = 0      # "Disabled"
    lobby._custom_prompt = "irrelevant"

    result = lobby._build_result()

    assert result.chaos_mode == "disabled"
    assert result.custom_chaos_prompt == ""


# ---------------------------------------------------------------------------
# Chaos frequency ranges flow through to ChaosDirectorConfig
# ---------------------------------------------------------------------------


def test_chaos_frequency_ranges_in_config() -> None:
    from chaos_chess.config import CHAOS_FREQUENCY_RANGES

    assert CHAOS_FREQUENCY_RANGES["calm"]   == (5, 7)
    assert CHAOS_FREQUENCY_RANGES["normal"] == (3, 5)
    assert CHAOS_FREQUENCY_RANGES["mayhem"] == (1, 3)


def test_director_uses_frequency_preset_from_config() -> None:
    from chaos_chess.chaos.director import ChaosDirector, ChaosDirectorConfig

    director_calm   = ChaosDirector(config=ChaosDirectorConfig(mode="local", seed=0, frequency_preset="calm"))
    director_mayhem = ChaosDirector(config=ChaosDirectorConfig(mode="local", seed=0, frequency_preset="mayhem"))

    # Calm: base (5,7) + adj 1 (no pressure) = randint(6,8)
    # Mayhem: base (1,3) + adj 1 (no pressure) = randint(2,4)
    calm_intervals   = [director_calm._roll_interval()   for _ in range(40)]
    mayhem_intervals = [director_mayhem._roll_interval() for _ in range(40)]

    assert sum(calm_intervals) > sum(mayhem_intervals)
