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
