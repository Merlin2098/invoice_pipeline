import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_SMOKE") != "1",
    reason="Exploratory Ollama smoke test disabled by default.",
)


def test_ollama_smoke_placeholder() -> None:
    assert True
