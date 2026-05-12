# Computer Use Phase 6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land `[ACTION:COMPUTER:goal]` — the vision-grounded fallback where Anthropic Computer Use drives the screen for apps that don't cleanly expose AX (Figma, Electron canvases, games, web embeds).

**Architecture:** New `computer_use.py` module wraps the Anthropic Computer Use beta. It captures full-screen screenshots (via `screencapture` shell), downscales for the model (via `sips`), and runs the Anthropic tool-use loop. Each tool action returned by the model — `screenshot`, `mouse_move`, `left_click`, `type`, `key`, `scroll`, `wait`, etc. — dispatches to a local executor that uses Quartz CGEvent for coordinate-based mouse moves/clicks and reuses phase 5's `_run_system_events` + `_scroll_via_cgevent` for keystrokes and scroll. Coordinates returned by the model live in the downscaled image space and are mapped back to real screen pixels before posting events. The loop terminates when the model returns text with no further tool_use blocks (or hits the `MAX_TURNS` cap).

**Tech Stack:** Python 3.13, `anthropic` SDK (already in deps), `screencapture` + `sips` shell utilities (built into macOS), Quartz CGEvent for mouse events, reuse of phase 5's `_run_system_events` and `_scroll_via_cgevent` for type/key/scroll.

**Spec:** `docs/specs/2026-05-11-general-agent-design.md` (the `[ACTION:COMPUTER:goal]` row of the action-tag table and the safety table that already gates COMPUTER on `CONFIRM` plus BLOCKED for payment keywords).

**Out of scope:**

- Per-tool-action voice re-confirmation inside the loop. `safety.classify("COMPUTER:goal")` already gates the entire session at `CONFIRM`; once the user authorizes the goal the loop runs without further interrupts. Stricter policies are a follow-up plan.
- Multi-display support. V1 always captures and acts on the **main** display.
- Native macOS Screen Recording permission UI integration. We surface the same kind of error narrate that phase 4's Accessibility prompt uses; the user grants the permission in System Settings just like the AX one.
- Optional `step` WebSocket progress message (phase 7).

---

## Task 1 — Module skeleton, Anthropic Computer Use config, permission helper

**Files:**

- Create: `/Users/dongminyu/Development/01_personal/Jarvis/computer_use.py`
- Create: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_computer_use.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_computer_use.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import computer_use  # noqa: E402


def test_module_exports_run_computer_goal():
    assert callable(computer_use.run_computer_goal)  # nosec B101


def test_module_constants_match_plan():
    assert computer_use.MAX_TURNS == 25  # nosec B101
    assert computer_use.MAX_SCALED_DIM == 1280  # nosec B101
    assert computer_use.COMPUTER_TOOL_TYPE == "computer_20250124"  # nosec B101
    assert computer_use.COMPUTER_USE_BETA == "computer-use-2025-01-24"  # nosec B101


def test_default_model_falls_back_when_env_unset(monkeypatch):
    monkeypatch.delenv("JARVIS_COMPUTER_MODEL", raising=False)
    assert computer_use._model() == "claude-sonnet-4-5-20250929"  # nosec B101


def test_default_model_honors_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_COMPUTER_MODEL", "claude-opus-4-7-20251015")
    assert computer_use._model() == "claude-opus-4-7-20251015"  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: `ModuleNotFoundError: No module named 'computer_use'`.

- [ ] **Step 3: Create module skeleton**

Create `computer_use.py`:

```python
"""Anthropic Computer Use bridge for JARVIS.

Vision-grounded GUI automation fallback for apps that don't cleanly
expose macOS Accessibility (Figma, Electron canvases, games, web
embeds). Handles a single `[ACTION:COMPUTER:goal]` invocation by
running Anthropic's Computer Use tool-call loop until the model
produces a final text answer (or MAX_TURNS triggers).

pyobjc / anthropic / subprocess calls all happen inside the public
entrypoint and helpers below so the module imports cleanly under unit
tests that monkeypatch the seams.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("jarvis.computer")

# Anthropic Computer Use API surface
COMPUTER_TOOL_TYPE = "computer_20250124"
COMPUTER_USE_BETA = "computer-use-2025-01-24"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Loop and image bounds
MAX_TURNS = 25
MAX_SCALED_DIM = 1280  # cap longest edge; preserves aspect ratio
MAX_OUTPUT_TOKENS = 4096


def _model() -> str:
    """Return the Claude model id to drive the Computer Use loop."""
    return os.getenv("JARVIS_COMPUTER_MODEL", DEFAULT_MODEL)


def run_computer_goal(goal: str) -> str:
    """Run a Computer Use session for `goal` and return the final
    narrated result. Filled in by later tasks."""
    raise NotImplementedError
```

- [ ] **Step 4: Run tests and confirm pass**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add computer_use.py tests/test_computer_use.py
git commit -m "feat(computer): scaffold computer_use module and constants"
```

---

## Task 2 — Screenshot capture + downscale pipeline

Anthropic's vision tokens scale with image dimensions; we downscale to a max edge of 1280px before sending. The model returns coordinates in this scaled space, so we keep the scale factor around to map back to real screen pixels in Task 3 onward.

`screencapture -x` (silent, no shutter sound) writes a PNG to a temp path; `sips -Z 1280` resizes in place preserving aspect ratio. Both are built into macOS — no new Python deps.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/computer_use.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_computer_use.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_computer_use.py`:

