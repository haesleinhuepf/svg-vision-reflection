import base64
import re

import cairosvg
import openai


def _extract_svg(text: str) -> str:
    """Extract SVG content from a potentially markdown-wrapped LLM response."""
    # Try to find SVG within a code block first
    match = re.search(r"```(?:svg|xml)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        if "<svg" in candidate.lower():
            return candidate

    # Fall back to extracting the raw <svg>...</svg> block
    match = re.search(r"(<svg[\s\S]*?</svg>)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Return as-is if nothing else matches
    return text.strip()


def _svg_to_png_base64(svg_content: str) -> str:
    """Convert an SVG string to a base-64-encoded PNG string."""
    png_bytes = cairosvg.svg2png(bytestring=svg_content.encode("utf-8"))
    return base64.b64encode(png_bytes).decode("utf-8")


def generate_svg(
    prompt: str,
    num_reflections: int = 2,
    report_history: bool = False,
    model: str = "gpt-4o",
    openai_client: openai.OpenAI = None,
):
    """Generate an SVG image from a text prompt using an LLM and iterative visual reflection.

    Parameters
    ----------
    prompt : str
        A natural-language description of what the SVG should show.
    num_reflections : int, optional
        Number of vision-based refinement iterations (default: 2).
    report_history : bool, optional
        When *True* the function returns a tuple ``(svg, history)`` where
        *history* is a list of ``(svg_str, png_bytes)`` tuples captured after
        each reflection step.
    model : str, optional
        OpenAI model to use (default: ``"gpt-4o"``).
    openai_client : openai.OpenAI, optional
        A pre-configured OpenAI client instance.  A default client is created
        from environment variables when *None*.

    Returns
    -------
    str or tuple
        The final SVG content as a string.  When *report_history* is *True*,
        returns ``(svg_str, history)`` where *history* is a list of
        ``(svg_str, png_bytes)`` tuples (one entry per reflection iteration).
    """
    client = openai_client or openai.OpenAI()

    # ------------------------------------------------------------------
    # Step 1 – ask the model to produce an initial SVG
    # ------------------------------------------------------------------
    initial_response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Create an SVG image that shows: {prompt}. "
                    "Return ONLY the raw SVG code with no explanation or markdown."
                ),
            }
        ],
    )
    svg_content = _extract_svg(initial_response.choices[0].message.content)

    history: list[tuple[str, bytes]] = []

    # ------------------------------------------------------------------
    # Step 2 – iterative reflection loop
    # ------------------------------------------------------------------
    for _ in range(num_reflections):
        # Render the current SVG to PNG so the model can *see* it
        png_bytes = cairosvg.svg2png(bytestring=svg_content.encode("utf-8"))
        png_base64 = base64.b64encode(png_bytes).decode("utf-8")

        history.append((svg_content, png_bytes))

        refine_response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"The SVG below should show: {prompt}.\n"
                                "The rendered PNG is attached so you can see how it looks. "
                                "If the image does not accurately represent the description, "
                                "please refine the SVG. "
                                "Return ONLY the improved SVG code with no explanation or markdown."
                            ),
                        },
                        {
                            "type": "text",
                            "text": f"Current SVG:\n{svg_content}",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{png_base64}"
                            },
                        },
                    ],
                }
            ],
        )
        svg_content = _extract_svg(refine_response.choices[0].message.content)

    if report_history:
        return svg_content, history

    return svg_content
