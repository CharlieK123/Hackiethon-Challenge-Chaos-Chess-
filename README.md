# Chaos Chess

Chaos Chess is a playable Python chess game built with `pygame` and `python-chess`. It supports human-vs-bot play, a 5+0 clock, local chaos events, and an optional Claude-powered "Chaos Director" that proposes structured chaos events with safe local fallback.

## Features

- Human vs bot gameplay with full standard chess rules
- 5+0 chess clocks with timeout handling
- Simple built-in bot that works without Stockfish
- Optional Stockfish integration with automatic fallback
- Local chaos engine with structured event validation
- Optional Claude Chaos Director for event generation only
- Safe fallback when Claude is unavailable or returns invalid data
- Restart button and testing toggles for chaos and Claude
- Event log, active event panel, move list, and polished board highlighting

## Installation

Requirements:

- Python 3.11+

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

`pygame-ce` is used because it imports as `pygame` and works reliably on newer Python versions.

## .env Setup

`run.py` automatically loads a local `.env` file from the project root.

Example:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
CHAOS_DIRECTOR_MODE=hybrid
CHAOS_DIRECTOR_MODEL=claude-sonnet-4-6
CHAOS_DIRECTOR_TIMEOUT_SECONDS=8.0
CHAOS_DIRECTOR_MAX_TOKENS=500

CHAOS_CHESS_BOT_MODE=auto
STOCKFISH_PATH=
CHAOS_CHESS_STOCKFISH_TIME_LIMIT=0.2
CHAOS_CHESS_FALLBACK_RANDOMNESS=18
```

Chaos modes:

- `hybrid`: try Claude first, then fall back to the local chaos generator
- `local`: use only local chaos generation
- `disabled`: turn chaos off entirely

Claude failure handling:

- missing API key: Claude is skipped automatically
- API error or timeout: local chaos is used instead
- invalid or unsafe event JSON: the event is rejected and regenerated locally

## Optional Stockfish Setup

Bot modes:

- `auto`: prefer Stockfish if available, otherwise use the built-in bot
- `stockfish`: try Stockfish first, but still fall back safely if it cannot start
- `simple`: always use the built-in material bot

To use Stockfish, either:

- add the Stockfish executable to your `PATH`, or
- set `STOCKFISH_PATH` in `.env`

Windows PowerShell example:

```powershell
$env:CHAOS_CHESS_BOT_MODE = "stockfish"
$env:STOCKFISH_PATH = "C:\tools\stockfish\stockfish-windows-x86-64-avx2.exe"
python run.py
```

If Stockfish is missing or fails to launch, the game falls back to the simple bot automatically.

## How To Run

From the project root:

```bash
python run.py
```

## Controls

- Left click a piece to select it
- Left click a highlighted square to move
- Click a promotion choice when a pawn promotes
- Press `R` or click `Restart` to start a new game
- Press `C` to toggle chaos on or off for testing
- Press `D` to toggle Claude-generated chaos on or off when Claude is configured

## Project Structure

```text
chaos_chess/
  run.py
  requirements.txt
  src/chaos_chess/
    bot/
    chaos/
    game/
    infra/
    ui/
  tests/
```

## Development Notes

- Claude is used only for chaos event generation, never for chess moves.
- All chaos events go through strict schema validation before application.
- The Pygame main loop does not block on Claude requests; chaos requests run in a background worker.
- The project includes tests for clocks, move legality, bots, chaos validation, and fallback behavior.
