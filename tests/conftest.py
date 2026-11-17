import sys

import pytest


@pytest.fixture(autouse=True)
def _ollama_module_and_package_attr_agree():
    """Tests delitem sys.modules["bb.ai.providers.ollama"] and re-import it. After teardown
    sys.modules holds the original module but the package attribute still points at the
    re-imported one, so string patch targets ("bb.ai.providers.ollama.x") miss the module
    that `from bb.ai.providers.ollama import x` returns. Re-sync them after every test."""
    yield
    mod = sys.modules.get("bb.ai.providers.ollama")
    pkg = sys.modules.get("bb.ai.providers")
    if mod is not None and pkg is not None:
        pkg.ollama = mod
