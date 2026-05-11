"""Live macOS tests for gui_actions. Run with: uv run pytest -m macos -v

Requirements: macOS, Accessibility permission granted to whichever process
runs pytest (e.g. your terminal app or VS Code). Skipped by default.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gui_actions  # noqa: E402

pytestmark = pytest.mark.macos


def test_accessibility_permission_is_granted():
    assert (
        gui_actions.is_accessibility_permitted() is True
    ), (  # nosec B101
        "Grant Accessibility permission to the test runner before running -m macos"
    )


def test_focus_finder_then_observe_returns_a_menu_bar():
    result = gui_actions.focus_app("Finder")
    assert "Focused" in result  # nosec B101
    out = gui_actions.observe_frontmost()
    # Finder always has a menu_bar; this is the minimal end-to-end signal.
    assert "menu_bar" in out, out  # nosec B101
