import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gui_actions  # noqa: E402


def test_module_exports_three_public_functions():
    assert callable(gui_actions.focus_app)  # nosec B101
    assert callable(gui_actions.observe_frontmost)  # nosec B101
    assert callable(gui_actions.is_accessibility_permitted)  # nosec B101


def test_module_constants_match_spec():
    assert gui_actions.MAX_ELEMENTS == 250  # nosec B101
    assert gui_actions.MAX_DEPTH == 15  # nosec B101
