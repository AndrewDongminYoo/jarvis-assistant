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


def test_focus_textedit_then_type_and_send_cmd_w():
    """Open TextEdit, type a short marker, then close the window with
    cmd+w (no save). The point is to verify the full FOCUS → TYPE → KEY
    pipeline works end-to-end."""
    import time

    assert "Focused" in gui_actions.focus_app("TextEdit")  # nosec B101
    time.sleep(0.5)
    # New document
    assert "Sent" in gui_actions.send_key("cmd+n")  # nosec B101
    time.sleep(0.5)
    # Type a small unique marker so we can recognize the window
    marker = "JARVIS-phase5-smoke"
    assert marker in gui_actions.type_text(marker)  # nosec B101
    time.sleep(0.3)
    # Close without saving (cmd+w then cmd+d for "Don't Save")
    assert "Sent" in gui_actions.send_key("cmd+w")  # nosec B101
    time.sleep(0.5)
    assert "Sent" in gui_actions.send_key("cmd+d")  # nosec B101


def test_scroll_does_not_raise_on_finder():
    """Smoke check: scroll posts a wheel event without raising. We don't
    assert anything about Finder's visible state — that's brittle. We
    only verify the function returns a success string."""
    assert "Focused" in gui_actions.focus_app("Finder")  # nosec B101
    result = gui_actions.scroll("down", 3)
    assert "Scrolled" in result  # nosec B101


def test_click_finder_menu_via_observe_vocabulary():
    """Focus Finder, observe its UI, find a menu_bar entry, click it,
    then send Escape to dismiss. The OBSERVE → CLICK vocabulary contract
    is what the LLM relies on; this verifies it holds against a real
    macOS app."""
    import time

    assert "Focused" in gui_actions.focus_app("Finder")  # nosec B101
    time.sleep(0.3)
    out = gui_actions.observe_frontmost()
    assert "menu_bar" in out, out  # nosec B101
    # "View" is a stable Finder menu title across recent macOS versions.
    # Top-level menu titles have AX role AXMenuBarItem (→ menu_bar_item),
    # not AXMenuButton — the latter is for popup-style buttons within
    # toolbars.
    result = gui_actions.click_element("menu_bar_item", "View")
    assert "Clicked" in result, result  # nosec B101
    time.sleep(0.3)
    # Dismiss
    gui_actions.send_key("escape")
