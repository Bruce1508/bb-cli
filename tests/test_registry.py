"""
Tests for bb/adapters/registry.py

Success criteria:
- register() decorator adds a class to the registry under the given name
- get_adapter() returns the registered class by name
- get_adapter() raises KeyError for unknown names
- Registering the same name twice overwrites the first entry
- discover_adapters() returns a dict of all currently registered adapters
- Registry state is isolated between tests (no cross-test pollution)
"""
import pytest

from bb.adapters.base import LMSAdapter
from bb.adapters.registry import _registry, discover_adapters, get_adapter, register


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(name: str = "test_adapter") -> type[LMSAdapter]:
    """Build a minimal concrete LMSAdapter subclass for testing."""
    class _Adapter(LMSAdapter):
        def authenticate(self) -> None: ...
        def check_session(self) -> str: return "fresh"
        def fetch_activity_stream(self): return []
        def fetch_grades(self): return []
        def fetch_course_content(self, course_id: str): return {}
    _Adapter.__name__ = name
    return _Adapter


# Use a fixture to restore _registry after each test
import pytest

@pytest.fixture(autouse=True)
def _clean_registry():
    """Restore the registry to its original state after every test."""
    original = dict(_registry)
    yield
    _registry.clear()
    _registry.update(original)


# ---------------------------------------------------------------------------
# register() decorator
# ---------------------------------------------------------------------------


def test_register_adds_class_to_registry():
    adapter_cls = _make_adapter()
    register("test_lms")(adapter_cls)
    assert "test_lms" in _registry


def test_register_returns_the_original_class():
    adapter_cls = _make_adapter()
    result = register("test_lms")(adapter_cls)
    assert result is adapter_cls


def test_register_as_decorator_works():
    @register("decorated_lms")
    class MyAdapter(LMSAdapter):
        def authenticate(self) -> None: ...
        def check_session(self) -> str: return "fresh"
        def fetch_activity_stream(self): return []
        def fetch_grades(self): return []
        def fetch_course_content(self, course_id: str): return {}

    assert "decorated_lms" in _registry
    assert _registry["decorated_lms"] is MyAdapter


def test_register_overwrites_existing_name():
    cls_a = _make_adapter("AdapterA")
    cls_b = _make_adapter("AdapterB")
    register("same_name")(cls_a)
    register("same_name")(cls_b)
    assert _registry["same_name"] is cls_b


# ---------------------------------------------------------------------------
# get_adapter()
# ---------------------------------------------------------------------------


def test_get_adapter_returns_registered_class():
    adapter_cls = _make_adapter()
    register("my_lms")(adapter_cls)
    result = get_adapter("my_lms")
    assert result is adapter_cls


def test_get_adapter_raises_key_error_for_unknown_name():
    with pytest.raises(KeyError):
        get_adapter("nonexistent_lms")


def test_get_adapter_error_message_includes_name():
    with pytest.raises(KeyError, match="nonexistent_lms"):
        get_adapter("nonexistent_lms")


def test_get_adapter_returned_class_is_instantiable():
    adapter_cls = _make_adapter()
    register("my_lms")(adapter_cls)
    cls = get_adapter("my_lms")
    instance = cls()
    assert isinstance(instance, LMSAdapter)


# ---------------------------------------------------------------------------
# discover_adapters()
# ---------------------------------------------------------------------------


def test_discover_adapters_returns_dict():
    result = discover_adapters()
    assert isinstance(result, dict)


def test_discover_adapters_includes_registered_adapter():
    adapter_cls = _make_adapter()
    register("discovered_lms")(adapter_cls)
    result = discover_adapters()
    assert "discovered_lms" in result
    assert result["discovered_lms"] is adapter_cls


def test_discover_adapters_returns_all_registered():
    cls_a = _make_adapter("A")
    cls_b = _make_adapter("B")
    register("lms_a")(cls_a)
    register("lms_b")(cls_b)
    result = discover_adapters()
    assert "lms_a" in result
    assert "lms_b" in result


def test_discover_adapters_returns_copy_not_reference():
    """Mutating the returned dict must not affect the internal registry."""
    result = discover_adapters()
    result["injected"] = _make_adapter()
    assert "injected" not in _registry
