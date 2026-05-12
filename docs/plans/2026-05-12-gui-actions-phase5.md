# GUI Actions Phase 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the write actions of the Accessibility fast path — `UI:CLICK`, `UI:TYPE`, `UI:KEY`, `UI:SCROLL` — so JARVIS can drive known macOS apps end-to-end (e.g. "send a Slack DM to Anna").

**Architecture:** Extend `gui_actions.py` with four public write functions on top of phase 4's read primitives. `click_element` walks the AX tree to find the target then dispatches `AXUIElementPerformAction(element, "AXPress")`. `type_text` and `send_key` go through AppleScript `System Events` (the same channel macOS apps already accept from `actions.py`) — fewer permission domains than splitting between AX and CGEvent. `scroll` uses Quartz `CGEventCreateScrollWheelEvent`. `server.py:dispatch_action` extends its existing `UI:*` branch; the system prompt teaches the four new tags. `safety.classify` already handles all four (CLICK by label, TYPE/KEY → CONFIRM, SCROLL → SAFE) — no safety changes.

**Tech Stack:** Python 3.13, pyobjc (`ApplicationServices`, `Quartz`), `osascript` for AppleScript, pytest with dict fixtures and monkeypatched subprocess.

**Spec:** `docs/specs/2026-05-11-general-agent-design.md` (action tags + safety table) and `docs/specs/2026-05-12-gui-actions-phase4-design.md` (module shape + dict/pyobjc fork pattern that this plan extends).

**Out of scope:**

