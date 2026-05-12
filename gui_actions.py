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
import os
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("jarvis.gui")

MAX_ELEMENTS = 250
MAX_DEPTH = 15
APPLESCRIPT_TIMEOUT = 10


def _ancestor_app_name(start_pid: Optional[int] = None) -> str:
    """Best-effort detection of the macOS .app ancestor of this process.

    Walks up the parent chain (bounded to 10 hops) looking for an ancestor
    whose executable path contains '.app/'. Returns the bundle stem
    (e.g. "Warp", "Visual Studio Code") or "" if no .app ancestor is
    found or any subprocess call fails. The result is used to make the
    Accessibility-permission prompt name the specific terminal app that
    spawned JARVIS, rather than a generic phrase.
    """
    import subprocess

    try:
        pid = start_pid if start_pid is not None else os.getppid()
        for _ in range(10):
            if pid <= 1:
                return ""
            comm_r = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if comm_r.returncode != 0:
                return ""
            comm = comm_r.stdout.strip()
            if ".app/" in comm:
                bundle_path = comm.split(".app/", 1)[0] + ".app"
                return Path(bundle_path).stem
            ppid_r = subprocess.run(
                ["ps", "-p", str(pid), "-o", "ppid="],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if ppid_r.returncode != 0:
                return ""
            ppid_str = ppid_r.stdout.strip()
            if not ppid_str.lstrip("-").isdigit():
                return ""
            pid = int(ppid_str)
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _permission_prompt() -> str:
    """Compose the Accessibility-permission narrate string, including the
    detected parent app name when available."""
    app = _ancestor_app_name()
    target = app if app else "the terminal or app that runs JARVIS"
    return (
        "JARVIS needs Accessibility permission. Open System Settings > "
        f"Privacy & Security > Accessibility and enable {target}. "
        "Then fully quit and relaunch it so the permission applies."
    )


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


def _find_element(root: Any, role: str, label_substring: str) -> Optional[Any]:
    """Depth-first search for the first element matching role + label.

    Returns the live element handle (or dict in tests) or None. The role
    argument is the normalized snake_case form ("button", "link", …);
    label match is case-insensitive substring. First DFS hit wins.
    """
    target_role = role.lower() if role else ""
    target_label = label_substring.lower() if label_substring else ""

    def _matches(element: Any) -> bool:
        elem_role, _tier = _normalize_role(_get_role(element))
        if elem_role != target_role:
            return False
        elem_label = _label_for(element)
        if not elem_label:
            return False
        return target_label in elem_label.lower()

    stack: list[Any] = [root]
    while stack:
        element = stack.pop()
        if _matches(element):
            return element
        # Reverse so children pop in declared order (DFS, left-to-right).
        for child in reversed(_get_children(element)):
            stack.append(child)
    return None


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
        # Reserve a budget slot for self BEFORE recursing children so the
        # combined emit (parent + descendants) never exceeds MAX_ELEMENTS.
        # If no descendant emits, refund the reservation and elide self.
        budget[0] -= 1
        child_lines = _walk_children(children, depth + 1, budget)
        if child_lines:
            label = _label_for(element)
            enabled = _is_enabled(element)
            self_line = _format_element(role_name, label, None, enabled, depth)
            return [self_line] + child_lines
        budget[0] += 1
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
        return _permission_prompt()
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
        return _permission_prompt()
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


def _press_via_ax(element: Any) -> bool:
    """Send the AXPress action to an AX element. Returns True on success."""
    from ApplicationServices import AXUIElementPerformAction  # type: ignore

    try:
        err = AXUIElementPerformAction(element, "AXPress")
        return err == 0
    except Exception as e:  # noqa: BLE001
        log.warning("AXPress failed: %s", e)
        return False


def click_element(role: str, label: str) -> str:
    if not _ax_is_trusted():
        return _permission_prompt()
    try:
        info = _frontmost_app()
    except Exception as e:  # noqa: BLE001
        log.warning("frontmost app lookup failed: %s", e)
        return "Couldn't read UI from the frontmost app."
    if info is None:
        return "No frontmost app — try 'focus <app name>' first."
    target = _find_element(info["root"], role, label)
    if target is None:
        return f"Couldn't find {role} matching '{label}'."
    if _press_via_ax(target):
        return f"Clicked {role}: {label}."
    return f"Couldn't click {role}: {label}."


def _run_system_events(action: str) -> bool:
    """Run an AppleScript `tell application "System Events" to <action>`.

    Returns True on success. Used for keystroke/key-code synthesis where AX
    actions don't directly apply.
    """
    import subprocess

    script = f'tell application "System Events" to {action}'
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=APPLESCRIPT_TIMEOUT,
        )
        if r.returncode != 0:
            log.warning("System Events AppleScript failed: %s", r.stderr.strip())
            return False
        return True
    except subprocess.TimeoutExpired:
        log.warning("System Events AppleScript timed out")
        return False


def _escape_applescript_string(text: str) -> str:
    """Escape backslashes and double quotes for embedding inside an
    AppleScript string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


_MODIFIER_ALIASES: dict[str, str] = {
    "cmd": "command down",
    "command": "command down",
    "shift": "shift down",
    "alt": "option down",
    "opt": "option down",
    "option": "option down",
    "ctrl": "control down",
    "control": "control down",
    "fn": "function down",
}

_NAMED_KEY_CODES: dict[str, int] = {
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


def _parse_key_spec(
    spec: str,
) -> tuple[Optional[str], Optional[int], list[str]]:
    """Parse a key combo like 'cmd+t' or 'shift+cmd+return'.

    Returns (character, key_code, modifiers). Exactly one of character or
    key_code is non-None on success. modifiers is a list of AppleScript
    modifier phrases ('command down', 'shift down', …) in the order given.
    On parse failure all three are (None, None, []).
    """
    if not spec or not spec.strip():
        return None, None, []
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        return None, None, []
    *mod_parts, key_part = parts
    modifiers: list[str] = []
    for m in mod_parts:
        phrase = _MODIFIER_ALIASES.get(m)
        if phrase is None:
            return None, None, []
        modifiers.append(phrase)
    if key_part in _NAMED_KEY_CODES:
        return None, _NAMED_KEY_CODES[key_part], modifiers
    if len(key_part) == 1:
        return key_part, None, modifiers
    return None, None, []


def type_text(text: str) -> str:
    if not text:
        return "Missing text to type."
    if not _ax_is_trusted():
        return _permission_prompt()
    escaped = _escape_applescript_string(text)
    action = f'keystroke "{escaped}"'
    if _run_system_events(action):
        return f"Typed: {text}"
    return f"Couldn't type '{text}'."
