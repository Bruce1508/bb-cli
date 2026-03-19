from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bb.adapters.base import LMSAdapter

_registry: dict[str, type["LMSAdapter"]] = {}


def register(name: str):
    """Decorator to register an LMSAdapter subclass under a name.

    Usage:
        @register("blackboard_ultra")
        class BlackboardUltraAdapter(LMSAdapter):
            ...
    """
    def decorator(cls: type["LMSAdapter"]) -> type["LMSAdapter"]:
        _registry[name] = cls
        return cls
    return decorator


def get_adapter(name: str) -> type["LMSAdapter"]:
    """Return the adapter class registered under `name`.

    Raises KeyError if no adapter is registered for that name.
    """
    if name not in _registry:
        raise KeyError(f"No adapter registered for '{name}'")
    return _registry[name]


def discover_adapters() -> dict[str, type["LMSAdapter"]]:
    """Return a shallow copy of all currently registered adapters.

    Returns a copy so callers cannot mutate the internal registry.
    """
    return dict(_registry)