- `[ACTION:COMPUTER:goal]` and `computer_use.py` (phase 6 — vision-grounded fallback for apps that don't cleanly expose AX).
- Optional `step` WebSocket progress message + frontend indicator (phase 7).
- `MAIL:SEND` actual dispatcher implementation.
- Anything beyond a single AXPress per CLICK (no mouse-click fallback at element coordinates — defer to phase 6).

---

## Task 1 — `_find_element` AX tree search helper

The matching function for `UI:CLICK:role::label`. Walks the AX tree depth-first and returns the first element whose normalized role matches and whose label contains the substring (case-insensitive). Pure-function tested with dict fixtures.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/gui_actions.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
    assert gui_actions._find_element(root, "button", "MESSAGE") is not None  # nosec B101


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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... '_find_element'`.

- [ ] **Step 3: Implement `_find_element`**

Add to `gui_actions.py` immediately above the `_traverse` definition (so phase 5 helpers cluster with phase 4's traversal machinery):

```python
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
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: all 7 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add _find_element AX tree search helper"
```

---

## Task 2 — `click_element` via `AXPress`

Public click function. Permission check → frontmost lookup → element find → AX press. Returns human-readable status string. No mouse-coordinate fallback in this phase — apps that don't expose `AXPress` fall through to phase 6 (computer use).

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/gui_actions.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... 'click_element'`.

- [ ] **Step 3: Implement `_press_via_ax` and `click_element`**

Append to `gui_actions.py` (after `observe_frontmost`):

```python
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
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: 5 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add click_element via AXPress"
```

---

## Task 3 — `type_text` and `_run_system_events` helper

AppleScript `System Events` is the simplest reliable channel for keystroke synthesis on modern macOS. The same channel powers the existing `actions.py` AppleScript helpers, so the user has already granted Automation permission (or will get one TCC prompt the first time JARVIS uses it).

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/gui_actions.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... 'type_text'`.

- [ ] **Step 3: Implement `_run_system_events` and `type_text`**

Append to `gui_actions.py` (after `click_element`):

```python
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
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: 5 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add type_text via System Events keystroke"
```

---

## Task 4 — `_parse_key_spec` parser

Parses strings like `cmd+t`, `shift+cmd+a`, `return`, `esc`. The output drives `send_key` in Task 5. Pure function, table-driven.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/gui_actions.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... '_parse_key_spec'`.

- [ ] **Step 3: Implement parser and tables**

Append to `gui_actions.py` (after `_escape_applescript_string`):

```python
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
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: 10 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add _parse_key_spec for cmd+t style combos"
```

---

## Task 5 — `send_key` public function

Builds the System Events action string from `_parse_key_spec` output and dispatches via `_run_system_events`.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/gui_actions.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... 'send_key'`.

- [ ] **Step 3: Implement `send_key`**

Append to `gui_actions.py` (after `_parse_key_spec`):

```python
def send_key(spec: str) -> str:
    if not _ax_is_trusted():
        return _permission_prompt()
    character, key_code, modifiers = _parse_key_spec(spec)
    if character is None and key_code is None:
        return f"Couldn't parse key spec '{spec}'."
    mod_clause = (
        " using {" + ", ".join(modifiers) + "}" if modifiers else ""
    )
    if character is not None:
        action = f'keystroke "{character}"' + mod_clause
    else:
        action = f"key code {key_code}" + mod_clause
    if _run_system_events(action):
        return f"Sent {spec}."
    return f"Couldn't send {spec}."
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: 6 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add send_key via System Events"
```

---

## Task 6 — `scroll` via CGEvent

Quartz `CGEventCreateScrollWheelEvent` is the canonical programmatic scroll on macOS. AppleScript-via-System-Events scrolling is unreliable across apps; CGEvent works at the window-server level.

**Direction convention** (matches user mental model): `down` = "show me content below" = wheel delta_y < 0; `up` = wheel delta_y > 0. Horizontal symmetric. macOS "natural scrolling" setting affects how the wheel direction maps to visible movement; this layer just posts the wheel event.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/gui_actions.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_gui_actions.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_gui_actions.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: `AttributeError: ... 'scroll'`.

- [ ] **Step 3: Implement `_scroll_via_cgevent` and `scroll`**

Append to `gui_actions.py` (after `send_key`):

```python
def _scroll_via_cgevent(direction: str, amount: int) -> bool:
    """Post a programmatic scroll wheel event. Returns True on success."""
    try:
        from Quartz import (  # type: ignore
            CGEventCreateScrollWheelEvent,
            CGEventPost,
            kCGHIDEventTap,
            kCGScrollEventUnitLine,
        )

        delta_y = 0
        delta_x = 0
        if direction == "up":
            delta_y = amount
        elif direction == "down":
            delta_y = -amount
        elif direction == "left":
            delta_x = amount
        elif direction == "right":
            delta_x = -amount
        else:
            return False
        if delta_x != 0:
            event = CGEventCreateScrollWheelEvent(
                None, kCGScrollEventUnitLine, 2, delta_y, delta_x
            )
        else:
            event = CGEventCreateScrollWheelEvent(
                None, kCGScrollEventUnitLine, 1, delta_y
            )
        if event is None:
            return False
        CGEventPost(kCGHIDEventTap, event)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("CGEvent scroll failed: %s", e)
        return False


def scroll(direction: str, amount: int) -> str:
    if not _ax_is_trusted():
        return _permission_prompt()
    direction_normalized = direction.lower().strip()
    if direction_normalized not in ("up", "down", "left", "right"):
        return f"Unknown scroll direction '{direction}'."
    if amount <= 0:
        return "Scroll amount must be a positive integer."
    if _scroll_via_cgevent(direction_normalized, amount):
        return f"Scrolled {direction_normalized} {amount} line(s)."
    return f"Couldn't scroll {direction_normalized}."
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_gui_actions.py -v
```

Expected: 6 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_actions.py tests/test_gui_actions.py
git commit -m "feat(gui): add scroll via Quartz CGEvent wheel"
```

---

## Task 7 — Wire `UI:CLICK` / `UI:TYPE` / `UI:KEY` / `UI:SCROLL` into `server.py`

The existing `UI:` branch in `dispatch_action` gets four new sub-kinds. The system prompt's action-tag list gains four lines.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/server.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_server.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_server.py`:

```python
def test_dispatch_action_routes_ui_click(monkeypatch):
    import gui_actions

    called = {}

    def fake_click(role, label):
        called["args"] = (role, label)
        return "Clicked button: Send."

    monkeypatch.setattr(gui_actions, "click_element", fake_click)
    result = run(server.dispatch_action("UI:CLICK:button::Send"))
    assert called["args"] == ("button", "Send")  # nosec B101
    assert "Clicked" in result  # nosec B101


def test_dispatch_action_routes_ui_type(monkeypatch):
    import gui_actions

    called = {}

    def fake_type(text):
        called["text"] = text
        return f"Typed: {text}"

    monkeypatch.setattr(gui_actions, "type_text", fake_type)
    result = run(server.dispatch_action("UI:TYPE:hello world"))
    assert called["text"] == "hello world"  # nosec B101
    assert "hello world" in result  # nosec B101


def test_dispatch_action_routes_ui_key(monkeypatch):
    import gui_actions

    called = {}

    def fake_key(spec):
        called["spec"] = spec
        return f"Sent {spec}."

    monkeypatch.setattr(gui_actions, "send_key", fake_key)
    result = run(server.dispatch_action("UI:KEY:cmd+t"))
    assert called["spec"] == "cmd+t"  # nosec B101
    assert "cmd+t" in result  # nosec B101


def test_dispatch_action_routes_ui_scroll(monkeypatch):
    import gui_actions

    called = {}

    def fake_scroll(direction, amount):
        called["args"] = (direction, amount)
        return f"Scrolled {direction} {amount} line(s)."

    monkeypatch.setattr(gui_actions, "scroll", fake_scroll)
    result = run(server.dispatch_action("UI:SCROLL:down::3"))
    assert called["args"] == ("down", 3)  # nosec B101
    assert "Scrolled" in result  # nosec B101


def test_dispatch_action_ui_scroll_non_numeric_amount_errors():
    result = run(server.dispatch_action("UI:SCROLL:down::abc"))
    assert "amount" in result.lower() or "integer" in result.lower()  # nosec B101


def test_dispatch_action_ui_click_missing_separator_errors():
    """UI:CLICK requires role::label; a missing :: should be rejected with a
    clear message rather than dispatched with empty label."""
    result = run(server.dispatch_action("UI:CLICK:onlyrole"))
    assert "::" in result or "label" in result.lower()  # nosec B101


def test_system_prompt_mentions_all_phase_5_tags():
    prompt = server._build_system_prompt()
    for tag in ("UI:CLICK", "UI:TYPE", "UI:KEY", "UI:SCROLL"):
        assert tag in prompt, tag  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_server.py -v
```

Expected: every new test FAILs — the UI branch only handles FOCUS and OBSERVE today.

- [ ] **Step 3: Extend the `UI` branch in `dispatch_action`**

In `server.py`, locate the existing `if kind == "UI":` block in `dispatch_action`. Replace its body with the extended version below (preserving the surrounding code):

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
        if sub == "CLICK":
            from gui_actions import click_element

            payload = parts[2] if len(parts) > 2 else ""
            role, sep, label = payload.partition("::")
            if not sep:
                return "UI:CLICK needs role::label."
            return await asyncio.to_thread(click_element, role.strip(), label.strip())
        if sub == "TYPE":
            from gui_actions import type_text

            text = parts[2] if len(parts) > 2 else ""
            return await asyncio.to_thread(type_text, text)
        if sub == "KEY":
            from gui_actions import send_key

            spec = parts[2] if len(parts) > 2 else ""
            return await asyncio.to_thread(send_key, spec)
        if sub == "SCROLL":
            from gui_actions import scroll

            payload = parts[2] if len(parts) > 2 else ""
            direction, sep, amount_str = payload.partition("::")
            if not sep:
                return "UI:SCROLL needs direction::amount."
            try:
                amount = int(amount_str.strip())
            except ValueError:
                return f"UI:SCROLL amount must be an integer, got '{amount_str}'."
            return await asyncio.to_thread(scroll, direction.strip(), amount)
        return f"Unknown UI action: {sub}"
```

- [ ] **Step 4: Update the system prompt**

In `server.py`'s `_build_system_prompt`, find the action-tag block. Just AFTER the existing `[ACTION:UI:OBSERVE]` line, insert four new lines:

```log
  [ACTION:UI:CLICK:role::label]          — click a tier-A element by its OBSERVE role/label
  [ACTION:UI:TYPE:text]                  — type the given text into the focused field
  [ACTION:UI:KEY:cmd+t]                  — send a keystroke (cmd/shift/alt/ctrl + char or named key)
  [ACTION:UI:SCROLL:direction::amount]   — scroll the frontmost window (direction: up|down|left|right, amount: lines)
```

Keep the existing "Prefer UI:OBSERVE before acting on UI…" guideline paragraph as-is.

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
git commit -m "feat(server): route UI:CLICK, UI:TYPE, UI:KEY, UI:SCROLL"
```

---

## Task 8 — Live macOS integration tests for write actions (skipped by default)

Two end-to-end tests that exercise the write surface against TextEdit. Skipped by default behind the existing `pytest -m macos` marker.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/integration/test_gui_actions_live.py`

- [ ] **Step 1: Append live tests**

Append to `tests/integration/test_gui_actions_live.py`:

```python
def test_focus_textedit_then_type_and_send_cmd_w():
    """Open TextEdit, type a short marker, then close the window with
    cmd+w (no save). The point is to verify the full FOCUS → TYPE → KEY
    pipeline works end-to-end."""
    import time

    assert "Focused" in gui_actions.focus_app("TextEdit")  # nosec B101
    time.sleep(0.5)
    # New document
    assert "Sent" in gui_actions.send_key("cmd+n")  # nosec B101
    time.sleep(0.5)
    # Type a small unique marker so we can recognize the window
    marker = "JARVIS-phase5-smoke"
    assert marker in gui_actions.type_text(marker)  # nosec B101
    time.sleep(0.3)
    # Close without saving (cmd+w then cmd+d for "Don't Save")
    assert "Sent" in gui_actions.send_key("cmd+w")  # nosec B101
    time.sleep(0.5)
    assert "Sent" in gui_actions.send_key("cmd+d")  # nosec B101


def test_scroll_does_not_raise_on_finder():
    """Smoke check: scroll posts a wheel event without raising. We don't
    assert anything about Finder's visible state — that's brittle. We
    only verify the function returns a success string."""
    assert "Focused" in gui_actions.focus_app("Finder")  # nosec B101
    result = gui_actions.scroll("down", 3)
    assert "Scrolled" in result  # nosec B101


def test_click_finder_menu_via_observe_vocabulary():
    """Focus Finder, observe its UI, find a menu_bar entry, click it,
    then send Escape to dismiss. The OBSERVE → CLICK vocabulary contract
    is what the LLM relies on; this verifies it holds against a real
    macOS app."""
    import time

    assert "Focused" in gui_actions.focus_app("Finder")  # nosec B101
    time.sleep(0.3)
    out = gui_actions.observe_frontmost()
    assert "menu_bar" in out, out  # nosec B101
    # "View" is a stable Finder menu title across recent macOS versions.
    result = gui_actions.click_element("menu_button", "View")
    assert "Clicked" in result, result  # nosec B101
    time.sleep(0.3)
    # Dismiss
    gui_actions.send_key("escape")
```

- [ ] **Step 2: Confirm tests are deselected by default**

```bash
uv run pytest -v
```

Expected: full suite passes; the new live tests are collected as part of the existing `tests/integration/` module but stay deselected per the `addopts = "-m 'not macos'"` setting from phase 4.

If `PytestUnknownMarkWarning` appears, recheck `pyproject.toml`'s `[tool.pytest.ini_options]` block.

- [ ] **Step 3: Optional — run live tests manually**

Reserved for the human user; the implementing agent should NOT run these. Requirements: Accessibility permission granted to the test runner AND Automation permission for "System Events" granted on first prompt:

```bash
uv run pytest -m macos -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_gui_actions_live.py
git commit -m "test(gui): add live macOS write-action integration tests"
```

---

## Verification Summary

After this plan lands, the GUI fast path supports the full read+write surface:

- `gui_actions.py` exports `click_element`, `type_text`, `send_key`, `scroll` alongside phase 4's `focus_app` and `observe_frontmost`.
- `server.py:dispatch_action` routes all six `UI:*` sub-kinds.
- System prompt teaches the LLM the four new tags plus the existing OBSERVE-first guideline (no change to that guideline — it still applies to phase 5 actions).
- All unit tests run without pyobjc installed (dict fixtures + monkeypatched subprocess + injected internal helpers).
- Three live integration tests gated behind `pytest -m macos`.

Minimum verification: `uv run pytest -v` (full suite must be green). Manual end-to-end smoke (after merging this PR):

1. "JARVIS, Slack 활성화해줘" → Slack frontmost
2. "이 화면 보여줘" → OBSERVE dump of Slack
3. "검색창에 동민 쳐줘" → JARVIS issues `UI:CLICK:text_field::Search` then `UI:TYPE:동민`
4. "엔터 눌러줘" → `UI:KEY:return`
5. "아래로 5줄 스크롤" → `UI:SCROLL:down::5`

`safety.classify` already gates each: CLICK on neutral labels SAFE, CLICK on Send/Delete/Buy/etc. CONFIRM, TYPE/KEY always CONFIRM, SCROLL SAFE.

## Follow-ups (separate plans)

1. Phase 6 — `[ACTION:COMPUTER:goal]` + `computer_use.py` (vision-grounded fallback for apps without clean AX).
2. Phase 7 — Optional `step` WebSocket progress message + frontend indicator.
3. Mouse-coordinate click fallback for tier-A elements that don't honor `AXPress` (covered by phase 6 in practice).
4. `MAIL:SEND` real dispatcher implementation (`safety.classify` already gates it).
