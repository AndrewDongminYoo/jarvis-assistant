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


def is_accessibility_permitted() -> bool:
    raise NotImplementedError


def focus_app(name: str) -> str:
    raise NotImplementedError


def observe_frontmost() -> str:
    raise NotImplementedError
