import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import computer_use  # noqa: E402


def test_module_exports_run_computer_goal():
    assert callable(computer_use.run_computer_goal)  # nosec B101


def test_module_constants_match_plan():
    assert computer_use.MAX_TURNS == 25  # nosec B101
    assert computer_use.MAX_SCALED_DIM == 1280  # nosec B101
    assert computer_use.COMPUTER_TOOL_TYPE == "computer_20250124"  # nosec B101
    assert computer_use.COMPUTER_USE_BETA == "computer-use-2025-01-24"  # nosec B101


def test_default_model_falls_back_when_env_unset(monkeypatch):
    monkeypatch.delenv("JARVIS_COMPUTER_MODEL", raising=False)
    assert computer_use._model() == "claude-sonnet-4-5-20250929"  # nosec B101


def test_default_model_honors_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_COMPUTER_MODEL", "claude-opus-4-7-20251015")
    assert computer_use._model() == "claude-opus-4-7-20251015"  # nosec B101
