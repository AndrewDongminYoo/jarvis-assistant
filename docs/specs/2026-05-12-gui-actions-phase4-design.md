# GUI Actions — Phase 4 (Observe + Focus) Design

Status: Draft
Date: 2026-05-12
Owner: Dongmin
Parent spec: `docs/specs/2026-05-11-general-agent-design.md`

## Goal

Land the first slice of `gui_actions.py` — the Accessibility-based fast path
for known macOS apps — with two read-only action tags: `UI:FOCUS` and
`UI:OBSERVE`. This validates the AX traversal + pruning pipeline before
phase 5 introduces write actions (CLICK, TYPE, KEY, SCROLL).

## Non-Goals

- Any write action (CLICK, TYPE, KEY, SCROLL) — deferred to phase 5.
- `[ACTION:COMPUTER:goal]` and `computer_use.py` — deferred to phase 6.
- Cross-app workflows. Both tags operate on the **frontmost** app only;
  FOCUS may change which app is frontmost, but OBSERVE has no argument.
- Custom AX inspection UIs or debug tools.

## Decisions

| Axis             | Decision                                                                                |
| ---------------- | --------------------------------------------------------------------------------------- |
| Output format    | Indented plain text, two spaces per level                                               |
| Pruning          | Click/input-target roles only + surrounding labels                                      |
| Role naming      | AX prefix stripped, snake_case (`AXButton` → `button`)                                  |
| FOCUS mechanism  | Substring match against running apps via `NSWorkspace`; AppleScript `activate` fallback |
| OBSERVE scope    | Frontmost app implicit; no argument                                                     |
| Limits           | `MAX_ELEMENTS = 250`, `MAX_DEPTH = 15`                                                  |
| Permission check | At every call site, not cached, since the system setting can flip                       |

## Action Tags

```plaintext
[ACTION:UI:FOCUS:<app_name>]   # bring the named app frontmost; substring match
                               # against NSWorkspace.runningApplications() localized
                               # names (case-insensitive). On miss, fall back to
                               # AppleScript `tell app "<name>" to activate` which
                               # also launches a closed app.

[ACTION:UI:OBSERVE]             # dump pruned UI tree of the frontmost app. No
                               # argument — always the current frontmost.
```

Both classify as `Decision.SAFE` per the existing `safety.classify` table.
No changes to `safety.py` are required.

### System prompt update

`server.py:_build_system_prompt` adds two lines to the action tag list and a
short guideline:

```log
[ACTION:UI:FOCUS:app_name]             — activate an app (Chrome, Slack, Mail…)
[ACTION:UI:OBSERVE]                    — read the frontmost app's UI

Prefer UI:OBSERVE before acting on UI. The click target's role/label come
from the OBSERVE output's vocabulary.
```

## Module Structure

### `gui_actions.py` (new)

Public surface — three functions, all returning human-readable result strings
(the same shape every other `dispatch_action` handler uses):

```python
def focus_app(name: str) -> str
def observe_frontmost() -> str
def is_accessibility_permitted() -> bool
```

Internal helpers (private, unit-tested in isolation):

```python
def _normalize_role(ax_role: str) -> str | None      # AXButton -> "button", drops uninteresting
def _label_for(element) -> str | None                # AXTitle → AXValue → AXDescription → AXHelp
def _format_element(role: str, label: str | None,
                    value: str | None, enabled: bool, depth: int) -> str
def _traverse(root, *, depth: int = 0,
              budget: list[int]) -> list[str]        # DFS with element budget
def _running_app_pid(name: str) -> int | None        # NSWorkspace match
def _applescript_activate(name: str) -> bool         # subprocess fallback
```

`budget` is passed as a mutable single-element list so the recursion can
share a counter without globals.

### Dependencies

Added to `pyproject.toml`:

```toml
pyobjc-framework-ApplicationServices  # AX API
pyobjc-framework-Cocoa                 # NSWorkspace, NSRunningApplication
```

Both are macOS-only. The module imports them lazily inside the public
functions so `from gui_actions import ...` at module load time doesn't fail
in environments without pyobjc (test fixtures, CI).

### `server.py` changes

Two new branches in `dispatch_action`:

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

System prompt updated. No other server-side changes.

