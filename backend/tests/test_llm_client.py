"""
Unit tests for app.llm.client and app.llm.prompts.
All openai calls are mocked — no real API is invoked.
conftest.py stubs app.config.settings before any import.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image as PILImage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completion(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _tiny_image() -> PILImage.Image:
    return PILImage.new("RGB", (1, 1), color=(255, 255, 255))


# ---------------------------------------------------------------------------
# LLMClient.chat — happy path
# ---------------------------------------------------------------------------

class TestLLMClientChat:
    def test_chat_returns_content(self):
        from app.llm.client import LLMClient
        client = LLMClient()
        client._client.chat.completions.create = MagicMock(
            return_value=_make_completion("hello")
        )
        assert client.chat([{"role": "user", "content": "hi"}]) == "hello"

    def test_chat_passes_json_mode(self):
        from app.llm.client import LLMClient
        payload = json.dumps({"score": 85, "reasons": ["good fit"]})
        mock_create = MagicMock(return_value=_make_completion(payload))
        client = LLMClient()
        client._client.chat.completions.create = mock_create
        result = client.chat([{"role": "user", "content": "score me"}], json_mode=True)
        assert result == payload
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_chat_passes_reasoning_effort(self):
        from app.llm.client import LLMClient
        mock_create = MagicMock(return_value=_make_completion("ok"))
        client = LLMClient()
        client._client.chat.completions.create = mock_create
        client.chat([{"role": "user", "content": "x"}])
        assert mock_create.call_args.kwargs["reasoning_effort"] == "high"

    def test_chat_strips_whitespace(self):
        from app.llm.client import LLMClient
        client = LLMClient()
        client._client.chat.completions.create = MagicMock(
            return_value=_make_completion("  trimmed  ")
        )
        assert client.chat([]) == "trimmed"


# ---------------------------------------------------------------------------
# LLMClient.chat — retry logic
# ---------------------------------------------------------------------------

class TestLLMClientRetry:
    def test_retries_on_rate_limit_then_succeeds(self):
        import openai as oai
        from app.llm.client import LLMClient

        calls = {"n": 0}

        def side_effect(**_kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise oai.RateLimitError(
                    "rate limited", response=MagicMock(status_code=429), body={}
                )
            return _make_completion("ok")

        client = LLMClient()
        with patch.object(client._client.chat.completions, "create", side_effect=side_effect):
            with patch("app.llm.client.time.sleep"):
                result = client.chat([])
        assert result == "ok"
        assert calls["n"] == 3

    def test_no_retry_on_auth_error(self):
        import openai as oai
        from app.llm.client import LLMClient

        client = LLMClient()
        with patch.object(
            client._client.chat.completions,
            "create",
            side_effect=oai.AuthenticationError(
                "bad key", response=MagicMock(status_code=401), body={}
            ),
        ):
            with pytest.raises(oai.AuthenticationError):
                client.chat([])

    def test_exhausts_retries_and_raises(self):
        import openai as oai
        from app.llm.client import LLMClient

        client = LLMClient()
        with patch.object(
            client._client.chat.completions,
            "create",
            side_effect=oai.RateLimitError(
                "rate limited", response=MagicMock(status_code=429), body={}
            ),
        ):
            with patch("app.llm.client.time.sleep"):
                with pytest.raises(oai.RateLimitError):
                    client.chat([])


# ---------------------------------------------------------------------------
# LLMClient.locate
# ---------------------------------------------------------------------------

class TestLLMClientLocate:
    def test_locate_returns_coords(self):
        from app.llm.client import LLMClient
        client = LLMClient()
        client._client.chat.completions.create = MagicMock(
            return_value=_make_completion(json.dumps({"x": 500, "y": 750}))
        )
        assert client.locate(_tiny_image(), "tap the button") == (500, 750)

    def test_locate_sends_image_url(self):
        from app.llm.client import LLMClient
        mock_create = MagicMock(
            return_value=_make_completion(json.dumps({"x": 100, "y": 200}))
        )
        client = LLMClient()
        client._client.chat.completions.create = mock_create
        client.locate(_tiny_image(), "some target")
        msgs = mock_create.call_args.kwargs["messages"]
        types = [block["type"] for block in msgs[0]["content"]]
        assert "image_url" in types

    def test_locate_raises_on_bad_json(self):
        from app.llm.client import LLMClient
        client = LLMClient()
        client._client.chat.completions.create = MagicMock(
            return_value=_make_completion("not json")
        )
        with pytest.raises(ValueError, match="Cannot parse locate response"):
            client.locate(_tiny_image(), "button")

    def test_locate_raises_on_out_of_range(self):
        from app.llm.client import LLMClient
        client = LLMClient()
        client._client.chat.completions.create = MagicMock(
            return_value=_make_completion(json.dumps({"x": 1500, "y": 0}))
        )
        with pytest.raises(ValueError, match="out of 0-1000 range"):
            client.locate(_tiny_image(), "button")

    def test_locate_boundary_values(self):
        from app.llm.client import LLMClient
        for x, y in [(0, 0), (1000, 1000), (0, 1000), (1000, 0)]:
            client = LLMClient()
            client._client.chat.completions.create = MagicMock(
                return_value=_make_completion(json.dumps({"x": x, "y": y}))
            )
            assert client.locate(_tiny_image(), "target") == (x, y)


# ---------------------------------------------------------------------------
# get_client singleton
# ---------------------------------------------------------------------------

def test_get_client_returns_singleton():
    from app.llm.client import get_client
    c1 = get_client()
    c2 = get_client()
    assert c1 is c2


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

class TestPrompts:
    def setup_method(self):
        from app.llm import prompts
        self.p = prompts

    def test_build_screen_prompt_structure(self):
        msgs = self.p.build_screen_prompt("my profile", "senior python dev")
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "my profile" in msgs[1]["content"]
        assert "senior python dev" in msgs[1]["content"]

    def test_build_screen_prompt_system_mentions_json(self):
        msgs = self.p.build_screen_prompt("p", "j")
        assert "JSON" in msgs[0]["content"] or "json" in msgs[0]["content"].lower()

    def test_build_greeting_prompt_structure(self):
        msgs = self.p.build_greeting_prompt("I'm Alice", "backend engineer", "TechCorp")
        assert msgs[0]["role"] == "system"
        assert "TechCorp" in msgs[1]["content"]
        assert "Alice" in msgs[1]["content"]

    def test_build_greeting_prompt_no_company(self):
        msgs = self.p.build_greeting_prompt("I'm Bob", "dev")
        assert msgs[1]["role"] == "user"
        assert "Company:" not in msgs[1]["content"]

    def test_locate_instruction_includes_target(self):
        inst = self.p.locate_instruction("the '立即沟通' button")
        assert "立即沟通" in inst

    def test_locate_instruction_includes_context(self):
        inst = self.p.locate_instruction("submit btn", context="job detail page")
        assert "job detail page" in inst

    def test_locate_instruction_mentions_0_1000(self):
        inst = self.p.locate_instruction("x")
        assert "1000" in inst

    def test_locate_instruction_no_context(self):
        inst = self.p.locate_instruction("x")
        assert "Screen context" not in inst
