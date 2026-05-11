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


def test_get_role_reads_from_dict():
    assert gui_actions._get_role({"role": "AXButton"}) == "AXButton"  # nosec B101
    assert gui_actions._get_role({}) == ""  # nosec B101


def test_get_children_reads_from_dict_default_empty():
    assert gui_actions._get_children({"children": [1, 2]}) == [1, 2]  # nosec B101
    assert gui_actions._get_children({}) == []  # nosec B101


def test_is_enabled_defaults_true():
    assert gui_actions._is_enabled({}) is True  # nosec B101
    assert gui_actions._is_enabled({"enabled": False}) is False  # nosec B101
    assert gui_actions._is_enabled({"enabled": True}) is True  # nosec B101


def test_get_attribute_dict_lowercase_mapping():
    el = {"title": "Send", "value": "hello", "description": "icon", "help": "?"}
    assert gui_actions._get_attribute(el, "AXTitle") == "Send"  # nosec B101
    assert gui_actions._get_attribute(el, "AXValue") == "hello"  # nosec B101
    assert gui_actions._get_attribute(el, "AXDescription") == "icon"  # nosec B101
    assert gui_actions._get_attribute(el, "AXHelp") == "?"  # nosec B101
    assert gui_actions._get_attribute(el, "AXFoo") is None  # nosec B101


def test_label_for_picks_title_first():
    el = {"title": "Save", "value": "ignored", "description": "ignored"}
    assert gui_actions._label_for(el) == "Save"  # nosec B101


def test_label_for_falls_through_to_value():
    el = {"title": "", "value": "hello"}
    assert gui_actions._label_for(el) == "hello"  # nosec B101


def test_label_for_falls_through_to_description_then_help():
    assert gui_actions._label_for({"description": "icon"}) == "icon"  # nosec B101
    assert gui_actions._label_for({"help": "tooltip"}) == "tooltip"  # nosec B101


def test_label_for_strips_whitespace():
    assert gui_actions._label_for({"title": "  Save  "}) == "Save"  # nosec B101


def test_label_for_returns_none_when_all_empty():
    assert gui_actions._label_for({}) is None  # nosec B101
    assert gui_actions._label_for({"title": "", "value": "  "}) is None  # nosec B101


def test_format_element_basic_button():
    line = gui_actions._format_element("button", "Send", None, True, 0)
    assert line == 'button "Send"'  # nosec B101


def test_format_element_indents_two_spaces_per_depth():
    line = gui_actions._format_element("button", "Reply", None, True, 2)
    assert line == '    button "Reply"'  # nosec B101


def test_format_element_disabled_appended():
    line = gui_actions._format_element("button", "Reply All", None, False, 1)
    assert line == '  button "Reply All" [disabled]'  # nosec B101


def test_format_element_text_field_with_value_distinct_from_label():
    line = gui_actions._format_element("text_field", "Search", "asyncio", True, 1)
    assert line == '  text_field "Search" "asyncio"'  # nosec B101


def test_format_element_text_field_with_value_equal_to_label_omits_duplicate():
    line = gui_actions._format_element("text_field", "Search", None, True, 0)
    assert line == 'text_field "Search"'  # nosec B101


def test_format_element_no_label_emits_bare_role():
    line = gui_actions._format_element("toolbar", None, None, True, 0)
    assert line == "toolbar"  # nosec B101


def test_format_element_no_label_with_disabled():
    line = gui_actions._format_element("toolbar", None, None, False, 1)
    assert line == "  toolbar [disabled]"  # nosec B101


def test_traverse_single_button():
    tree = {"role": "AXButton", "title": "Send"}
    lines = gui_actions._traverse(tree)
    assert lines == ['button "Send"']  # nosec B101


def test_traverse_tier_a_without_label_drops_self_keeps_walk():
    # AXButton with no label is treated like an ignored role: drop self,
    # recurse children at same depth.
    tree = {
        "role": "AXButton",
        "title": "",
        "children": [{"role": "AXStaticText", "title": "Send"}],
    }
    lines = gui_actions._traverse(tree)
    assert lines == ['text "Send"']  # nosec B101