```python
import base64
from unittest.mock import MagicMock


def test_capture_screenshot_returns_image_dims_scale(monkeypatch, tmp_path):
    """Happy path: screencapture + sips succeed, helper returns
    (b64_png, scaled_w, scaled_h, scale_factor)."""
    fake_png = tmp_path / "fake.png"
    fake_png.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    # Force a deterministic tmp path
    monkeypatch.setattr(computer_use, "_screenshot_path", lambda: str(fake_png))

    runs = []

    def fake_run(args, **kwargs):
        runs.append(args)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    import subprocess

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Native dims and scaled dims come from monkeypatched probes
    monkeypatch.setattr(
        computer_use, "_image_dims", lambda _path: (2880, 1800)
    )

    out = computer_use._capture_screenshot()
    assert out is not None  # nosec B101
    b64, sw, sh, scale = out
    assert b64 == base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()  # nosec B101
    assert sw == 1280  # nosec B101
    # scaled height preserves aspect ratio (rounded): 1800 * 1280 / 2880 = 800
    assert sh == 800  # nosec B101
    # scale factor maps scaled -> native: 2880 / 1280 = 2.25
    assert abs(scale - 2.25) < 1e-6  # nosec B101

    # First subprocess call should be `screencapture -x <path>`
    assert runs[0][0] == "screencapture"  # nosec B101
    assert "-x" in runs[0]  # nosec B101
    # Second call should be `sips -Z 1280 <path> --out <path>`
    assert runs[1][0] == "sips"  # nosec B101
    assert "-Z" in runs[1] and "1280" in runs[1]  # nosec B101


def test_capture_screenshot_returns_none_when_screencapture_fails(monkeypatch):
    """If screencapture exits non-zero (e.g. Screen Recording denied),
    return None so the caller can surface a permission prompt."""
    import subprocess

    def fake_run(args, **kwargs):
        result = MagicMock()
        result.returncode = 0 if args[0] != "screencapture" else 1
        result.stdout = ""
        result.stderr = "denied"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        computer_use, "_screenshot_path", lambda: "/tmp/nope.png"
    )
    assert computer_use._capture_screenshot() is None  # nosec B101


def test_capture_screenshot_skips_sips_when_image_already_under_cap(monkeypatch, tmp_path):
    """Don't bother running sips if the native screen is already at or
    under MAX_SCALED_DIM on the longest edge."""
    fake_png = tmp_path / "fake.png"
    fake_png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    monkeypatch.setattr(computer_use, "_screenshot_path", lambda: str(fake_png))

    runs = []

    def fake_run(args, **kwargs):
        runs.append(args[0])
        result = MagicMock()
        result.returncode = 0
        return result

    import subprocess

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        computer_use, "_image_dims", lambda _path: (1280, 800)
    )

    out = computer_use._capture_screenshot()
    assert out is not None  # nosec B101
    _b64, sw, sh, scale = out
    assert sw == 1280 and sh == 800 and scale == 1.0  # nosec B101
    # screencapture ran but sips did not
    assert "screencapture" in runs  # nosec B101
    assert "sips" not in runs  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: `AttributeError: ... '_capture_screenshot'`.

- [ ] **Step 3: Implement the screenshot pipeline**

Append to `computer_use.py` (after `_model`):

```python
import base64
import tempfile


def _screenshot_path() -> str:
    """Return a fresh temp path for the next screenshot. Separate function
    so tests can pin it to a deterministic path via monkeypatch."""
    fd, path = tempfile.mkstemp(prefix="jarvis_cu_", suffix=".png")
    os.close(fd)
    return path


def _image_dims(path: str) -> Optional[tuple[int, int]]:
    """Probe image dimensions via `sips -g pixelWidth -g pixelHeight`.

    Returns (width, height) or None on failure.
    """
    import subprocess

    try:
        r = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return None
        width = height = 0
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("pixelWidth:"):
                width = int(line.split(":", 1)[1].strip())
            elif line.startswith("pixelHeight:"):
                height = int(line.split(":", 1)[1].strip())
        if width <= 0 or height <= 0:
            return None
        return width, height
    except Exception as e:  # noqa: BLE001
        log.warning("image dims probe failed: %s", e)
        return None


