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


def test_normalize_role_tier_a_examples():
    assert gui_actions._normalize_role("AXButton") == ("button", "A")  # nosec B101
    assert gui_actions._normalize_role("AXLink") == ("link", "A")  # nosec B101
    assert gui_actions._normalize_role("AXTextField") == (
        "text_field",
        "A",
    )  # nosec B101
    assert gui_actions._normalize_role("AXTextArea") == ("text_area", "A")  # nosec B101
    assert gui_actions._normalize_role("AXCheckBox") == ("checkbox", "A")  # nosec B101
    assert gui_actions._normalize_role("AXRadioButton") == ("radio", "A")  # nosec B101
    assert gui_actions._normalize_role("AXMenuItem") == ("menu_item", "A")  # nosec B101
    assert gui_actions._normalize_role("AXMenuButton") == (
        "menu_button",
        "A",
    )  # nosec B101
    assert gui_actions._normalize_role("AXTab") == ("tab", "A")  # nosec B101
    assert gui_actions._normalize_role("AXStaticText") == ("text", "A")  # nosec B101
    assert gui_actions._normalize_role("AXRow") == ("row", "A")  # nosec B101
    assert gui_actions._normalize_role("AXCell") == ("cell", "A")  # nosec B101
    assert gui_actions._normalize_role("AXPopUpButton") == ("popup", "A")  # nosec B101
    assert gui_actions._normalize_role("AXComboBox") == ("combo", "A")  # nosec B101
    assert gui_actions._normalize_role("AXImage") == ("image", "A")  # nosec B101


def test_normalize_role_tier_b_examples():
    assert gui_actions._normalize_role("AXWindow") == ("window", "B")  # nosec B101
    assert gui_actions._normalize_role("AXToolbar") == ("toolbar", "B")  # nosec B101
    assert gui_actions._normalize_role("AXMenuBar") == ("menu_bar", "B")  # nosec B101
    assert gui_actions._normalize_role("AXMenu") == ("menu", "B")  # nosec B101
    assert gui_actions._normalize_role("AXTabGroup") == ("tab_group", "B")  # nosec B101


def test_normalize_role_ignored_returns_none_pair():
    for role in (
        "AXGroup",
        "AXScrollArea",
        "AXLayoutItem",
        "AXSplitter",
        "AXSplitGroup",
        "AXOutline",
        "AXList",
        "AXTable",
        "AXNotAThing",
        "",
    ):
        assert gui_actions._normalize_role(role) == (None, None), role  # nosec B101
