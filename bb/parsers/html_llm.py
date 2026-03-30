"""LLM-based HTML parser — fallback when CSS selectors fail.

Uses a locally running Ollama model to extract structured data from raw HTML
chunks. Designed to be called by the Blackboard adapter when primary and
fallback CSS selectors both return zero items.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Return only a valid JSON array. No explanation, no markdown, no code blocks."
)


def extract_from_html(
    html_chunk: str,
    hint: str,
    ollama_model: str | None = None,
) -> list[dict]:
    """Use Ollama to extract structured items from HTML when CSS selectors fail.

    Args:
        html_chunk: Raw HTML string (trimmed, max ~8000 chars recommended).
        hint: What to extract, e.g. "course announcements" or "deadline items".
        ollama_model: Specific model name. If None, uses get_model("") priority list.

    Returns:
        List of dicts with extracted data. Returns [] if Ollama unavailable or fails.
        Never raises.
    """
    from bb.ai.providers.ollama import get_model

    model = ollama_model if ollama_model is not None else get_model("")
    if model is None:
        logger.debug("html_llm: Ollama unavailable, skipping LLM extraction")
        return []

    try:
        import ollama  # lazy — not installed in all environments

        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract {hint} from this HTML:\n\n{html_chunk}",
                },
            ],
            options={"num_predict": 2048},
        )

        raw = response.message.content
        parsed = json.loads(raw)

        if not isinstance(parsed, list):
            logger.debug(
                "html_llm: LLM returned non-list JSON (%s), discarding",
                type(parsed).__name__,
            )
            return []

        return parsed

    except Exception as exc:  # noqa: BLE001
        logger.debug("html_llm: extraction failed: %s", exc)
        return []