def test_traverse_ignored_role_passes_through_at_same_depth():
    tree = {
        "role": "AXGroup",
        "children": [
            {"role": "AXButton", "title": "A"},
            {"role": "AXButton", "title": "B"},
        ],
    }
    lines = gui_actions._traverse(tree)
    assert lines == ['button "A"', 'button "B"']  # nosec B101


def test_traverse_disabled_flag():
    tree = {"role": "AXButton", "title": "Reply All", "enabled": False}
    lines = gui_actions._traverse(tree)
    assert lines == ['button "Reply All" [disabled]']  # nosec B101


def test_traverse_text_field_with_value():
    tree = {"role": "AXTextField", "title": "Search", "value": "asyncio"}
    lines = gui_actions._traverse(tree)
    assert lines == ['text_field "Search" "asyncio"']  # nosec B101


def test_traverse_text_field_value_only_uses_value_as_label():
    # No title; value becomes the label via _label_for. No duplicate.
    tree = {"role": "AXTextField", "value": "hello"}
    lines = gui_actions._traverse(tree)
    assert lines == ['text_field "hello"']  # nosec B101


def test_traverse_nested_tier_a_indents_one_per_level():
    # Two tier-A elements stacked (the second nested inside the first).
    # _traverse handles tier-A with tier-A children by indenting children.
    tree = {
        "role": "AXRow",
        "title": "Anna",
        "children": [{"role": "AXStaticText", "title": "Lunch tomorrow?"}],
    }
    lines = gui_actions._traverse(tree)
    assert lines == ['row "Anna"', '  text "Lunch tomorrow?"']  # nosec B101


def test_traverse_tier_b_emits_when_descendant_emits():
    tree = {
        "role": "AXWindow",
        "title": "Inbox",
        "children": [{"role": "AXButton", "title": "New Message"}],
    }
    lines = gui_actions._traverse(tree)
    assert lines == ['window "Inbox"', '  button "New Message"']  # nosec B101


def test_traverse_tier_b_elided_when_no_descendant_emits():
    tree = {
        "role": "AXToolbar",
        "children": [{"role": "AXGroup", "children": []}],
    }
    lines = gui_actions._traverse(tree)
    assert lines == []  # nosec B101


def test_traverse_tier_b_without_label_emits_bare_role():
    tree = {
        "role": "AXToolbar",
        "children": [{"role": "AXButton", "title": "Send"}],
    }
    lines = gui_actions._traverse(tree)
    assert lines == ["toolbar", '  button "Send"']  # nosec B101


def test_traverse_max_depth_cap():
    # 20 nested AXButtons; MAX_DEPTH=15 means only depths 0..15 (16 lines).
    leaf = {"role": "AXButton", "title": "L20"}
    tree = leaf
    for i in range(19, -1, -1):
        tree = {"role": "AXButton", "title": f"L{i}", "children": [tree]}
    lines = gui_actions._traverse(tree)
    # Lines emit at depth 0..15 → 16 elements
    assert len(lines) == 16  # nosec B101
    assert lines[0] == 'button "L0"'  # nosec B101
    assert lines[15] == ("  " * 15) + 'button "L15"'  # nosec B101


def test_traverse_max_elements_truncates_with_marker():
    # 300 sibling buttons; MAX_ELEMENTS=250 means 250 lines + 1 marker.
    children = [{"role": "AXButton", "title": f"B{i}"} for i in range(300)]
    tree = {"role": "AXGroup", "children": children}
    lines = gui_actions._traverse(tree)
    assert len(lines) == 251  # 250 + truncation marker  # nosec B101
    assert lines[0] == 'button "B0"'  # nosec B101
    assert lines[249] == 'button "B249"'  # nosec B101
    assert lines[250] == "[... truncated, 50 more elements skipped]"  # nosec B101


def test_traverse_max_elements_no_marker_when_under_budget():
    tree = {
        "role": "AXGroup",
        "children": [{"role": "AXButton", "title": f"B{i}"} for i in range(50)],
    }
    lines = gui_actions._traverse(tree)
    assert len(lines) == 50  # nosec B101
    assert not any("truncated" in line for line in lines)  # nosec B101


def test_is_accessibility_permitted_returns_true_when_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    assert gui_actions.is_accessibility_permitted() is True  # nosec B101


def test_is_accessibility_permitted_returns_false_when_not_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: False)
    assert gui_actions.is_accessibility_permitted() is False  # nosec B101