## Pruning Rules

### Tier A — content roles (always emitted when a label exists)

| AX role                      | Output        | Rationale            |
| ---------------------------- | ------------- | -------------------- |
| `AXButton`                   | `button`      | Click target         |
| `AXLink`                     | `link`        | Click target         |
| `AXTextField`                | `text_field`  | Input target         |
| `AXTextArea`                 | `text_area`   | Input target         |
| `AXCheckBox`                 | `checkbox`    | Click target         |
| `AXRadioButton`              | `radio`       | Click target         |
| `AXMenuItem`                 | `menu_item`   | Click target         |
| `AXMenuButton`               | `menu_button` | Click target         |
| `AXTab`                      | `tab`         | Click target         |
| `AXStaticText`               | `text`        | Identifies neighbors |
| `AXRow`                      | `row`         | List/table item      |
| `AXCell`                     | `cell`        | Table item           |
| `AXPopUpButton`              | `popup`       | Dropdown             |
| `AXComboBox`                 | `combo`       | Dropdown             |
| `AXImage` (with description) | `image`       | Labeled icon         |

### Tier B — structural roles (emitted only when they have at least one emitted descendant)

| AX role      | Output      |
| ------------ | ----------- |
| `AXWindow`   | `window`    |
| `AXToolbar`  | `toolbar`   |
| `AXMenuBar`  | `menu_bar`  |
| `AXMenu`     | `menu`      |
| `AXTabGroup` | `tab_group` |