def _capture_screenshot() -> Optional[tuple[str, int, int, float]]:
    """Capture the main display, downscale if needed, return
    (base64_png, scaled_width, scaled_height, scale_factor).

    `scale_factor = native_dim / scaled_dim` is what later helpers use
    to map model-supplied coordinates back into real screen pixels.

    Returns None if screencapture fails (Screen Recording permission
    likely missing) or any subprocess raises.
    """
    import subprocess

    path = _screenshot_path()
    try:
        r = subprocess.run(
            ["screencapture", "-x", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            log.warning("screencapture failed: %s", r.stderr.strip())
            return None

        dims = _image_dims(path)
        if dims is None:
            return None
        native_w, native_h = dims
        scale = 1.0
        scaled_w, scaled_h = native_w, native_h

        if max(native_w, native_h) > MAX_SCALED_DIM:
            r = subprocess.run(
                ["sips", "-Z", str(MAX_SCALED_DIM), path, "--out", path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode != 0:
                log.warning("sips downscale failed: %s", r.stderr.strip())
                return None
            new_dims = _image_dims(path)
            if new_dims is None:
                return None
            scaled_w, scaled_h = new_dims
            # The longer edge maps native_dim -> MAX_SCALED_DIM. Same
            # ratio applies on both axes since sips -Z preserves it.
            if native_w >= native_h:
                scale = native_w / scaled_w
            else:
                scale = native_h / scaled_h

        with open(path, "rb") as f:
            png_bytes = f.read()
        b64 = base64.b64encode(png_bytes).decode()
        return b64, scaled_w, scaled_h, scale
    except Exception as e:  # noqa: BLE001
        log.warning("screenshot pipeline failed: %s", e)
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: all tests PASS (4 existing + 3 new = 7 total).

- [ ] **Step 5: Commit**

```bash
git add computer_use.py tests/test_computer_use.py
git commit -m "feat(computer): add screenshot capture + downscale pipeline"
```

---

## Task 3 — Coordinate-based mouse helpers via Quartz CGEvent

Computer Use returns coordinates in scaled-screenshot space; we always multiply by `scale_factor` (from Task 2) before posting events. Three helpers — `_mouse_move`, `_mouse_click`, `_mouse_drag` — cover the action surface Computer Use uses.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/computer_use.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_computer_use.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_computer_use.py`:

```python
def test_mouse_click_posts_down_then_up_at_scaled_coords(monkeypatch):
    """Coordinates are in scaled-screenshot space; the helper must
    multiply by scale_factor before posting CGEvents."""
    posted = []

    def fake_create(_src, event_type, point, _button):
        return ("event", event_type, point)

    def fake_post(_tap, event):
        posted.append(event)

    monkeypatch.setattr(
        computer_use, "_cg_create_mouse_event", fake_create
    )
    monkeypatch.setattr(computer_use, "_cg_post_event", fake_post)

    # scale_factor=2 → scaled (100, 50) maps to native (200, 100)
    ok = computer_use._mouse_click(100, 50, scale=2.0, button="left")
    assert ok is True  # nosec B101
    assert len(posted) == 2  # down + up  # nosec B101
    _t1, event_type_down, point_down = posted[0]
    _t2, event_type_up, point_up = posted[1]
    assert point_down == (200.0, 100.0)  # nosec B101
    assert point_up == (200.0, 100.0)  # nosec B101
    # Down before Up
    assert event_type_down != event_type_up  # nosec B101


def test_mouse_click_supports_right_and_double(monkeypatch):
    posted = []
    monkeypatch.setattr(
        computer_use,
        "_cg_create_mouse_event",
        lambda _s, t, p, _b: ("event", t, p),
    )
    monkeypatch.setattr(
        computer_use, "_cg_post_event", lambda _tap, event: posted.append(event)
    )
    # Right-click: 1 down + 1 up
    computer_use._mouse_click(10, 10, scale=1.0, button="right")
    assert len(posted) == 2  # nosec B101
    posted.clear()
    # Double-click: 2 down + 2 up
    computer_use._mouse_click(10, 10, scale=1.0, button="left", count=2)
    assert len(posted) == 4  # nosec B101


def test_mouse_move_posts_single_moved_event(monkeypatch):
    posted = []
    monkeypatch.setattr(
        computer_use,
        "_cg_create_mouse_event",
        lambda _s, t, p, _b: ("event", t, p),
    )
    monkeypatch.setattr(
        computer_use, "_cg_post_event", lambda _tap, event: posted.append(event)
    )
    ok = computer_use._mouse_move(50, 25, scale=2.0)
    assert ok is True  # nosec B101
    assert len(posted) == 1  # nosec B101
    _kind, _t, point = posted[0]
    assert point == (100.0, 50.0)  # nosec B101


def test_mouse_drag_posts_down_move_up(monkeypatch):
    posted = []
    monkeypatch.setattr(
        computer_use,
        "_cg_create_mouse_event",
        lambda _s, t, p, _b: ("event", t, p),
    )
    monkeypatch.setattr(
        computer_use, "_cg_post_event", lambda _tap, event: posted.append(event)
    )
    ok = computer_use._mouse_drag(0, 0, 100, 50, scale=1.0)
    assert ok is True  # nosec B101
    # 1 down at start, 1 drag move to end, 1 up at end
    assert len(posted) >= 3  # nosec B101
    _k_first, _t_first, p_first = posted[0]
    _k_last, _t_last, p_last = posted[-1]
    assert p_first == (0.0, 0.0)  # nosec B101
    assert p_last == (100.0, 50.0)  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: `AttributeError: ... '_mouse_click'`.

- [ ] **Step 3: Implement the mouse helpers**

Append to `computer_use.py` (after `_capture_screenshot`):

```python
def _cg_create_mouse_event(source, event_type, point, button):
    """Production CGEvent factory. Tests monkeypatch this."""
    from Quartz import CGEventCreateMouseEvent  # type: ignore

    return CGEventCreateMouseEvent(source, event_type, point, button)


def _cg_post_event(tap, event) -> None:
    """Production CGEvent poster. Tests monkeypatch this."""
    from Quartz import CGEventPost  # type: ignore

    CGEventPost(tap, event)


def _mouse_move(x: float, y: float, scale: float) -> bool:
    """Post a mouse-move event at scaled coordinate (x, y).

    Multiplies by `scale` to recover real-screen pixels.
    """
    try:
        from Quartz import (  # type: ignore
            kCGEventMouseMoved,
            kCGHIDEventTap,
            kCGMouseButtonLeft,
        )

        native = (x * scale, y * scale)
        event = _cg_create_mouse_event(
            None, kCGEventMouseMoved, native, kCGMouseButtonLeft
        )
        if event is None:
            return False
        _cg_post_event(kCGHIDEventTap, event)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("mouse_move failed: %s", e)
        return False


def _mouse_click(
    x: float,
    y: float,
    scale: float,
    button: str = "left",
    count: int = 1,
) -> bool:
    """Post `count` click cycles (down+up) at scaled coordinate (x, y).

    button ∈ {"left", "right", "middle"}; default left. count ≥ 1 for
    single/double/triple clicks.
    """
    try:
        from Quartz import (  # type: ignore
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGEventOtherMouseDown,
            kCGEventOtherMouseUp,
            kCGEventRightMouseDown,
            kCGEventRightMouseUp,
            kCGHIDEventTap,
            kCGMouseButtonCenter,
            kCGMouseButtonLeft,
            kCGMouseButtonRight,
        )

        mapping = {
            "left": (kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGMouseButtonLeft),
            "right": (kCGEventRightMouseDown, kCGEventRightMouseUp, kCGMouseButtonRight),
            "middle": (
                kCGEventOtherMouseDown,
                kCGEventOtherMouseUp,
                kCGMouseButtonCenter,
            ),
        }
        down, up, btn = mapping.get(button, mapping["left"])
        native = (x * scale, y * scale)
        for _ in range(max(1, count)):
            d = _cg_create_mouse_event(None, down, native, btn)
            if d is None:
                return False
            _cg_post_event(kCGHIDEventTap, d)
            u = _cg_create_mouse_event(None, up, native, btn)
            if u is None:
                return False
            _cg_post_event(kCGHIDEventTap, u)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("mouse_click failed: %s", e)
        return False


def _mouse_drag(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    scale: float,
) -> bool:
    """Press at start, drag to end, release. Scaled coordinates."""
    try:
        from Quartz import (  # type: ignore
            kCGEventLeftMouseDown,
            kCGEventLeftMouseDragged,
            kCGEventLeftMouseUp,
            kCGHIDEventTap,
            kCGMouseButtonLeft,
        )

        start_native = (start_x * scale, start_y * scale)
        end_native = (end_x * scale, end_y * scale)
        down = _cg_create_mouse_event(
            None, kCGEventLeftMouseDown, start_native, kCGMouseButtonLeft
        )
        if down is None:
            return False
        _cg_post_event(kCGHIDEventTap, down)
        moved = _cg_create_mouse_event(
            None, kCGEventLeftMouseDragged, end_native, kCGMouseButtonLeft
        )
        if moved is None:
            return False
        _cg_post_event(kCGHIDEventTap, moved)
        up = _cg_create_mouse_event(
            None, kCGEventLeftMouseUp, end_native, kCGMouseButtonLeft
        )
        if up is None:
            return False
        _cg_post_event(kCGHIDEventTap, up)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("mouse_drag failed: %s", e)
        return False
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: 4 new tests PASS (11 total in computer_use tests).

- [ ] **Step 5: Commit**

```bash
git add computer_use.py tests/test_computer_use.py
git commit -m "feat(computer): add coordinate-based mouse helpers via CGEvent"
```

---

## Task 4 — Tool action dispatcher

Maps every Anthropic Computer Use tool action to a local executor. Reuses phase 5's `_run_system_events` (for `type` and `key`) and `_scroll_via_cgevent` (for `scroll`) so we don't duplicate AppleScript / Quartz wiring.

Computer Use key action uses xdotool-style strings (`Return`, `cmd+t`, `ctrl+shift+T`). Our phase 5 `_parse_key_spec` accepts almost identical input — we lowercase and translate a small set of xdotool aliases (`Return → return`, `BackSpace → backspace`, etc.) then forward.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/computer_use.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_computer_use.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_computer_use.py`:

```python
def test_execute_action_screenshot_returns_tool_result_with_image(monkeypatch):
    monkeypatch.setattr(
        computer_use,
        "_capture_screenshot",
        lambda: ("BASE64DATA", 1280, 800, 2.25),
    )
    result = computer_use._execute_action(
        action="screenshot",
        params={},
        scale=1.0,
    )
    assert result["type"] == "image"  # nosec B101
    assert result["data"] == "BASE64DATA"  # nosec B101
    # The fresh screenshot's scale is carried back so subsequent actions
    # in this turn use the right factor.
    assert result["scale"] == 2.25  # nosec B101


def test_execute_action_left_click_uses_scale_factor(monkeypatch):
    calls = {}

    def fake_click(x, y, scale, button="left", count=1):
        calls["args"] = (x, y, scale, button, count)
        return True

    monkeypatch.setattr(computer_use, "_mouse_click", fake_click)
    result = computer_use._execute_action(
        action="left_click",
        params={"coordinate": [100, 200]},
        scale=2.0,
    )
    assert calls["args"] == (100, 200, 2.0, "left", 1)  # nosec B101
    assert result["type"] == "text"  # nosec B101
    assert "click" in result["text"].lower()  # nosec B101


def test_execute_action_double_click(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        computer_use,
        "_mouse_click",
        lambda x, y, scale, button="left", count=1: calls.update(
            args=(x, y, scale, button, count)
        )
        or True,
    )
    computer_use._execute_action(
        action="double_click",
        params={"coordinate": [50, 75]},
        scale=1.0,
    )
    assert calls["args"] == (50, 75, 1.0, "left", 2)  # nosec B101


def test_execute_action_right_click(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        computer_use,
        "_mouse_click",
        lambda x, y, scale, button="left", count=1: calls.update(
            args=(x, y, scale, button, count)
        )
        or True,
    )
    computer_use._execute_action(
        action="right_click",
        params={"coordinate": [10, 10]},
        scale=1.0,
    )
    assert calls["args"] == (10, 10, 1.0, "right", 1)  # nosec B101


def test_execute_action_mouse_move(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        computer_use,
        "_mouse_move",
        lambda x, y, scale: calls.update(args=(x, y, scale)) or True,
    )
    computer_use._execute_action(
        action="mouse_move",
        params={"coordinate": [33, 44]},
        scale=2.5,
    )
    assert calls["args"] == (33, 44, 2.5)  # nosec B101


def test_execute_action_left_click_drag(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        computer_use,
        "_mouse_drag",
        lambda *args: calls.update(args=args) or True,
    )
    computer_use._execute_action(
        action="left_click_drag",
        params={"start_coordinate": [0, 0], "coordinate": [100, 50]},
        scale=1.0,
    )
    assert calls["args"] == (0, 0, 100, 50, 1.0)  # nosec B101


def test_execute_action_type_routes_to_system_events(monkeypatch):
    import gui_actions

    sent = {}
    monkeypatch.setattr(
        gui_actions,
        "_run_system_events",
        lambda action: sent.update(action=action) or True,
    )
    monkeypatch.setattr(
        gui_actions,
        "_escape_applescript_string",
        lambda s: s.replace('"', '\\"'),
    )
    result = computer_use._execute_action(
        action="type",
        params={"text": "hello"},
        scale=1.0,
    )
    assert sent["action"] == 'keystroke "hello"'  # nosec B101
    assert result["type"] == "text"  # nosec B101


def test_execute_action_key_translates_xdotool_aliases(monkeypatch):
    import gui_actions

    sent = []
    monkeypatch.setattr(
        gui_actions,
        "_run_system_events",
        lambda action: sent.append(action) or True,
    )
    # xdotool "Return" → our parser "return" → AppleScript key code 36
    computer_use._execute_action(
        action="key", params={"text": "Return"}, scale=1.0
    )
    assert sent[-1] == "key code 36"  # nosec B101
    # cmd+t → keystroke "t" using {command down}
    computer_use._execute_action(
        action="key", params={"text": "cmd+t"}, scale=1.0
    )
    assert sent[-1] == 'keystroke "t" using {command down}'  # nosec B101


def test_execute_action_scroll_routes_to_cgevent(monkeypatch):
    import gui_actions

    calls = {}
    monkeypatch.setattr(
        gui_actions,
        "_scroll_via_cgevent",
        lambda direction, amount: calls.update(args=(direction, amount)) or True,
    )
    computer_use._execute_action(
        action="scroll",
        params={
            "coordinate": [100, 100],
            "scroll_direction": "down",
            "scroll_amount": 3,
        },
        scale=1.0,
    )
    assert calls["args"] == ("down", 3)  # nosec B101


def test_execute_action_wait_sleeps(monkeypatch):
    import time

    slept = {}
    monkeypatch.setattr(
        time, "sleep", lambda secs: slept.update(secs=secs) or None
    )
    result = computer_use._execute_action(
        action="wait", params={"duration": 0.5}, scale=1.0
    )
    assert slept["secs"] == 0.5  # nosec B101
    assert result["type"] == "text"  # nosec B101


def test_execute_action_unknown_returns_error_text():
    result = computer_use._execute_action(
        action="moonwalk", params={}, scale=1.0
    )
    assert result["type"] == "text"  # nosec B101
    assert "unsupported" in result["text"].lower() or "unknown" in result["text"].lower()  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: `AttributeError: ... '_execute_action'`.

- [ ] **Step 3: Implement the dispatcher**

Append to `computer_use.py` (after `_mouse_drag`):

```python
# xdotool key-name aliases → our _parse_key_spec vocabulary.
_XDOTOOL_KEY_ALIASES: dict[str, str] = {
    "return": "return",
    "enter": "return",
    "backspace": "backspace",
    "delete": "delete",
    "escape": "escape",
    "esc": "escape",
    "tab": "tab",
    "space": "space",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    # Modifier aliases handled by _parse_key_spec already (cmd/ctrl/etc)
}


def _translate_key_spec(xdotool_spec: str) -> str:
    """Translate xdotool key spec to our _parse_key_spec format.

    xdotool uses `Return`, `BackSpace`, `cmd+t`, `ctrl+shift+a`. Our
    parser is case-insensitive and accepts `+`-separated modifiers, so
    the main work is lowercasing and renaming a few special keys.
    """
    parts = [p.strip() for p in xdotool_spec.split("+") if p.strip()]
    if not parts:
        return ""
    translated = []
    for token in parts[:-1]:
        translated.append(token.lower())  # modifier; parser handles aliases
    last = parts[-1].lower()
    translated.append(_XDOTOOL_KEY_ALIASES.get(last, last))
    return "+".join(translated)


def _execute_action(action: str, params: dict, scale: float) -> dict:
    """Run a single Computer Use tool action and return a tool_result
    content block ready for the next message.

    The returned dict has shape:
      {"type": "image", "data": "<b64>", "scale": <new scale>}   # for screenshot
      {"type": "text", "text": "<status>"}                        # everything else

    `scale` is the current factor for translating model coordinates to
    real-screen pixels. A screenshot action can return a NEW scale that
    the caller should adopt for subsequent actions in this turn.
    """
    import gui_actions

    coord = params.get("coordinate") or [0, 0]
    if action == "screenshot":
        shot = _capture_screenshot()
        if shot is None:
            return {
                "type": "text",
                "text": (
                    "Screenshot failed — JARVIS may need Screen Recording "
                    "permission. Grant it in System Settings > Privacy & "
                    "Security > Screen Recording."
                ),
            }
        b64, _w, _h, new_scale = shot
        return {"type": "image", "data": b64, "scale": new_scale}

    if action == "mouse_move":
        _mouse_move(coord[0], coord[1], scale)
        return {"type": "text", "text": f"moved cursor to ({coord[0]}, {coord[1]})"}

    if action in ("left_click", "right_click", "middle_click", "double_click", "triple_click"):
        button = "left"
        count = 1
        if action == "right_click":
            button = "right"
        elif action == "middle_click":
            button = "middle"
        elif action == "double_click":
            count = 2
        elif action == "triple_click":
            count = 3
        _mouse_click(coord[0], coord[1], scale, button=button, count=count)
        return {
            "type": "text",
            "text": f"{action} at ({coord[0]}, {coord[1]})",
        }

    if action == "left_click_drag":
        start = params.get("start_coordinate") or [0, 0]
        end = coord
        _mouse_drag(start[0], start[1], end[0], end[1], scale)
        return {
            "type": "text",
            "text": f"dragged from {start} to {end}",
        }

    if action == "type":
        text = str(params.get("text", ""))
        escaped = gui_actions._escape_applescript_string(text)
        gui_actions._run_system_events(f'keystroke "{escaped}"')
        return {"type": "text", "text": f"typed: {text}"}

    if action == "key":
        spec = _translate_key_spec(str(params.get("text", "")))
        char, key_code, modifiers = gui_actions._parse_key_spec(spec)
        mod_clause = (
            " using {" + ", ".join(modifiers) + "}" if modifiers else ""
        )
        if char is not None:
            applescript = f'keystroke "{char}"' + mod_clause
        elif key_code is not None:
            applescript = f"key code {key_code}" + mod_clause
        else:
            return {"type": "text", "text": f"unsupported key spec: {spec}"}
        gui_actions._run_system_events(applescript)
        return {"type": "text", "text": f"sent key: {spec}"}

    if action == "scroll":
        direction = str(params.get("scroll_direction", "down")).lower()
        amount = int(params.get("scroll_amount", 1))
        gui_actions._scroll_via_cgevent(direction, amount)
        return {
            "type": "text",
            "text": f"scrolled {direction} {amount} line(s)",
        }

    if action == "wait":
        import time

        duration = float(params.get("duration", 1.0))
        time.sleep(duration)
        return {"type": "text", "text": f"waited {duration}s"}

    if action == "cursor_position":
        return {"type": "text", "text": "cursor_position not implemented"}

    return {"type": "text", "text": f"unsupported action: {action}"}
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: 11 new tests PASS (22 total).

- [ ] **Step 5: Commit**

```bash
git add computer_use.py tests/test_computer_use.py
git commit -m "feat(computer): add tool action dispatcher reusing phase 5 helpers"
```

---

## Task 5 — `run_computer_goal` main loop

Wraps Anthropic's tool-call iteration: build the initial messages with the goal + an opening screenshot, call `client.beta.messages.create` with the computer tool, parse the response for `tool_use` blocks, execute each, build tool_result content, append to messages, and loop. Stop conditions: model returns text with no tool_use (success), `MAX_TURNS` reached (timeout), or any exception (error narrate).

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/computer_use.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_computer_use.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_computer_use.py`:

```python
def test_run_computer_goal_returns_permission_message_when_screenshot_fails(monkeypatch):
    monkeypatch.setattr(computer_use, "_capture_screenshot", lambda: None)
    result = computer_use.run_computer_goal("open Chrome")
    assert "permission" in result.lower() or "screen recording" in result.lower()  # nosec B101


def test_run_computer_goal_returns_text_when_model_finishes_without_tool_use(monkeypatch):
    """If the model returns plain text (no tool_use) on the first turn,
    `run_computer_goal` returns that text verbatim."""
    monkeypatch.setattr(
        computer_use,
        "_capture_screenshot",
        lambda: ("B64", 1280, 800, 2.0),
    )

    class FakeBlock:
        def __init__(self, type_, **kwargs):
            self.type = type_
            for k, v in kwargs.items():
                setattr(self, k, v)

    class FakeResponse:
        def __init__(self):
            self.stop_reason = "end_turn"
            self.content = [FakeBlock("text", text="Done. Window is open.")]

    class FakeClient:
        def __init__(self):
            self.beta = self
            self.messages = self

        def create(self, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(computer_use, "_client", lambda: FakeClient())

    result = computer_use.run_computer_goal("any goal")
    assert "Done" in result  # nosec B101


def test_run_computer_goal_loops_through_tool_use(monkeypatch):
    """Model emits one tool_use (left_click), then ends with text. The
    loop must execute the click and produce the final text."""
    monkeypatch.setattr(
        computer_use,
        "_capture_screenshot",
        lambda: ("B64", 1280, 800, 2.0),
    )
    executed = []

    def fake_execute(action, params, scale):
        executed.append((action, params, scale))
        return {"type": "text", "text": "ok"}

    monkeypatch.setattr(computer_use, "_execute_action", fake_execute)

    class FakeBlock:
        def __init__(self, type_, **kwargs):
            self.type = type_
            for k, v in kwargs.items():
                setattr(self, k, v)

    responses = [
        # First response: a tool_use call
        type("R", (), {
            "stop_reason": "tool_use",
            "content": [
                FakeBlock(
                    "tool_use",
                    id="t1",
                    name="computer",
                    input={"action": "left_click", "coordinate": [100, 100]},
                ),
            ],
        })(),
        # Second response: final text
        type("R", (), {
            "stop_reason": "end_turn",
            "content": [FakeBlock("text", text="Clicked it.")],
        })(),
    ]

    class FakeClient:
        def __init__(self):
            self.beta = self
            self.messages = self
            self.call_count = 0

        def create(self, **_kwargs):
            r = responses[self.call_count]
            self.call_count += 1
            return r

    monkeypatch.setattr(computer_use, "_client", lambda: FakeClient())

    result = computer_use.run_computer_goal("click somewhere")
    assert executed == [
        ("left_click", {"action": "left_click", "coordinate": [100, 100]}, 2.0)
    ]  # nosec B101
    assert "Clicked it" in result  # nosec B101


def test_run_computer_goal_hits_max_turns(monkeypatch):
    """If the model keeps emitting tool_use beyond MAX_TURNS, the loop
    bails out with a timeout message."""
    monkeypatch.setattr(
        computer_use,
        "_capture_screenshot",
        lambda: ("B64", 1280, 800, 2.0),
    )
    monkeypatch.setattr(
        computer_use,
        "_execute_action",
        lambda *_a, **_kw: {"type": "text", "text": "ok"},
    )

    class FakeBlock:
        def __init__(self, type_, **kwargs):
            self.type = type_
            for k, v in kwargs.items():
                setattr(self, k, v)

    class FakeClient:
        def __init__(self):
            self.beta = self
            self.messages = self

        def create(self, **_kwargs):
            return type("R", (), {
                "stop_reason": "tool_use",
                "content": [
                    FakeBlock(
                        "tool_use",
                        id="t",
                        name="computer",
                        input={"action": "wait", "duration": 0.01},
                    ),
                ],
            })()

    monkeypatch.setattr(computer_use, "_client", lambda: FakeClient())
    # Reduce MAX_TURNS for a fast test
    monkeypatch.setattr(computer_use, "MAX_TURNS", 3)
    result = computer_use.run_computer_goal("never end")
    assert "max" in result.lower() or "turn" in result.lower()  # nosec B101


def test_run_computer_goal_recovers_on_anthropic_exception(monkeypatch):
    monkeypatch.setattr(
        computer_use,
        "_capture_screenshot",
        lambda: ("B64", 1280, 800, 2.0),
    )

    class FakeClient:
        def __init__(self):
            self.beta = self
            self.messages = self

        def create(self, **_kwargs):
            raise RuntimeError("Anthropic 500")

    monkeypatch.setattr(computer_use, "_client", lambda: FakeClient())
    result = computer_use.run_computer_goal("any")
    assert "error" in result.lower() or "failed" in result.lower()  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: 5 new tests FAIL on `NotImplementedError` from `run_computer_goal`.

- [ ] **Step 3: Implement the loop**

Replace the `run_computer_goal` stub in `computer_use.py` with the full implementation:

```python
def _client():
    """Production Anthropic client factory. Tests monkeypatch this."""
    import anthropic  # type: ignore

    return anthropic.Anthropic()


def run_computer_goal(goal: str) -> str:
    """Drive Anthropic Computer Use until the model produces a final text
    answer or `MAX_TURNS` triggers. Returns the final spoken result.
    """
    if not goal or not goal.strip():
        return "Missing goal for Computer Use."

    shot = _capture_screenshot()
    if shot is None:
        return (
            "JARVIS needs Screen Recording permission to drive Computer Use. "
            "Grant it in System Settings > Privacy & Security > "
            "Screen Recording, then fully quit and relaunch the terminal app."
        )
    b64, scaled_w, scaled_h, scale = shot

    tool_def = {
        "type": COMPUTER_TOOL_TYPE,
        "name": "computer",
        "display_width_px": scaled_w,
        "display_height_px": scaled_h,
    }

    messages: list[dict] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": goal.strip()},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                },
            ],
        }
    ]

    client = _client()
    current_scale = scale

    for turn in range(MAX_TURNS):
        try:
            response = client.beta.messages.create(
                model=_model(),
                max_tokens=MAX_OUTPUT_TOKENS,
                tools=[tool_def],
                messages=messages,
                betas=[COMPUTER_USE_BETA],
            )
        except Exception as e:  # noqa: BLE001
            log.error("Computer Use API call failed: %s", e)
            return f"Computer Use failed: {e}"

        # Look for a tool_use block first
        tool_uses = [b for b in response.content if getattr(b, "type", "") == "tool_use"]
        if not tool_uses:
            # No tool calls — model produced final text
            texts = [
                getattr(b, "text", "")
                for b in response.content
                if getattr(b, "type", "") == "text"
            ]
            return "\n".join(t for t in texts if t).strip() or "Done."

        # Execute every tool_use in order, build the tool_result message
        tool_results: list[dict] = []
        for tu in tool_uses:
            params = getattr(tu, "input", {}) or {}
            action = params.get("action", "")
            outcome = _execute_action(
                action=action, params=params, scale=current_scale
            )
            if outcome.get("type") == "image":
                current_scale = outcome.get("scale", current_scale)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": outcome["data"],
                                },
                            }
                        ],
                    }
                )
            else:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": outcome["text"],
                    }
                )

        # Append assistant turn (the tool_use response) and our results
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return (
        f"Computer Use exceeded the {MAX_TURNS}-turn cap without finishing. "
        "Last action may have partially completed."
    )
```

- [ ] **Step 4: Run and confirm pass**

```bash
uv run pytest tests/test_computer_use.py -v
```

Expected: all tests PASS (22 + 5 = 27 total).

- [ ] **Step 5: Commit**

```bash
git add computer_use.py tests/test_computer_use.py
git commit -m "feat(computer): add run_computer_goal Anthropic tool-call loop"
```

---

## Task 6 — Wire `[ACTION:COMPUTER:goal]` into `server.py` + system prompt

`dispatch_action` gains a `COMPUTER` branch; the system prompt teaches the model the new tag plus a clear "OBSERVE first, COMPUTER last" guideline.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/server.py`
- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/test_server.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_server.py`:

```python
def test_dispatch_action_routes_computer(monkeypatch):
    import computer_use

    called = {}

    def fake_run(goal):
        called["goal"] = goal
        return "Done. Window is open."

    monkeypatch.setattr(computer_use, "run_computer_goal", fake_run)
    result = run(server.dispatch_action("COMPUTER:open Chrome and search asyncio"))
    assert called["goal"] == "open Chrome and search asyncio"  # nosec B101
    assert "Done" in result  # nosec B101


def test_dispatch_action_computer_empty_goal_rejected():
    result = run(server.dispatch_action("COMPUTER:"))
    assert "goal" in result.lower() or "empty" in result.lower()  # nosec B101


def test_system_prompt_mentions_computer_tag():
    prompt = server._build_system_prompt()
    assert "[ACTION:COMPUTER:" in prompt  # nosec B101


def test_system_prompt_prefers_ui_observe_over_computer():
    """The guideline must steer the model toward UI:OBSERVE before falling
    back to COMPUTER (cost + reliability)."""
    prompt = server._build_system_prompt()
    assert "OBSERVE" in prompt  # nosec B101
    # The model is told to prefer AX-based UI actions when feasible.
    assert "fallback" in prompt.lower() or "when" in prompt.lower()  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

```bash
uv run pytest tests/test_server.py -v
```

Expected: the new tests FAIL — `dispatch_action` returns `"Unknown action: COMPUTER"` and the prompt has no COMPUTER line.

- [ ] **Step 3: Add the `COMPUTER` branch in `dispatch_action`**

In `server.py`'s `dispatch_action`, add a new branch alongside the others (before the final `return f"Unknown action: {kind}"`):

```python
    if kind == "COMPUTER":
        from computer_use import run_computer_goal

        goal = parts[1] if len(parts) > 1 else ""
        if len(parts) > 2:
            goal = goal + ":" + parts[2]
        goal = goal.strip()
        if not goal:
            return "COMPUTER needs a non-empty goal."
        return await asyncio.to_thread(run_computer_goal, goal)
```

Note: `tag.split(":", 2)` produces `parts = ["COMPUTER", "<rest>"]` when there's only one `:` after `COMPUTER`. If the goal itself contains colons, the third `parts[2]` element holds the tail; we reassemble before passing to `run_computer_goal`.

- [ ] **Step 4: Update the system prompt**

In `server.py`'s `_build_system_prompt`, find the action-tag block. AFTER the last `[ACTION:UI:SCROLL:...]` line (added in phase 5) and BEFORE the `[ACTION:REMEMBER:fact]` line, insert:

```log
  [ACTION:COMPUTER:goal]                 — vision-grounded fallback (Anthropic Computer Use); use only when UI:* can't reach the target
```

Update the existing "Prefer UI:OBSERVE before acting on UI..." paragraph to also call out COMPUTER ordering. Replace it with:

```log
Prefer UI:OBSERVE before acting on UI. The click target's role/label come from the OBSERVE output's vocabulary. Reach for COMPUTER only when the app doesn't expose AX (Figma canvases, web embeds, games) — it is slower and costlier than UI:* and runs the screen, so reserve it for genuine fallbacks.
```

- [ ] **Step 5: Run all tests**

```bash
uv run pytest -v
```

Expected: every test PASSes.

- [ ] **Step 6: Compile-check**

```bash
uv run python -m compileall server.py computer_use.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat(server): route COMPUTER:goal and teach OBSERVE→UI→COMPUTER ordering"
```

---

## Task 7 — Live macOS integration test (skipped by default)

One smoke test that exercises Computer Use end-to-end against a benign, predictable target (open a new Finder window via the menu bar and confirm a title shows up). Skipped by default behind the existing `-m macos` marker; requires Screen Recording + Accessibility permissions AND the `ANTHROPIC_API_KEY` env var.

**Files:**

- Modify: `/Users/dongminyu/Development/01_personal/Jarvis/tests/integration/test_gui_actions_live.py`

- [ ] **Step 1: Append the live test**

Append to `tests/integration/test_gui_actions_live.py`:

```python
def test_computer_use_round_trip_finder_new_window():
    """Smoke check: Computer Use can drive a single goal end-to-end.

    Requirements: ANTHROPIC_API_KEY set, Screen Recording permission
    granted, Accessibility permission granted, network reachable.

    The test focuses Finder, runs a small goal ("open a new Finder
    window"), and checks that the assistant returned a final answer
    that doesn't look like an error.
    """
    import os
    import time

    if not os.environ.get("ANTHROPIC_API_KEY"):
        import pytest

        pytest.skip("ANTHROPIC_API_KEY not set — Computer Use cannot run")

    import computer_use

    assert "Focused" in gui_actions.focus_app("Finder")  # nosec B101
    time.sleep(0.5)
    result = computer_use.run_computer_goal(
        "Open a new Finder window using the File menu, then briefly describe what you see."
    )
    # We don't assert specific window contents — Finder layout varies.
    # We just verify the loop terminated with a non-error answer.
    assert isinstance(result, str)  # nosec B101
    assert "failed" not in result.lower(), result  # nosec B101
    assert "exceeded" not in result.lower(), result  # nosec B101
```

- [ ] **Step 2: Confirm test is deselected by default**

```bash
uv run pytest -v
```

Expected: the new live test is collected but stays deselected per `addopts = "-m 'not macos'"`. Full unit suite passes.

- [ ] **Step 3: Do NOT run live tests**

Reserved for the human user. The implementing agent must NOT execute `uv run pytest -m macos`. The default `uv run pytest -v` is sufficient.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_gui_actions_live.py
git commit -m "test(computer): add live Computer Use round-trip test"
```

---

## Verification Summary

After this plan lands, the GUI stack supports both the AX fast path (phase 4+5) and the vision-grounded fallback (phase 6):

- `computer_use.py` exports `run_computer_goal(goal)` plus its internal screenshot, mouse, and tool-dispatch helpers.
- `server.py:dispatch_action` routes `COMPUTER:<goal>` through `asyncio.to_thread` (the loop is sync because of pyobjc + subprocess).
- System prompt teaches the model to prefer UI:OBSERVE → UI:\* and reach for COMPUTER only as a fallback.
- `safety.classify` already gates COMPUTER on `CONFIRM` (and BLOCKED on payment keywords) — no safety changes.
- Phase 5 helpers (`_run_system_events`, `_escape_applescript_string`, `_parse_key_spec`, `_scroll_via_cgevent`) are reused — Computer Use's `type`/`key`/`scroll` actions don't duplicate AppleScript or CGEvent code.

Minimum verification: `uv run pytest -v` (green). Manual end-to-end smoke (post-merge):

1. "JARVIS, Figma에서 선택된 레이어 색을 빨강으로 바꿔줘" → CONFIRM gate → "응" → run_computer_goal drives the Figma canvas.
2. Watch `jarvis.computer` logs for tool action sequence (screenshot → click → type → final text).
3. If Screen Recording is denied → the first screenshot returns None and the user gets a System Settings prompt narrate.

## Follow-ups (separate plans)

1. Optional `step` WebSocket progress message + frontend indicator (phase 7) — would surface each tool action ("clicked Chrome", "typed asyncio") to the UI so the user can see progress mid-loop.
2. Per-tool-action safety gating inside the loop (e.g. re-confirm when Computer Use is about to click a button whose visible label looks risky). YAGNI until we observe real misuse.
3. Multi-display support (currently main display only). The screenshot pipeline would need a display-id parameter and the click helpers would need to know which display's coordinate space they're in.
4. `cursor_position` action — currently returns a placeholder; rarely needed in practice but should be implemented for completeness if a model requests it.
