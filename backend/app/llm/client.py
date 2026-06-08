"""
LLM client — unified wrapper around gpt-5.5 (text + multimodal).

Rules:
  - openai.OpenAI constructed with base_url/api_key from settings.
  - chat() supports text with reasoning_effort and optional JSON mode.
  - locate() sends a screenshot + instruction and returns (x, y) in 0-1000 space.
  - Authorization/key never written to logs.
  - Retries on transient errors (rate-limit / server error); fast-fail on client errors.
"""
from __future__ import annotations

import base64
import logging
import time
from io import BytesIO
from typing import Any

import openai
from openai import OpenAI
from PIL.Image import Image

from app.config import settings

logger = logging.getLogger(__name__)

# Retry config
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2.0  # seconds; doubles each attempt

# Status codes that warrant a retry
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _should_retry(exc: openai.OpenAIError) -> bool:
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError) and exc.status_code in _RETRYABLE_STATUS:
        return True
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    return False


class LLMClient:
    """Thin, retrying wrapper around OpenAI SDK targeting gpt-5.5 at gpt.pkpp.cn."""

    def __init__(self) -> None:
        # api_key kept in object but never serialised / logged
        self._client = OpenAI(
            base_url=settings.gpt_base_url,
            api_key=settings.gpt_api_key,
        )
        self._model = settings.gpt_model
        self._reasoning = settings.gpt_reasoning

    # ------------------------------------------------------------------
    # Text interface
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        json_mode: bool = False,
    ) -> str:
        """Send a chat request and return the assistant text content.

        Args:
            messages: OpenAI-format message list.
            json_mode: If True, request JSON object response format.

        Returns:
            Stripped text content of the first choice.

        Raises:
            openai.OpenAIError: After all retries are exhausted.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "reasoning_effort": self._reasoning,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_exc: openai.OpenAIError | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                return (resp.choices[0].message.content or "").strip()
            except openai.OpenAIError as exc:
                # Never log the exception repr when it might embed auth headers
                safe_msg = type(exc).__name__
                if isinstance(exc, openai.APIStatusError):
                    safe_msg += f"(status={exc.status_code})"
                if not _should_retry(exc):
                    logger.error("LLM chat non-retryable error: %s", safe_msg)
                    raise
                last_exc = exc
                wait = _RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "LLM chat transient error %s, retry %d/%d in %.1fs",
                    safe_msg, attempt + 1, _MAX_RETRIES, wait,
                )
                time.sleep(wait)

        logger.error("LLM chat failed after %d retries", _MAX_RETRIES)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Vision / locate interface
    # ------------------------------------------------------------------

    def locate(self, image: Image, instruction: str) -> tuple[int, int]:
        """Given a screenshot and an instruction, return (x, y) in 0-1000 space.

        The model is expected to reply with JSON: {"x": <0-1000>, "y": <0-1000>}.

        Args:
            image: PIL Image of the device screen.
            instruction: Natural-language description of the target element.

        Returns:
            (x, y) normalised coordinates in [0, 1000].

        Raises:
            ValueError: If the model response cannot be parsed as valid coordinates.
            openai.OpenAIError: After all retries are exhausted.
        """
        img_b64 = _pil_to_b64(image)
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"{instruction}\n\n"
                            "Reply with ONLY valid JSON in this exact format: "
                            '{"x": <integer 0-1000>, "y": <integer 0-1000>}'
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            }
        ]

        raw = self.chat(messages, json_mode=True)
        return _parse_coords(raw)


# ------------------------------------------------------------------
# Module-level singleton (lazy, reused across callers)
# ------------------------------------------------------------------

_client_instance: LLMClient | None = None


def get_client() -> LLMClient:
    """Return the shared LLMClient singleton."""
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _pil_to_b64(image: Image) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _parse_coords(raw: str) -> tuple[int, int]:
    """Parse {"x": ..., "y": ...} JSON and validate 0-1000 range."""
    import json

    try:
        data = json.loads(raw)
        x = int(data["x"])
        y = int(data["y"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Cannot parse locate response: {raw!r}") from exc

    if not (0 <= x <= 1000 and 0 <= y <= 1000):
        raise ValueError(f"Coordinates out of 0-1000 range: x={x}, y={y}")

    return x, y
