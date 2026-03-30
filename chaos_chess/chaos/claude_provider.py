from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

import chess

from chaos_chess.chaos.candidates import (
    frozen_piece_candidates,
    gust_shift_candidates,
    locked_square_candidates,
    slippery_square_candidates,
)
from chaos_chess.chaos.models import ChaosEvent
from chaos_chess.chaos.provider import ChaosEventProvider, ChaosProviderResponse
from chaos_chess.chaos.validator import ChaosValidator

if TYPE_CHECKING:
    from chaos_chess.chaos.personality import ChaosDirectorPersonality

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised only when the optional dependency is absent.
    anthropic = None


class ClaudeChaosProvider(ChaosEventProvider):
    """Ask Claude for one structured event, then validate it locally before use."""

    TOOL_NAME = "submit_chaos_event"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        custom_chaos_prompt: str = "",
    ) -> None:
        self._api_key = api_key.strip() if api_key is not None and api_key.strip() else None
        self._model = model.strip()
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._custom_chaos_prompt = custom_chaos_prompt.strip()
        if anthropic is not None and self._api_key is not None:
            self._client = anthropic.Anthropic(
                api_key=self._api_key,
                max_retries=0,
                timeout=self._timeout_seconds,
            )
        else:
            self._client = None
        # Context set by ChaosDirector before each generate_event call.
        self._personality: ChaosDirectorPersonality | None = None
        self._chaos_level: int = 1

    @property
    def name(self) -> str:
        return "Claude Chaos Director"

    def is_configured(self) -> bool:
        return anthropic is not None and self._api_key is not None

    def set_context(self, *, personality: object = None, chaos_level: int = 1) -> None:
        self._personality = personality  # type: ignore[assignment]
        self._chaos_level = max(1, min(4, chaos_level))

    def generate_event(self, board: chess.Board) -> ChaosProviderResponse:
        if not self.is_configured():
            return ChaosProviderResponse(event=None)

        try:
            message = self._request_message(board)
        except (anthropic.APIError, anthropic.APITimeoutError, anthropic.APIConnectionError):
            return self._warning_response("Claude Chaos Director was unavailable. Using local chaos instead.")

        payload = self._extract_tool_payload(message)
        if payload is None:
            return self._warning_response("Claude returned no usable chaos event. Using local chaos instead.")

        event = ChaosValidator.validate_payload(board, payload)
        if event is None:
            return self._warning_response("Claude proposed an invalid chaos event. Using local chaos instead.")

        dramatic = self.generate_description(event, board)
        if dramatic:
            event = dataclasses.replace(event, description=dramatic)

        return ChaosProviderResponse(event=event)

    def generate_description(self, event: ChaosEvent, board: chess.Board) -> str | None:
        """Make a lightweight second call to get a dramatic event description.

        Returns None on any failure so the caller can fall back to the original.
        """
        try:
            prompt = self._description_prompt(event, board)
            message = self._client.messages.create(
                model=self._model,
                max_tokens=80,
                system=(
                    "You write short, dramatic chess narration for a theatrical narrator. "
                    "Never mention Claude. Never use quotation marks."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            text = self._extract_text(message)
            return text.strip() if text and text.strip() else None
        except Exception:
            return None

    def _request_message(self, board: chess.Board):
        """Keep the Claude request shape in one place so it is easy to audit."""

        return self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": self._user_prompt(board),
                }
            ],
            tools=[self._tool_definition()],
            tool_choice={"type": "tool", "name": self.TOOL_NAME},
        )

    def _user_prompt(self, board: chess.Board) -> str:
        legal_moves = list(board.legal_moves)
        clock_pressure = self._chaos_level  # already mapped 1-4

        prompt_context = {
            "fen": board.fen(),
            "side_to_move": "white" if board.turn == chess.WHITE else "black",
            "legal_move_count": len(legal_moves),
            "locked_square_candidates": [
                chess.square_name(square) for square in locked_square_candidates(board, legal_moves)
            ],
            "frozen_piece_candidates": frozen_piece_candidates(board, legal_moves),
            "slippery_square_candidates": [
                chess.square_name(square) for square in slippery_square_candidates(board, legal_moves)
            ],
            "gust_shift_candidates": {
                "left": self._gust_context(board, -1),
                "right": self._gust_context(board, 1),
            },
            "chaos_level": self._chaos_level,
        }

        personality_section = ""
        if self._personality is not None:
            personality_section = f"\nGame history:\n{self._personality.to_prompt_context()}\n"
            dominant = self._personality.dominant_color
            last_event_type = (
                self._personality.events_fired[-1]["event_type"]
                if self._personality.events_fired
                else None
            )
            turn_count = self._personality.turn_count

            bias_lines: list[str] = []
            if dominant != "balanced":
                bias_lines.append(
                    f"- {dominant.capitalize()} is leading. Prefer events that disadvantage {dominant}."
                )
            if last_event_type == "gust_of_wind":
                bias_lines.append("- The last event was gust_of_wind. Avoid it this turn for variety.")
            if turn_count > 20:
                bias_lines.append(
                    "- The game is deep. Prefer frozen_piece or locked_squares to create tension."
                )

            if bias_lines:
                personality_section += "Strategic bias for this turn:\n" + "\n".join(bias_lines) + "\n"

        chaos_instruction = (
            f"\nThe chaos level is {self._chaos_level}/4. "
            "At higher levels, prefer more disruptive events and write more dramatic descriptions."
        )

        return (
            "Choose exactly one fair chaos event for the next turn.\n"
            "Use only the submit_chaos_event tool. Do not explain anything outside the tool call.\n"
            "Rules:\n"
            "- Never choose a chess move or recommend a chess move.\n"
            "- event_type must be one of gust_of_wind, locked_squares, frozen_piece, slippery_square.\n"
            "- duration_turns must be 1.\n"
            "- locked_squares must choose 1 to 3 unique squares from locked_square_candidates.\n"
            "- frozen_piece must choose exactly one piece from frozen_piece_candidates.\n"
            "- slippery_square must choose exactly one square from slippery_square_candidates.\n"
            "- gust_of_wind must use only shifts from gust_shift_candidates for a single direction.\n"
            "- Keep the event surprising but playable and fair.\n"
            "- description must be a single player-facing sentence.\n"
            f"{personality_section}"
            f"{chaos_instruction}\n\n"
            f"Board context:\n{json.dumps(prompt_context, indent=2)}"
        )

    def _description_prompt(self, event: ChaosEvent, board: chess.Board) -> str:
        side = "white" if board.turn == chess.WHITE else "black"

        material_parts: list[str] = []
        piece_values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
        white_mat = sum(v * len(board.pieces(pt, chess.WHITE)) for pt, v in piece_values.items())
        black_mat = sum(v * len(board.pieces(pt, chess.BLACK)) for pt, v in piece_values.items())
        diff = white_mat - black_mat
        if diff > 0:
            material_parts.append(f"white is ahead by {diff} point{'s' if diff != 1 else ''}")
        elif diff < 0:
            material_parts.append(f"black is ahead by {abs(diff)} point{'s' if diff != -1 else ''}")
        else:
            material_parts.append("material is equal")
        material_summary = material_parts[0]

        last_move_text = ""
        try:
            last_move = board.peek()
            last_move_text = f" The last move was {board.san(last_move)}."
        except Exception:
            pass

        return (
            f"Chess chaos event: {event.event_type.value}.\n"
            f"Details: {event.description}\n"
            f"Side to move: {side}. {material_summary.capitalize()}.{last_move_text}\n\n"
            "Write one dramatic sentence describing this chaos event from the perspective of a "
            "theatrical narrator. Reference the specific pieces or squares affected. "
            "Do not mention Claude. Do not use quotation marks."
        )

    @staticmethod
    def _extract_text(message) -> str | None:
        content = getattr(message, "content", None)
        if not isinstance(content, Iterable) or isinstance(content, (str, bytes)):
            return None
        for block in content:
            block_type = getattr(block, "type", None)
            block_text = getattr(block, "text", None)
            if block_type == "text" and isinstance(block_text, str):
                return block_text
        return None

    @staticmethod
    def _warning_response(message: str) -> ChaosProviderResponse:
        return ChaosProviderResponse(event=None, warning=message)

    def _system_prompt(self) -> str:
        base = (
            "You are the Chaos Director, a dramatic and cunning force that shapes this chess match.\n"
            "You remember every event you have fired and the flow of the game.\n"
            "When one player dominates, you intervene with disruptive chaos.\n"
            "When the game is close, you add subtle pressure.\n"
            "You have a flair for the dramatic. Your choices should feel intentional, not random.\n"
            "Generate exactly one chaos event as structured data.\n"
            "Never choose chess moves.\n"
            "Never add commentary outside the tool call.\n"
            "Return exactly one submit_chaos_event tool call."
        )
        if self._custom_chaos_prompt:
            return base + f"\n\nPlayer instruction: {self._custom_chaos_prompt}"
        return base

    def _gust_context(self, board: chess.Board, direction: int) -> dict[str, list[dict[str, str]]]:
        return {
            "white": gust_shift_candidates(board, direction, chess.WHITE),
            "black": gust_shift_candidates(board, direction, chess.BLACK),
        }

    @classmethod
    def _extract_tool_payload(cls, message) -> Mapping[str, object] | None:
        content = getattr(message, "content", None)
        if not isinstance(content, Iterable) or isinstance(content, (str, bytes)):
            return None

        for block in content:
            block_type = getattr(block, "type", None)
            block_name = getattr(block, "name", None)
            block_input = getattr(block, "input", None)

            if block_type is None and isinstance(block, Mapping):
                block_type = block.get("type")
                block_name = block.get("name")
                block_input = block.get("input")

            if (
                block_type == "tool_use"
                and block_name == cls.TOOL_NAME
                and isinstance(block_input, Mapping)
            ):
                return block_input

        return None

    @classmethod
    def _tool_definition(cls) -> dict[str, object]:
        string_schema = {"type": "string", "minLength": 1}
        shift_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["from_square", "to_square", "piece_type", "color"],
            "properties": {
                "from_square": {"type": "string"},
                "to_square": {"type": "string"},
                "piece_type": {
                    "type": "string",
                    "enum": ["pawn", "knight", "bishop", "rook", "queen", "king"],
                },
                "color": {"type": "string", "enum": ["white", "black"]},
            },
        }

        return {
            "name": cls.TOOL_NAME,
            "description": "Submit one structured chaos event for the next turn.",
            "input_schema": {
                "oneOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["event_type", "description", "duration_turns", "parameters"],
                        "properties": {
                            "event_type": {"type": "string", "enum": ["gust_of_wind"]},
                            "description": string_schema,
                            "duration_turns": {"type": "integer", "enum": [1]},
                            "parameters": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["direction", "targets", "shifts"],
                                "properties": {
                                    "direction": {"type": "string", "enum": ["left", "right"]},
                                    "targets": {"type": "string", "enum": ["non_king_pieces"]},
                                    "shifts": {
                                        "type": "array",
                                        "minItems": 1,
                                        "items": shift_schema,
                                    },
                                },
                            },
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["event_type", "description", "duration_turns", "parameters"],
                        "properties": {
                            "event_type": {"type": "string", "enum": ["locked_squares"]},
                            "description": string_schema,
                            "duration_turns": {"type": "integer", "enum": [1]},
                            "parameters": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["squares"],
                                "properties": {
                                    "squares": {
                                        "type": "array",
                                        "minItems": 1,
                                        "maxItems": 3,
                                        "items": {"type": "string"},
                                    }
                                },
                            },
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["event_type", "description", "duration_turns", "parameters"],
                        "properties": {
                            "event_type": {"type": "string", "enum": ["frozen_piece"]},
                            "description": string_schema,
                            "duration_turns": {"type": "integer", "enum": [1]},
                            "parameters": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["square", "piece_type", "color"],
                                "properties": {
                                    "square": {"type": "string"},
                                    "piece_type": {
                                        "type": "string",
                                        "enum": ["pawn", "knight", "bishop", "rook", "queen", "king"],
                                    },
                                    "color": {"type": "string", "enum": ["white", "black"]},
                                },
                            },
                        },
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["event_type", "description", "duration_turns", "parameters"],
                        "properties": {
                            "event_type": {"type": "string", "enum": ["slippery_square"]},
                            "description": string_schema,
                            "duration_turns": {"type": "integer", "enum": [1]},
                            "parameters": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["square"],
                                "properties": {
                                    "square": {"type": "string"},
                                },
                            },
                        },
                    },
                ]
            },
        }
