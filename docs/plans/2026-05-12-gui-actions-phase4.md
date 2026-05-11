# GUI Actions Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land `gui_actions.py` with `UI:FOCUS` and `UI:OBSERVE` action handlers — the read-only Accessibility fast path for the JARVIS general agent.

**Architecture:** New `gui_actions.py` module exposes three functions (`focus_app`, `observe_frontmost`, `is_accessibility_permitted`). AX attribute access goes through small module-level helpers that production uses with pyobjc and tests monkeypatch with dict accessors. `_traverse` is a DFS over the AX tree with tier-A/tier-B/ignored role handling, a `MAX_ELEMENTS=250` budget, and a `MAX_DEPTH=15` cap. `server.py:dispatch_action` gets two new branches; the system prompt is updated to teach the new tags.

**Tech Stack:** Python 3.13, pyobjc (`ApplicationServices`, `Cocoa`), pytest with monkeypatch + dict fixtures, existing project conventions (`uv run pytest`, `# nosec B101`).

**Spec:** `docs/specs/2026-05-12-gui-actions-phase4-design.md`

**Out of scope (phase 5+):** `UI:CLICK`, `UI:TYPE`, `UI:KEY`, `UI:SCROLL`, `[ACTION:COMPUTER:goal]`, optional `step` WebSocket message, frontend changes.

---

## Task 1 — Add pyobjc deps and module skeleton

**Files:**

- Modify: `pyproject.toml`
- Create: `gui_actions.py`
- Create: `tests/test_gui_actions.py`

- [ ] **Step 1: Add pyobjc dependencies**

