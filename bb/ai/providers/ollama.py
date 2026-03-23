"""Ollama provider helpers — availability check and model selection."""
from __future__ import annotations

# Preferred models in priority order (best tool-calling accuracy first)
_DEFAULT_PRIORITY = [
    "qwen3:30b-a3b",
    "qwen3:8b",
    "qwen2.5:7b",
    "llama3.2:3b",
]


def is_available() -> bool:
    """Return True if the Ollama server is reachable."""
    try:
        import ollama
        ollama.list()
        return True
    except Exception:
        return False


def get_model(preferred: str) -> str | None:
    """Return the best available Ollama model name.

    Args:
        preferred: model name from config (empty string = use default priority).

    Returns the first match using this logic:
    1. If preferred is set and is an exact match → return it.
    2. If preferred is set and a model with the same base name exists → return it.
    3. Walk _DEFAULT_PRIORITY, returning the first model present on the server.
    4. Return None if nothing matches.
    """
    try:
        import ollama
        response = ollama.list()
    except Exception:
        return None

    available = [m.model for m in response.models]

    if preferred:
        # Exact match first
        if preferred in available:
            return preferred
        # Base-name fallback (e.g. "qwen3:30b-a3b" → look for any "qwen3" model)
        base = preferred.split(":")[0]
        match = next((n for n in available if base in n), None)
        if match:
            return match

    # Walk default priority list
    for candidate in _DEFAULT_PRIORITY:
        if candidate in available:
            return candidate
        base = candidate.split(":")[0]
        match = next((n for n in available if base in n), None)
        if match:
            return match

    return None
