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
    assert gui_actions._normalize_role("AXMenuBarItem") == (
        "menu_bar_item",
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


def test_traverse_tier_b_root_respects_max_elements_cap():
    """A tier-B root (e.g. AXWindow) with overflowing children must not
    push the emit count past MAX_ELEMENTS by adding the parent line after
    the budget is spent. Total emitted lines (excluding the marker) must
    equal MAX_ELEMENTS exactly.
    """
    children = [{"role": "AXButton", "title": f"B{i}"} for i in range(300)]
    tree = {"role": "AXWindow", "title": "BigWindow", "children": children}
    lines = gui_actions._traverse(tree)
    non_marker_lines = [line for line in lines if "truncated" not in line]
    assert len(non_marker_lines) == gui_actions.MAX_ELEMENTS  # nosec B101
    assert lines[0] == 'window "BigWindow"'  # nosec B101
    # 300 buttons exist; 249 fit alongside the window parent. 51 skipped.
    assert lines[-1] == "[... truncated, 51 more elements skipped]"  # nosec B101


def test_traverse_tier_b_refunds_budget_when_no_descendant_emits():
    """Tier-B that reserves a budget slot must refund it when its subtree
    emits nothing, so siblings can still consume the freed slot.
    """
    tree = {
        "role": "AXGroup",
        "children": [
            # First child: tier-B with no emitted descendants — should refund.
            {"role": "AXToolbar", "children": [{"role": "AXGroup", "children": []}]},
            # Second child: a labeled tier-A — should be able to emit.
            {"role": "AXButton", "title": "Send"},
        ],
    }
    lines = gui_actions._traverse(tree)
    assert lines == ['button "Send"'], lines  # nosec B101


def test_is_accessibility_permitted_returns_true_when_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    assert gui_actions.is_accessibility_permitted() is True  # nosec B101


def test_is_accessibility_permitted_returns_false_when_not_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: False)
    assert gui_actions.is_accessibility_permitted() is False  # nosec B101


def test_focus_app_returns_permission_message_when_not_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: False)
    result = gui_actions.focus_app("Chrome")
    assert "Accessibility" in result  # nosec B101