These help the LLM locate content spatially ("Send button inside the
Compose window"). They emit without a quoted label when their own
`AXTitle` is empty — just the bare snake_case role.

### Roles ignored

Container-only roles (`AXGroup`, `AXScrollArea`, `AXLayoutItem`,
`AXSplitter`, `AXSplitGroup`, `AXOutline`, `AXList`, `AXTable`) are walked
through but never emitted as their own lines. Their tier-A/B descendants
are emitted at the depth they would have had if the container were absent.

Unknown roles fall through `_normalize_role` returning `None` and are
ignored the same way (children still walked).

### Label extraction

First non-empty of: `AXTitle`, `AXValue`, `AXDescription`, `AXHelp`. Whitespace
trimmed. If all empty, the element is dropped — without a label there's
nothing for the LLM to reference in a follow-up CLICK.

### Element line format

```log
<role> "<label>"
```

If the element is a `text_field` or `text_area` with a non-empty `AXValue`
distinct from its label, the format extends to:

```log
text_field "Search" "current value"
```

If `AXEnabled` is `False`, append `[disabled]`. Enabled is the default and not annotated.

### Limits

- `MAX_ELEMENTS = 250` — DFS counts every emitted line; on cap, traversal
  stops and the last output line is `[... truncated, N more elements skipped]`
  where N is computed by continuing the walk in count-only mode.
- `MAX_DEPTH = 15` — depths beyond are not walked. No marker; deep menus
  rarely matter to the agent.

### Indentation

Two spaces per nesting level, where "level" counts only emitted (non-skipped)
ancestors. The root window starts at depth 0.

## Sample Output

Mail.app frontmost, 3 unread messages:

```log
window "Inbox"
  toolbar
    button "New Message"
    button "Reply"
    button "Reply All" [disabled]
    button "Forward" [disabled]
    text_field "Search" ""
  text "Inbox · 3 unread"
  row
    text "Anna"
    text "Lunch tomorrow?"
    text "10:23 AM"
  row
    text "GitHub"
    text "[PR #42] approved"
    text "Yesterday"
menu_bar
  menu_button "File"
  menu_button "Edit"
  menu_button "View"
```

The `window`, `toolbar`, and `menu_bar` lines are tier-B structural roles
(see the pruning table above). They emit only because they have at least
one emitted descendant. A toolbar with no labeled buttons would be
elided.

## FOCUS Mechanism

1. `_running_app_pid(name)` iterates `NSWorkspace.sharedWorkspace().runningApplications()`
   and returns the first `processIdentifier` whose `localizedName` contains
   `name` case-insensitively. So `focus_app("chrome")` matches "Google Chrome".
2. If found, send `AXFrontmost = True` via the AX API on
   `AXUIElementCreateApplication(pid)`. This brings the app forward without
   spawning a new process.
3. If no running app matches, run `osascript -e 'tell app "<name>" to activate'`.
   This launches a closed app by bundle name. Timeout 10s. On non-zero exit,
   return `"Couldn't find an app matching '<name>'."`.
4. On success, return `"Focused <localizedName>."` (whichever name actually
   matched, so the LLM sees the canonical form).

## Permission Handling

`is_accessibility_permitted()` calls `AXIsProcessTrustedWithOptions(None)`
(no prompt). Returns the boolean.

Every public function (`focus_app`, `observe_frontmost`) calls
`is_accessibility_permitted()` first. On `False`:

```log
JARVIS needs Accessibility permission. Open System Settings >
Privacy & Security > Accessibility and enable the terminal or app that
runs JARVIS.
```

The check is not cached — the user might toggle the permission while the
server is running. Each call is a fast IPC and runs synchronously.

## Error Paths

| Case                                           | Handler returns                                                 |
| ---------------------------------------------- | --------------------------------------------------------------- |
| AX permission missing                          | The Korean+English narrate prompt above                         |
| No frontmost app (Finder showing desktop only) | `"No frontmost app — try 'focus <app name>' first."`            |
| `focus_app`: name miss + AppleScript fail      | `"Couldn't find an app matching '<name>'."`                     |
| `observe_frontmost`: AX call raises            | Log the exception, return `"Couldn't read UI from <app_name>."` |
| Traversal exceeds 5 seconds                    | Stop, return partial output + `[... timed out]` line            |

All errors return human-readable strings rather than raising. `_run_action_loop`
already treats these as ordinary step results, so the LLM can incorporate
them into the next iteration's response.

## Test Strategy

| Target                       | File                                         | Approach                                                |
| ---------------------------- | -------------------------------------------- | ------------------------------------------------------- |
| `_normalize_role`            | `tests/test_gui_actions.py`                  | Parameterized table                                     |
| `_label_for`                 | same                                         | Fixture elements with each label source missing         |
| `_format_element`            | same                                         | Disabled flag, value-distinct-from-title, missing label |
| `_traverse`                  | same                                         | Synthetic dict tree, expected indented-text output      |
| `MAX_ELEMENTS` truncation    | same                                         | 1000-element fixture → 250 + truncation marker          |
| `MAX_DEPTH` limit            | same                                         | 20-deep fixture → no lines at depth 16+                 |
| `focus_app` name matching    | same                                         | Monkeypatch NSWorkspace + subprocess.run                |
| `is_accessibility_permitted` | same                                         | Monkeypatch `AXIsProcessTrustedWithOptions`             |
| Live AX integration          | `tests/integration/test_gui_actions_live.py` | `pytest -m macos`, default skip                         |

The live integration test verifies the smallest possible end-to-end:
focus Finder, observe, expect at least one menu bar entry. Skipped by
default because it requires a logged-in macOS session with Accessibility
granted to the test runner.

## Rollout

Single PR:

1. Add `gui_actions.py` with all internal helpers, unit-tested in isolation
   using fixture trees.
2. Wire `UI:FOCUS` and `UI:OBSERVE` into `server.py:dispatch_action`.
3. Update `_build_system_prompt` to teach the LLM about the new tags.
4. Add `pyobjc-framework-ApplicationServices` and `pyobjc-framework-Cocoa`
   to `pyproject.toml` and `uv.lock`.
5. Run full suite green; manually verify against Mail, Finder, Chrome,
   Slack, and Notes.

Phase 5 (CLICK/TYPE/KEY/SCROLL) lands in a separate plan once OBSERVE's
output stability is confirmed across several apps.

## Open Questions

- Should OBSERVE cache the last observation for one turn so a follow-up
  CLICK doesn't need a second AX walk? Defer until phase 5 shows the cost.
- For apps that don't cleanly expose AX (web canvases, Electron with
  Accessibility disabled), what's the graceful degradation? Currently a
  near-empty tree. Document in phase 6 (computer_use) as the fallback
  trigger.
- Do we need a way to override `MAX_ELEMENTS` per call? Probably yes
  eventually, but YAGNI for phase 4.
