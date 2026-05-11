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


def _normalize_role(ax_role: str) -> tuple[Optional[str], Optional[str]]:
    """Map an AX role to (snake_case_name, tier). Tier ∈ {"A", "B"} or None."""
    if ax_role in _TIER_A_ROLES:
        return _TIER_A_ROLES[ax_role], "A"
    if ax_role in _TIER_B_ROLES:
        return _TIER_B_ROLES[ax_role], "B"
    return None, None


def is_accessibility_permitted() -> bool:
    raise NotImplementedError


def focus_app(name: str) -> str:
    raise NotImplementedError


def observe_frontmost() -> str:
    raise NotImplementedError