def test_focus_app_substring_match_against_running_apps(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(
        gui_actions,
        "_running_apps",
        lambda: [
            {"name": "Finder", "pid": 100},
            {"name": "Google Chrome", "pid": 200},
            {"name": "Slack", "pid": 300},
        ],
    )
    called = {}

    def fake_set_frontmost(pid):
        called["pid"] = pid
        return True

    monkeypatch.setattr(gui_actions, "_set_app_frontmost", fake_set_frontmost)
    result = gui_actions.focus_app("chrome")  # case-insensitive
    assert called["pid"] == 200  # nosec B101
    assert "Focused" in result and "Google Chrome" in result  # nosec B101


def test_focus_app_falls_back_to_applescript_when_no_running_match(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "_running_apps", lambda: [])
    monkeypatch.setattr(gui_actions, "_applescript_activate", lambda name: True)
    result = gui_actions.focus_app("Mail")
    assert "Focused" in result and "Mail" in result  # nosec B101


def test_focus_app_returns_not_found_when_both_paths_fail(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "_running_apps", lambda: [])
    monkeypatch.setattr(gui_actions, "_applescript_activate", lambda name: False)
    result = gui_actions.focus_app("Nonexistent")
    assert "Couldn't" in result or "couldn't" in result  # nosec B101
    assert "Nonexistent" in result  # nosec B101


def test_focus_app_empty_name_returns_error(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    result = gui_actions.focus_app("")
    assert "app name" in result.lower() or "missing" in result.lower()  # nosec B101


def test_observe_returns_permission_message_when_not_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: False)
    out = gui_actions.observe_frontmost()
    assert "Accessibility" in out  # nosec B101


def test_observe_returns_no_frontmost_message_when_none(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "_frontmost_app", lambda: None)
    out = gui_actions.observe_frontmost()
    assert "No frontmost app" in out  # nosec B101


def test_observe_returns_formatted_tree_for_fake_app(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    fake_root = {
        "role": "AXWindow",
        "title": "Inbox",
        "children": [
            {"role": "AXButton", "title": "New Message"},
            {"role": "AXButton", "title": "Reply", "enabled": False},
        ],
    }
    monkeypatch.setattr(
        gui_actions,
        "_frontmost_app",
        lambda: {"name": "Mail", "root": fake_root},
    )
    out = gui_actions.observe_frontmost()
    assert 'window "Inbox"' in out  # nosec B101
    assert '  button "New Message"' in out  # nosec B101
    assert '  button "Reply" [disabled]' in out  # nosec B101


def test_observe_returns_read_error_when_traversal_raises(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)

    def boom():
        raise RuntimeError("AX call failed")

    monkeypatch.setattr(gui_actions, "_frontmost_app", boom)
    out = gui_actions.observe_frontmost()
    assert "Couldn't read UI" in out  # nosec B101


def _fake_ps_runner(chain):
    """Build a fake subprocess.run that walks a PID → (comm, ppid) chain.

    `chain` is a dict mapping pid (int) → (comm, ppid).
    """
    import subprocess as _subprocess

    def fake_run(args, **kwargs):
        # args = ["ps", "-p", str(pid), "-o", "comm="|"ppid="]
        pid = int(args[2])
        field = args[4]
        node = chain.get(pid)
        if node is None:
            return _subprocess.CompletedProcess(
                args, returncode=1, stdout="", stderr=""
            )
        comm, ppid = node
        if field == "comm=":
            return _subprocess.CompletedProcess(
                args, returncode=0, stdout=f"{comm}\n", stderr=""
            )
        if field == "ppid=":
            return _subprocess.CompletedProcess(
                args, returncode=0, stdout=f"{ppid}\n", stderr=""
            )
        return _subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="")

    return fake_run


def test_ancestor_app_name_detects_warp_directly(monkeypatch):
    import subprocess

    chain = {1234: ("/Applications/Warp.app/Contents/MacOS/stable", 1)}
    monkeypatch.setattr(subprocess, "run", _fake_ps_runner(chain))
    assert gui_actions._ancestor_app_name(start_pid=1234) == "Warp"  # nosec B101


def test_ancestor_app_name_walks_up_through_shells(monkeypatch):
    """Typical chain: python → uv → bash → -zsh → Warp.app/.../stable"""
    import subprocess

    chain = {
        1000: ("uv", 1001),
        1001: ("bash", 1002),
        1002: ("-zsh", 1003),
        1003: ("/Applications/Warp.app/Contents/MacOS/stable", 1),
    }
    monkeypatch.setattr(subprocess, "run", _fake_ps_runner(chain))
    assert gui_actions._ancestor_app_name(start_pid=1000) == "Warp"  # nosec B101


def test_ancestor_app_name_handles_vscode_helper(monkeypatch):
    """VS Code integrated terminal runs under Code Helper inside the
    Visual Studio Code.app bundle. We want the bundle name, not the helper.
    """
    import subprocess

    chain = {
        2000: (
            "/Applications/Visual Studio Code.app/Contents/Frameworks/"
            "Code Helper.app/Contents/MacOS/Code Helper",
            1,
        ),
    }
    monkeypatch.setattr(subprocess, "run", _fake_ps_runner(chain))
    assert (  # nosec B101
        gui_actions._ancestor_app_name(start_pid=2000) == "Visual Studio Code"
    )


def test_ancestor_app_name_returns_empty_when_no_app_ancestor(monkeypatch):
    """Walk terminates at pid 1 without ever seeing a .app."""
    import subprocess

    chain = {
        500: ("python", 501),
        501: ("bash", 1),
    }
    monkeypatch.setattr(subprocess, "run", _fake_ps_runner(chain))
    assert gui_actions._ancestor_app_name(start_pid=500) == ""  # nosec B101


def test_ancestor_app_name_returns_empty_on_subprocess_failure(monkeypatch):
    import subprocess

    def boom(*args, **kwargs):
        raise OSError("ps not available")

    monkeypatch.setattr(subprocess, "run", boom)
    assert gui_actions._ancestor_app_name(start_pid=1234) == ""  # nosec B101


def test_permission_prompt_includes_detected_app_name(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ancestor_app_name", lambda: "Warp")
    msg = gui_actions._permission_prompt()
    assert "Warp" in msg  # nosec B101
    assert "Accessibility" in msg  # nosec B101
    assert "relaunch" in msg.lower()  # nosec B101


def test_permission_prompt_falls_back_when_app_unknown(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ancestor_app_name", lambda: "")
    msg = gui_actions._permission_prompt()
    assert "terminal" in msg.lower()  # nosec B101
    assert "Accessibility" in msg  # nosec B101


def test_find_element_returns_first_match_by_role_and_label():
    root = {
        "role": "AXWindow",
        "children": [
            {"role": "AXButton", "title": "Cancel"},
            {"role": "AXButton", "title": "Send"},
        ],
    }
    found = gui_actions._find_element(root, "button", "Send")
    assert found is not None  # nosec B101
    assert found["title"] == "Send"  # nosec B101


def test_find_element_case_insensitive_label_substring():
    root = {"role": "AXButton", "title": "New Message"}
    assert gui_actions._find_element(root, "button", "new") is not None  # nosec B101
    assert (
        gui_actions._find_element(root, "button", "MESSAGE") is not None
    )  # nosec B101


def test_find_element_returns_none_when_role_mismatches():
    root = {"role": "AXLink", "title": "Send"}
    assert gui_actions._find_element(root, "button", "Send") is None  # nosec B101


def test_find_element_returns_none_when_no_match():
    root = {
        "role": "AXWindow",
        "children": [{"role": "AXButton", "title": "Cancel"}],
    }
    assert gui_actions._find_element(root, "button", "Send") is None  # nosec B101


def test_find_element_descends_into_nested_subtrees():
    root = {
        "role": "AXWindow",
        "children": [
            {
                "role": "AXToolbar",
                "children": [
                    {
                        "role": "AXGroup",
                        "children": [{"role": "AXButton", "title": "Send"}],
                    }
                ],
            }
        ],
    }
    found = gui_actions._find_element(root, "button", "Send")
    assert found is not None and found["title"] == "Send"  # nosec B101


def test_find_element_dfs_returns_first_match_not_deepest():
    """First DFS match wins. A shallow button beats a deep button with
    the same label."""
    root = {
        "role": "AXWindow",
        "children": [
            {"role": "AXButton", "title": "Send", "id": "shallow"},
            {
                "role": "AXGroup",
                "children": [{"role": "AXButton", "title": "Send", "id": "deep"}],
            },
        ],
    }
    found = gui_actions._find_element(root, "button", "Send")
    assert found is not None and found["id"] == "shallow"  # nosec B101


def test_find_element_skips_label_less_elements():
    root = {
        "role": "AXWindow",
        "children": [
            {"role": "AXButton"},  # no label
            {"role": "AXButton", "title": "Send"},
        ],
    }
    found = gui_actions._find_element(root, "button", "Send")
    assert found is not None and found["title"] == "Send"  # nosec B101


def test_click_element_returns_permission_message_when_not_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: False)
    result = gui_actions.click_element("button", "Send")
    assert "Accessibility" in result  # nosec B101


def test_click_element_returns_no_frontmost_when_none(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "_frontmost_app", lambda: None)
    result = gui_actions.click_element("button", "Send")
    assert "No frontmost app" in result  # nosec B101


def test_click_element_returns_not_found_when_no_match(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    fake_root = {"role": "AXWindow", "children": []}
    monkeypatch.setattr(
        gui_actions,
        "_frontmost_app",
        lambda: {"name": "Mail", "root": fake_root},
    )
    result = gui_actions.click_element("button", "Nonexistent")
    assert "Couldn't find" in result and "Nonexistent" in result  # nosec B101


def test_click_element_presses_and_reports_success(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    fake_root = {
        "role": "AXWindow",
        "children": [{"role": "AXButton", "title": "Send"}],
    }
    monkeypatch.setattr(
        gui_actions,
        "_frontmost_app",
        lambda: {"name": "Mail", "root": fake_root},
    )
    pressed = {}

    def fake_press(element):
        pressed["title"] = element["title"]
        return True

    monkeypatch.setattr(gui_actions, "_press_via_ax", fake_press)
    result = gui_actions.click_element("button", "Send")
    assert pressed == {"title": "Send"}  # nosec B101
    assert "Clicked" in result and "Send" in result  # nosec B101


def test_click_element_reports_failure_when_press_returns_false(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    fake_root = {
        "role": "AXWindow",
        "children": [{"role": "AXButton", "title": "Send"}],
    }
    monkeypatch.setattr(
        gui_actions,
        "_frontmost_app",
        lambda: {"name": "Mail", "root": fake_root},
    )
    monkeypatch.setattr(gui_actions, "_press_via_ax", lambda _e: False)
    result = gui_actions.click_element("button", "Send")
    assert "Couldn't click" in result  # nosec B101


def test_type_text_returns_permission_message_when_not_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: False)
    result = gui_actions.type_text("hello")
    assert "Accessibility" in result  # nosec B101


def test_type_text_returns_missing_message_when_empty(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    result = gui_actions.type_text("")
    assert "Missing" in result or "missing" in result  # nosec B101


def test_type_text_invokes_system_events_keystroke(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    sent = {}

    def fake_run(action):
        sent["action"] = action
        return True

    monkeypatch.setattr(gui_actions, "_run_system_events", fake_run)
    result = gui_actions.type_text("hello world")
    assert sent["action"] == 'keystroke "hello world"'  # nosec B101
    assert "Typed" in result  # nosec B101


def test_type_text_escapes_quotes_and_backslashes(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    sent = {}

    def fake_run(action):
        sent["action"] = action
        return True

    monkeypatch.setattr(gui_actions, "_run_system_events", fake_run)
    gui_actions.type_text('a "quoted" \\ string')
    assert sent["action"] == 'keystroke "a \\"quoted\\" \\\\ string"'  # nosec B101


def test_type_text_reports_failure_when_run_returns_false(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "_run_system_events", lambda _a: False)
    result = gui_actions.type_text("hello")
    assert "Couldn't" in result  # nosec B101


def test_parse_key_spec_single_character():
    char, code, mods = gui_actions._parse_key_spec("t")
    assert char == "t"  # nosec B101
    assert code is None  # nosec B101
    assert mods == []  # nosec B101


def test_parse_key_spec_single_modifier_plus_char():
    char, code, mods = gui_actions._parse_key_spec("cmd+t")
    assert char == "t"  # nosec B101
    assert code is None  # nosec B101
    assert mods == ["command down"]  # nosec B101


def test_parse_key_spec_multiple_modifiers_in_order():
    char, code, mods = gui_actions._parse_key_spec("shift+cmd+a")
    assert char == "a"  # nosec B101
    assert mods == ["shift down", "command down"]  # nosec B101


def test_parse_key_spec_modifier_aliases():
    _c1, _k1, m1 = gui_actions._parse_key_spec("command+t")
    _c2, _k2, m2 = gui_actions._parse_key_spec("option+t")
    _c3, _k3, m3 = gui_actions._parse_key_spec("opt+t")
    _c4, _k4, m4 = gui_actions._parse_key_spec("control+t")
    assert m1 == ["command down"]  # nosec B101
    assert m2 == ["option down"]  # nosec B101
    assert m3 == ["option down"]  # nosec B101
    assert m4 == ["control down"]  # nosec B101


def test_parse_key_spec_named_keys():
    cases = {
        "return": 36,
        "enter": 36,
        "tab": 48,
        "space": 49,
        "esc": 53,
        "escape": 53,
        "delete": 51,
        "backspace": 51,
        "up": 126,
        "down": 125,
        "left": 123,
        "right": 124,
    }
    for spec, expected_code in cases.items():
        char, code, mods = gui_actions._parse_key_spec(spec)
        assert char is None, spec  # nosec B101
        assert code == expected_code, spec  # nosec B101
        assert mods == [], spec  # nosec B101


def test_parse_key_spec_named_key_with_modifier():
    char, code, mods = gui_actions._parse_key_spec("cmd+return")
    assert char is None  # nosec B101
    assert code == 36  # nosec B101
    assert mods == ["command down"]  # nosec B101


def test_parse_key_spec_case_insensitive():
    char, code, mods = gui_actions._parse_key_spec("CMD+T")
    assert char == "t"  # nosec B101
    assert mods == ["command down"]  # nosec B101


def test_parse_key_spec_unknown_modifier_returns_none():
    char, code, mods = gui_actions._parse_key_spec("hyper+t")
    assert char is None and code is None  # nosec B101
    assert mods == []  # nosec B101


def test_parse_key_spec_unknown_named_key_returns_none():
    char, code, mods = gui_actions._parse_key_spec("foobar")
    assert char is None and code is None  # nosec B101


def test_parse_key_spec_empty_string_returns_none():
    char, code, mods = gui_actions._parse_key_spec("")
    assert char is None and code is None  # nosec B101


def test_send_key_returns_permission_message_when_not_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: False)
    assert "Accessibility" in gui_actions.send_key("cmd+t")  # nosec B101


def test_send_key_rejects_unparseable_spec(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    result = gui_actions.send_key("hyper+t")
    assert "parse" in result.lower() or "couldn't" in result.lower()  # nosec B101


def test_send_key_character_with_modifiers(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    sent = {}

    def fake_run(action):
        sent["action"] = action
        return True

    monkeypatch.setattr(gui_actions, "_run_system_events", fake_run)
    result = gui_actions.send_key("shift+cmd+a")
    assert sent["action"] == (
        'keystroke "a" using {shift down, command down}'
    )  # nosec B101
    assert "Sent" in result and "shift+cmd+a" in result  # nosec B101


def test_send_key_character_without_modifiers(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    sent = {}

    def fake_run(action):
        sent["action"] = action
        return True

    monkeypatch.setattr(gui_actions, "_run_system_events", fake_run)
    gui_actions.send_key("a")
    assert sent["action"] == 'keystroke "a"'  # nosec B101


def test_send_key_named_key_uses_key_code(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    sent = {}

    def fake_run(action):
        sent["action"] = action
        return True

    monkeypatch.setattr(gui_actions, "_run_system_events", fake_run)
    gui_actions.send_key("cmd+return")
    assert sent["action"] == "key code 36 using {command down}"  # nosec B101


def test_send_key_reports_failure_when_run_returns_false(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "_run_system_events", lambda _a: False)
    result = gui_actions.send_key("cmd+t")
    assert "Couldn't" in result  # nosec B101


def test_scroll_returns_permission_message_when_not_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: False)
    assert "Accessibility" in gui_actions.scroll("down", 3)  # nosec B101


def test_scroll_rejects_unknown_direction(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    result = gui_actions.scroll("sideways", 3)
    assert "direction" in result.lower()  # nosec B101


def test_scroll_rejects_non_positive_amount(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    result = gui_actions.scroll("down", 0)
    assert "positive" in result.lower() or "amount" in result.lower()  # nosec B101


def test_scroll_calls_cgevent_with_correct_signs(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    calls = []

    def fake_scroll(direction, amount):
        calls.append((direction, amount))
        return True

    monkeypatch.setattr(gui_actions, "_scroll_via_cgevent", fake_scroll)
    gui_actions.scroll("down", 5)
    gui_actions.scroll("UP", 2)
    gui_actions.scroll("Left", 1)
    assert calls == [("down", 5), ("up", 2), ("left", 1)]  # nosec B101


def test_scroll_reports_failure_when_cgevent_returns_false(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "_scroll_via_cgevent", lambda _d, _a: False)
    result = gui_actions.scroll("down", 3)
    assert "Couldn't" in result  # nosec B101


def test_scroll_reports_success_with_direction_and_amount(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "_scroll_via_cgevent", lambda _d, _a: True)
    result = gui_actions.scroll("down", 3)
    assert "Scrolled" in result  # nosec B101
    assert "down" in result and "3" in result  # nosec B101
