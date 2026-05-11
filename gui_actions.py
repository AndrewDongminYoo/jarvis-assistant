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


def _normalize_role(ax_role: str) -> tuple[Optional[str], Optional[str]]:
    """Map an AX role to (snake_case_name, tier). Tier ∈ {"A", "B"} or None."""
    if ax_role in _TIER_A_ROLES:
        return _TIER_A_ROLES[ax_role], "A"
    if ax_role in _TIER_B_ROLES:
        return _TIER_B_ROLES[ax_role], "B"
    return None, None


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


def _ax_is_trusted() -> bool:
    """Production-only: returns True iff this process has Accessibility
    permission. Tests monkeypatch this module-level function rather than
    pyobjc."""
    from ApplicationServices import AXIsProcessTrustedWithOptions  # type: ignore

    return bool(AXIsProcessTrustedWithOptions(None))


def is_accessibility_permitted() -> bool:
    return _ax_is_trusted()


def focus_app(name: str) -> str:
    raise NotImplementedError


def observe_frontmost() -> str:
    raise NotImplementedError