Open `pyproject.toml`. The dependency block uses PEP 621 `[project] dependencies = [...]`. Append two entries just before the closing bracket (the existing entries are not alphabetical, so insertion order doesn't matter — match the existing version-pin style):

```toml
  "pyobjc-framework-ApplicationServices>=11.0,<12.0",
  "pyobjc-framework-Cocoa>=11.0,<12.0",
```

Then run:

```bash
uv sync
```

Expected: dependencies install, `uv.lock` updates, no errors.

- [ ] **Step 2: Write failing import test**

Create `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 3: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `ModuleNotFoundError: No module named 'gui_actions'`.

- [ ] **Step 4: Create module skeleton**

Create `gui_actions.py`:

```python
"""macOS Accessibility-based GUI inspection for JARVIS.

Provides UI:OBSERVE (dump frontmost app's UI tree) and UI:FOCUS (activate
an app by name) action handlers. Read-only — write actions (CLICK, TYPE,
KEY, SCROLL) land in phase 5.

pyobjc imports happen lazily inside the production helpers so this module
is importable on systems without pyobjc (e.g. test fixtures that monkey-
patch the AX accessors).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("jarvis.gui")

MAX_ELEMENTS = 250
MAX_DEPTH = 15
APPLESCRIPT_TIMEOUT = 10


def is_accessibility_permitted() -> bool:
    raise NotImplementedError


def focus_app(name: str) -> str:
    raise NotImplementedError


def observe_frontmost() -> str:
    raise NotImplementedError
```

- [ ] **Step 5: Run tests and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): scaffold gui_actions module with pyobjc deps"
```

---

## Task 2 — `_normalize_role` and tier tables

**Files:**

- Modify: `gui_actions.py`
- Modify: `tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
def test_normalize_role_tier_a_examples():
    assert gui_actions._normalize_role("AXButton") == ("button", "A")  # nosec B101
    assert gui_actions._normalize_role("AXLink") == ("link", "A")  # nosec B101
    assert gui_actions._normalize_role("AXTextField") == ("text_field", "A")  # nosec B101
    assert gui_actions._normalize_role("AXTextArea") == ("text_area", "A")  # nosec B101
    assert gui_actions._normalize_role("AXCheckBox") == ("checkbox", "A")  # nosec B101
    assert gui_actions._normalize_role("AXRadioButton") == ("radio", "A")  # nosec B101
    assert gui_actions._normalize_role("AXMenuItem") == ("menu_item", "A")  # nosec B101
    assert gui_actions._normalize_role("AXMenuButton") == ("menu_button", "A")  # nosec B101
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: module 'gui_actions' has no attribute '_normalize_role'`.

- [ ] **Step 3: Implement `_normalize_role`**

Add to `gui_actions.py` (just above `is_accessibility_permitted`):

```python
_TIER_A_ROLES: dict[str, str] = {
    "AXButton": "button",
    "AXLink": "link",
    "AXTextField": "text_field",
    "AXTextArea": "text_area",
    "AXCheckBox": "checkbox",
    "AXRadioButton": "radio",
    "AXMenuItem": "menu_item",
    "AXMenuButton": "menu_button",
    "AXTab": "tab",
    "AXStaticText": "text",
    "AXRow": "row",
    "AXCell": "cell",
    "AXPopUpButton": "popup",
    "AXComboBox": "combo",
    "AXImage": "image",
}

_TIER_B_ROLES: dict[str, str] = {
    "AXWindow": "window",
    "AXToolbar": "toolbar",
    "AXMenuBar": "menu_bar",
    "AXMenu": "menu",
    "AXTabGroup": "tab_group",
}


def _normalize_role(ax_role: str) -> tuple[Optional[str], Optional[str]]:
    """Map an AX role to (snake_case_name, tier). Tier ∈ {"A", "B"} or None."""
    if ax_role in _TIER_A_ROLES:
        return _TIER_A_ROLES[ax_role], "A"
    if ax_role in _TIER_B_ROLES:
        return _TIER_B_ROLES[ax_role], "B"
    return None, None
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add _normalize_role with tier-A/tier-B tables"
```

---

## Task 3 — AX attribute accessors and `_label_for`

The four accessors (`_get_role`, `_get_attribute`, `_get_children`, `_is_enabled`) are the seam between production (pyobjc) and tests (dict fixtures). Tests pass dicts; production wraps live AX handles. `_label_for` is the priority-ordered label extractor that the rest of the module depends on.

**Files:**

- Modify: `gui_actions.py`
- Modify: `tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... '_get_role'` (or similar) on every new test.

- [ ] **Step 3: Implement accessors and `_label_for`**

Add to `gui_actions.py` (above `_normalize_role`):

```python
# Element accessors — production wraps live pyobjc AX handles; tests pass
# dicts. The isinstance check is the only fork between the two paths.

def _ax_attribute(element: Any, attr: str) -> Any:
    """Production AX attribute getter. Lazy pyobjc import."""
    from ApplicationServices import AXUIElementCopyAttributeValue

    err, value = AXUIElementCopyAttributeValue(element, attr, None)
    if err != 0:
        return None
    return value


def _get_role(element: Any) -> str:
    if isinstance(element, dict):
        return element.get("role", "")
    return _ax_attribute(element, "AXRole") or ""


def _get_attribute(element: Any, attr: str) -> Optional[str]:
    if isinstance(element, dict):
        # Map AXTitle -> "title", AXValue -> "value", etc.
        key = attr.removeprefix("AX").lower()
        v = element.get(key)
        return v if isinstance(v, str) or v is None else str(v)
    v = _ax_attribute(element, attr)
    return v if isinstance(v, str) else None


def _get_children(element: Any) -> list:
    if isinstance(element, dict):
        return element.get("children", [])
    return _ax_attribute(element, "AXChildren") or []


def _is_enabled(element: Any) -> bool:
    if isinstance(element, dict):
        return element.get("enabled", True)
    v = _ax_attribute(element, "AXEnabled")
    return bool(v) if v is not None else True


def _label_for(element: Any) -> Optional[str]:
    for attr in ("AXTitle", "AXValue", "AXDescription", "AXHelp"):
        v = _get_attribute(element, attr)
        if v and v.strip():
            return v.strip()
    return None
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add AX accessors and label extraction"
```

---

## Task 4 — `_format_element`

**Files:**

- Modify: `gui_actions.py`
- Modify: `tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... '_format_element'`.

- [ ] **Step 3: Implement `_format_element`**

Add to `gui_actions.py` (after `_label_for`):

```python
def _format_element(
    role: str,
    label: Optional[str],
    value: Optional[str],
    enabled: bool,
    depth: int,
) -> str:
    indent = "  " * depth
    parts = [role]
    if label is not None:
        parts.append(f'"{label}"')
    if value is not None and value != label:
        parts.append(f'"{value}"')
    line = indent + " ".join(parts)
    if not enabled:
        line += " [disabled]"
    return line
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add _format_element with disabled flag and value handling"
```

---

## Task 5 — `_traverse` core (tier-A only, no limits)

This task lands the recursion shape and tier-A behavior. Tier-B (deferred-emit) and the `MAX_ELEMENTS` / `MAX_DEPTH` limits come in Task 6.

**Files:**

- Modify: `gui_actions.py`
- Modify: `tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... '_traverse'`.

- [ ] **Step 3: Implement `_traverse` core**

Add to `gui_actions.py` (after `_format_element`):

```python
def _traverse(element: Any, depth: int = 0) -> list[str]:
    """Walk an AX subtree and emit pruned, indented lines.

    Tier-A roles (Button, Link, TextField, etc.) emit a line when they have
    a label; their children recurse at depth+1. Tier-B roles (Window,
    Toolbar, etc.) are added in a later task — for now they behave like
    ignored roles. Ignored roles (Group, ScrollArea, etc.) and tier-A
    without a label both pass through to children at the same depth.
    """
    role_name, tier = _normalize_role(_get_role(element))
    children = _get_children(element)

    if tier == "A":
        label = _label_for(element)
        if label is None:
            # No label — drop self, recurse children at same depth.
            return _walk_children(children, depth)
        # AXValue is already the label when title was empty; only include
        # value as a separate field for text inputs whose title and value
        # are distinct (e.g. a "Search" field with current text).
        value = None
        if role_name in ("text_field", "text_area"):
            raw_value = _get_attribute(element, "AXValue")
            if raw_value and raw_value.strip() and raw_value.strip() != label:
                value = raw_value.strip()
        enabled = _is_enabled(element)
        line = _format_element(role_name, label, value, enabled, depth)
        return [line] + _walk_children(children, depth + 1)

    # Tier B + ignored: behave like ignored (pass-through). Tier B's
    # deferred-emit semantics land in Task 6.
    return _walk_children(children, depth)


def _walk_children(children: list, depth: int) -> list[str]:
    out: list[str] = []
    for child in children:
        out.extend(_traverse(child, depth))
    return out
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add _traverse core with tier-A and ignored roles"
```

---

## Task 6 — Tier-B deferred emit, `MAX_ELEMENTS` truncation, `MAX_DEPTH` cap

**Files:**

- Modify: `gui_actions.py`
- Modify: `tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
    children = [
        {"role": "AXButton", "title": f"B{i}"} for i in range(300)
    ]
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: tier-B tests fail (current code passes them through). MAX_DEPTH and MAX_ELEMENTS tests also fail.

- [ ] **Step 3: Replace `_traverse` and `_walk_children` with the budgeted version**

Replace the bodies of `_traverse` and `_walk_children` in `gui_actions.py` with:

```python
def _traverse(element: Any, depth: int = 0) -> list[str]:
    """Walk an AX subtree and emit pruned, indented lines.

    Termination: any of (a) depth > MAX_DEPTH, (b) emitted-line budget
    exhausted, (c) walk completes. When the budget runs out, the count of
    additional qualifying elements is appended as a truncation marker.
    """
    budget = [MAX_ELEMENTS]
    lines = _traverse_inner(element, depth, budget)
    if budget[0] <= 0:
        skipped = _count_remaining(element, depth, MAX_ELEMENTS)
        if skipped > 0:
            lines.append(f"[... truncated, {skipped} more elements skipped]")
    return lines


def _traverse_inner(element: Any, depth: int, budget: list[int]) -> list[str]:
    if depth > MAX_DEPTH or budget[0] <= 0:
        return []

    role_name, tier = _normalize_role(_get_role(element))
    children = _get_children(element)

    if tier == "A":
        label = _label_for(element)
        if label is None:
            return _walk_children(children, depth, budget)
        value = None
        if role_name in ("text_field", "text_area"):
            raw_value = _get_attribute(element, "AXValue")
            if raw_value and raw_value.strip() and raw_value.strip() != label:
                value = raw_value.strip()
        enabled = _is_enabled(element)
        line = _format_element(role_name, label, value, enabled, depth)
        budget[0] -= 1
        return [line] + _walk_children(children, depth + 1, budget)

    if tier == "B":
        # Recurse children first; only emit self if any child emitted.
        child_lines = _walk_children(children, depth + 1, budget)
        if child_lines:
            label = _label_for(element)
            enabled = _is_enabled(element)
            self_line = _format_element(role_name, label, None, enabled, depth)
            budget[0] -= 1
            return [self_line] + child_lines
        return []

    # Ignored role — pass through children at same depth.
    return _walk_children(children, depth, budget)


def _walk_children(children: list, depth: int, budget: list[int]) -> list[str]:
    out: list[str] = []
    for child in children:
        if budget[0] <= 0:
            break
        out.extend(_traverse_inner(child, depth, budget))
    return out


def _count_remaining(element: Any, depth: int, emitted_so_far: int) -> int:
    """Count emittable elements in the full tree, return excess past budget.

    Second pass: how many lines would have emitted if MAX_ELEMENTS were
    unlimited. The number returned is the excess only (full count minus the
    budget already spent).
    """
    total = _count_inner(element, depth)
    return max(total - emitted_so_far, 0)


def _count_inner(element: Any, depth: int) -> int:
    """Mirror of _traverse_inner's tier handling, but counting only."""
    if depth > MAX_DEPTH:
        return 0
    _role_name, tier = _normalize_role(_get_role(element))
    children = _get_children(element)
    if tier == "A":
        label = _label_for(element)
        if label is None:
            return sum(_count_inner(c, depth) for c in children)
        return 1 + sum(_count_inner(c, depth + 1) for c in children)
    if tier == "B":
        child_count = sum(_count_inner(c, depth + 1) for c in children)
        return (1 + child_count) if child_count > 0 else 0
    return sum(_count_inner(c, depth) for c in children)
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: all tests PASS, including the new tier-B and limit tests.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add tier-B deferred emit + MAX_ELEMENTS/MAX_DEPTH limits"
```

---

## Task 7 — `is_accessibility_permitted`

**Files:**

- Modify: `gui_actions.py`
- Modify: `tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
def test_is_accessibility_permitted_returns_true_when_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    assert gui_actions.is_accessibility_permitted() is True  # nosec B101


def test_is_accessibility_permitted_returns_false_when_not_trusted(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: False)
    assert gui_actions.is_accessibility_permitted() is False  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... '_ax_is_trusted'` or `NotImplementedError`.

- [ ] **Step 3: Implement permission check**

In `gui_actions.py`, replace the `is_accessibility_permitted` skeleton with:

```python
def _ax_is_trusted() -> bool:
    """Production-only: returns True iff this process has Accessibility
    permission. Tests monkeypatch this module-level function rather than
    pyobjc."""
    from ApplicationServices import AXIsProcessTrustedWithOptions  # type: ignore

    return bool(AXIsProcessTrustedWithOptions(None))


def is_accessibility_permitted() -> bool:
    return _ax_is_trusted()
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: both new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add is_accessibility_permitted with pyobjc check"
```

---

## Task 8 — `focus_app`

**Files:**

- Modify: `gui_actions.py`
- Modify: `tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
    monkeypatch.setattr(
        gui_actions, "_applescript_activate", lambda name: True
    )
    result = gui_actions.focus_app("Mail")
    assert "Focused" in result and "Mail" in result  # nosec B101


def test_focus_app_returns_not_found_when_both_paths_fail(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "_running_apps", lambda: [])
    monkeypatch.setattr(
        gui_actions, "_applescript_activate", lambda name: False
    )
    result = gui_actions.focus_app("Nonexistent")
    assert "Couldn't" in result or "couldn't" in result  # nosec B101
    assert "Nonexistent" in result  # nosec B101


def test_focus_app_empty_name_returns_error(monkeypatch):
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    result = gui_actions.focus_app("")
    assert "app name" in result.lower() or "missing" in result.lower()  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `NotImplementedError` from `focus_app`.

- [ ] **Step 3: Implement `focus_app` and helpers**

In `gui_actions.py`, replace the `focus_app` skeleton with:

```python
PERMISSION_PROMPT = (
    "JARVIS needs Accessibility permission. Open System Settings > "
    "Privacy & Security > Accessibility and enable the terminal or app "
    "that runs JARVIS."
)


def _running_apps() -> list[dict]:
    """Return [{name, pid}, ...] for every running app. Lazy pyobjc."""
    from Cocoa import NSWorkspace  # type: ignore

    workspace = NSWorkspace.sharedWorkspace()
    out: list[dict] = []
    for app in workspace.runningApplications():
        name = app.localizedName()
        pid = app.processIdentifier()
        if name:
            out.append({"name": str(name), "pid": int(pid)})
    return out


def _set_app_frontmost(pid: int) -> bool:
    """Bring the app with this PID to the front via AX. Returns success."""
    try:
        from ApplicationServices import (  # type: ignore
            AXUIElementCreateApplication,
            AXUIElementSetAttributeValue,
        )

        app_element = AXUIElementCreateApplication(pid)
        err = AXUIElementSetAttributeValue(app_element, "AXFrontmost", True)
        return err == 0
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to set frontmost via AX: %s", e)
        return False


def _applescript_activate(name: str) -> bool:
    """Fallback: `tell app "<name>" to activate`. Returns success."""
    import subprocess

    escaped = name.replace('"', '\\"')
    script = f'tell application "{escaped}" to activate'
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=APPLESCRIPT_TIMEOUT,
        )
        if r.returncode != 0:
            log.warning("AppleScript activate failed: %s", r.stderr.strip())
            return False
        return True
    except subprocess.TimeoutExpired:
        log.warning("AppleScript activate timed out for %s", name)
        return False


def focus_app(name: str) -> str:
    if not name or not name.strip():
        return "Missing app name."
    if not _ax_is_trusted():
        return PERMISSION_PROMPT
    target = name.strip()
    lower = target.lower()
    for app in _running_apps():
        if lower in app["name"].lower():
            if _set_app_frontmost(app["pid"]):
                return f"Focused {app['name']}."
            # AX failed even though we found the app — try AppleScript anyway.
            break
    if _applescript_activate(target):
        return f"Focused {target}."
    return f"Couldn't find an app matching '{target}'."
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: all new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add focus_app with NSWorkspace match and AppleScript fallback"
```

---

## Task 9 — `observe_frontmost`

**Files:**

- Modify: `gui_actions.py`
- Modify: `tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `NotImplementedError` from `observe_frontmost`.

- [ ] **Step 3: Implement `observe_frontmost`**

In `gui_actions.py`, replace the `observe_frontmost` skeleton with:

```python
def _frontmost_app() -> Optional[dict]:
    """Return {"name": <localized name>, "root": <AX root element>} or None.

    The "root" is the AX element returned by AXUIElementCreateApplication
    for the frontmost process; _traverse can walk it via _get_children.
    Lazy pyobjc.
    """
    from ApplicationServices import AXUIElementCreateApplication  # type: ignore
    from Cocoa import NSWorkspace  # type: ignore

    workspace = NSWorkspace.sharedWorkspace()
    app = workspace.frontmostApplication()
    if app is None:
        return None
    name = app.localizedName()
    pid = app.processIdentifier()
    if not name or not pid:
        return None
    return {"name": str(name), "root": AXUIElementCreateApplication(int(pid))}


def observe_frontmost() -> str:
    if not _ax_is_trusted():
        return PERMISSION_PROMPT
    try:
        info = _frontmost_app()
    except Exception as e:  # noqa: BLE001
        log.warning("frontmost app lookup failed: %s", e)
        return "Couldn't read UI from the frontmost app."
    if info is None:
        return "No frontmost app — try 'focus <app name>' first."
    try:
        lines = _traverse(info["root"])
    except Exception as e:  # noqa: BLE001
        log.warning("AX traversal failed for %s: %s", info["name"], e)
        return f"Couldn't read UI from {info['name']}."
    if not lines:
        return f"{info['name']} has no inspectable UI right now."
    return "\n".join(lines)
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: all new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add observe_frontmost public entrypoint"
```

---

## Task 10 — Wire `UI:FOCUS` / `UI:OBSERVE` into `server.py` and update system prompt

**Files:**

- Modify: `server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_server.py`:

```python
def test_dispatch_action_routes_ui_focus(monkeypatch):
    import gui_actions

    called = {}

    def fake_focus(name):
        called["name"] = name
        return "Focused Chrome."

    monkeypatch.setattr(gui_actions, "focus_app", fake_focus)
    result = run(server.dispatch_action("UI:FOCUS:Chrome"))
    assert called["name"] == "Chrome"  # nosec B101
    assert result == "Focused Chrome."  # nosec B101


def test_dispatch_action_routes_ui_observe(monkeypatch):
    import gui_actions

    monkeypatch.setattr(
        gui_actions,
        "observe_frontmost",
        lambda: 'window "Inbox"\n  button "Send"',
    )
    result = run(server.dispatch_action("UI:OBSERVE"))
    assert "Inbox" in result and "Send" in result  # nosec B101


def test_dispatch_action_unknown_ui_subkind_returns_message():
    result = run(server.dispatch_action("UI:WHATEVER"))
    assert "Unknown UI action" in result  # nosec B101


def test_system_prompt_mentions_ui_focus_and_ui_observe():
    prompt = server._build_system_prompt()
    assert "UI:FOCUS" in prompt  # nosec B101
    assert "UI:OBSERVE" in prompt  # nosec B101
```

If `tests/test_server.py` does not already define `run = asyncio.run`, add this at the top of the file under existing imports (it's already in the file from earlier work — confirm before adding).

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_server.py -v
```

Expected: 4 new tests FAIL — `dispatch_action` returns `"Unknown action: UI"` and the system prompt does not mention the new tags.

- [ ] **Step 3: Add `UI` branch in `dispatch_action`**

In `server.py`'s `dispatch_action`, add a new branch alongside the others (anywhere before the final `return f"Unknown action: {kind}"`):

```python
    if kind == "UI":
        sub = parts[1].upper() if len(parts) > 1 else ""
        if sub == "FOCUS":
            from gui_actions import focus_app

            target = parts[2] if len(parts) > 2 else ""
            return await asyncio.to_thread(focus_app, target)
        if sub == "OBSERVE":
            from gui_actions import observe_frontmost

            return await asyncio.to_thread(observe_frontmost)
        return f"Unknown UI action: {sub}"
```

- [ ] **Step 4: Update system prompt**

In `server.py`'s `_build_system_prompt`, the action tag list currently includes lines like `[ACTION:CALENDAR] — upcoming calendar events`. Add two new lines just before `[ACTION:REMEMBER:fact]`:

```log
  [ACTION:UI:FOCUS:app_name]             — activate an app (Chrome, Slack, Mail…)
  [ACTION:UI:OBSERVE]                    — read the frontmost app's UI
```

And, just below the action tag block (before the `{facts_block}` placeholder), add the usage guideline as a separate paragraph:

```log
Prefer UI:OBSERVE before acting on UI. The click target's role/label come from the OBSERVE output's vocabulary.
```

- [ ] **Step 5: Run all tests**

```bash
uv run pytest -v
```

Expected: every test PASSes.

- [ ] **Step 6: Compile-check**

```bash
uv run python -m compileall server.py gui_actions.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat(server): route UI:FOCUS and UI:OBSERVE actions"
```

---

## Task 11 — Optional live integration test (skipped by default)

This task adds a single live test that exercises the AX pipeline end-to-end against Finder, gated behind a `macos` marker so CI doesn't run it.

**Files:**

- Modify: `pyproject.toml` (register the `macos` marker)
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_gui_actions_live.py`

- [ ] **Step 1: Register the `macos` marker**

In `pyproject.toml`, find the `[tool.pytest.ini_options]` block. If a `markers = [...]` list exists, append:

```toml
    "macos: live macOS-only integration tests requiring Accessibility permission",
```

If no such list exists, add it:

```toml
[tool.pytest.ini_options]
markers = [
    "macos: live macOS-only integration tests requiring Accessibility permission",
]
```

Preserve any other existing keys in the block.

- [ ] **Step 2: Create integration test directory marker**

Create `tests/integration/__init__.py` (empty file).

- [ ] **Step 3: Create the live test**

Create `tests/integration/test_gui_actions_live.py`:

```python
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
    assert gui_actions.is_accessibility_permitted() is True, (  # nosec B101
        "Grant Accessibility permission to the test runner before running -m macos"
    )


def test_focus_finder_then_observe_returns_a_menu_bar():
    result = gui_actions.focus_app("Finder")
    assert "Focused" in result  # nosec B101
    out = gui_actions.observe_frontmost()
    # Finder always has a menu_bar; this is the minimal end-to-end signal.
    assert "menu_bar" in out, out  # nosec B101
```

- [ ] **Step 4: Confirm the test is skipped by default**

```bash
uv run pytest -v
```

Expected: the live test is collected but reported as deselected (no `macos` marker active), all other tests PASS.

- [ ] **Step 5: Optional — run the live test manually**

This step is for the human user, not the implementing agent. After ensuring Accessibility permission is granted to whichever process runs pytest:

```bash
uv run pytest -m macos -v
```

Expected: both live tests PASS, or the permission test fails with the granting instructions.

The implementing agent should NOT attempt to run this — it requires interactive system permission grants.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/integration/__init__.py tests/integration/test_gui_actions_live.py
git commit -m "test(gui): add live macOS integration test behind macos marker"
```

---

## Verification Summary

After this plan lands, the branch state is:

- `gui_actions.py` provides `focus_app`, `observe_frontmost`, `is_accessibility_permitted`.
- `server.py:dispatch_action` routes `UI:FOCUS:<name>` and `UI:OBSERVE`.
- System prompt teaches the LLM the two new tags + the OBSERVE-first guideline.
- All AX accessors are unit-tested with dict fixtures; pyobjc is required only for live execution.
- One live integration test is wired behind `pytest -m macos`, skipped by default.

Minimum verification: `uv run pytest -v` (must be green). Manual: ask JARVIS "Chrome 활성화해줘" then "보이는 UI 읽어줘" — Chrome should focus and the OBSERVE output should appear in the LLM's narrated reply.

## Follow-ups (separate plans)

1. Phase 5 — `UI:CLICK`, `UI:TYPE`, `UI:KEY`, `UI:SCROLL` (write actions) — match against the OBSERVE vocabulary.
2. Phase 6 — `[ACTION:COMPUTER:goal]` with Anthropic Computer Use.
3. OBSERVE-result caching for one turn (decide based on phase 5 latency data).
4. 5-second traversal hard timeout (the spec mentions this as defense-in-depth; `MAX_ELEMENTS`/`MAX_DEPTH` make it unnecessary in practice, but a true wall-clock guard would protect against pathological pyobjc latency).
