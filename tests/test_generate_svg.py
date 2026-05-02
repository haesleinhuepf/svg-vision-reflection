"""Tests for svg_vision_reflection.generate_svg."""
import base64
import types
from unittest.mock import MagicMock, patch

import pytest

from svg_vision_reflection import generate_svg
from svg_vision_reflection._generate import _extract_svg, _svg_to_png_base64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
    '<rect width="10" height="10" fill="red"/>'
    "</svg>"
)


def _make_completion(content: str):
    """Return a minimal fake openai ChatCompletion object."""
    choice = MagicMock()
    choice.message.content = content
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def _make_client(*svg_responses: str) -> MagicMock:
    """Return a fake OpenAI client whose chat.completions.create cycles through
    the given SVG strings (each returned as the message content)."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _make_completion(r) for r in svg_responses
    ]
    return client


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


class TestExtractSvg:
    def test_bare_svg(self):
        assert _extract_svg(MINIMAL_SVG) == MINIMAL_SVG

    def test_markdown_svg_block(self):
        wrapped = f"```svg\n{MINIMAL_SVG}\n```"
        assert _extract_svg(wrapped) == MINIMAL_SVG

    def test_markdown_xml_block(self):
        wrapped = f"```xml\n{MINIMAL_SVG}\n```"
        assert _extract_svg(wrapped) == MINIMAL_SVG

    def test_markdown_generic_block(self):
        wrapped = f"```\n{MINIMAL_SVG}\n```"
        assert _extract_svg(wrapped) == MINIMAL_SVG

    def test_svg_with_surrounding_text(self):
        text = f"Here is your image:\n{MINIMAL_SVG}\nEnjoy!"
        assert _extract_svg(text) == MINIMAL_SVG

    def test_passthrough_when_no_svg(self):
        text = "Sorry, I cannot generate that."
        assert _extract_svg(text) == text


class TestSvgToPngBase64:
    def test_returns_valid_base64_png(self):
        result = _svg_to_png_base64(MINIMAL_SVG)
        raw = base64.b64decode(result)
        # PNG files start with the 8-byte PNG signature
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Integration-style tests for generate_svg (LLM calls are mocked)
# ---------------------------------------------------------------------------


class TestGenerateSvg:
    def test_returns_svg_string_no_history(self):
        # 1 initial call + 2 reflection calls
        client = _make_client(MINIMAL_SVG, MINIMAL_SVG, MINIMAL_SVG)
        result = generate_svg("a red square", openai_client=client)
        assert isinstance(result, str)
        assert "<svg" in result

    def test_num_reflections_controls_call_count(self):
        reflections = 3
        # 1 initial + 3 reflection calls
        client = _make_client(*([MINIMAL_SVG] * (1 + reflections)))
        generate_svg("a red square", num_reflections=reflections, openai_client=client)
        assert client.chat.completions.create.call_count == 1 + reflections

    def test_zero_reflections(self):
        client = _make_client(MINIMAL_SVG)
        result = generate_svg("a red square", num_reflections=0, openai_client=client)
        assert client.chat.completions.create.call_count == 1
        assert "<svg" in result

    def test_report_history_returns_tuple(self):
        client = _make_client(MINIMAL_SVG, MINIMAL_SVG, MINIMAL_SVG)
        result = generate_svg(
            "a red square", num_reflections=2, report_history=True, openai_client=client
        )
        assert isinstance(result, tuple)
        svg, history = result
        assert isinstance(svg, str)
        assert len(history) == 2

    def test_report_history_entries_are_svg_and_bytes(self):
        client = _make_client(MINIMAL_SVG, MINIMAL_SVG, MINIMAL_SVG)
        _svg, history = generate_svg(
            "a red square", num_reflections=2, report_history=True, openai_client=client
        )
        for svg_entry, png_bytes in history:
            assert isinstance(svg_entry, str)
            assert isinstance(png_bytes, bytes)
            # Each PNG blob should start with the PNG signature
            assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_reflection_request_includes_image(self):
        """The second (reflection) LLM call must include an image_url content block."""
        client = _make_client(MINIMAL_SVG, MINIMAL_SVG)
        generate_svg("a red square", num_reflections=1, openai_client=client)

        # The second call is the reflection call
        calls = client.chat.completions.create.call_args_list
        reflection_call_kwargs = calls[1][1]  # keyword args of second call
        messages = reflection_call_kwargs["messages"]
        content_blocks = messages[0]["content"]
        types_in_content = [block["type"] for block in content_blocks]
        assert "image_url" in types_in_content

    def test_markdown_wrapped_response_is_handled(self):
        wrapped = f"```svg\n{MINIMAL_SVG}\n```"
        client = _make_client(wrapped, wrapped, wrapped)
        result = generate_svg("a red square", num_reflections=2, openai_client=client)
        # Markdown fence should be stripped
        assert result.startswith("<svg")
