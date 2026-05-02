"""svg-vision-reflection

A small Python library that generates SVG images from text prompts using an
LLM and iteratively refines them by feeding the rendered PNG back into the
model (vision-based reflection).
"""

from ._generate import generate_svg

__all__ = ["generate_svg"]
