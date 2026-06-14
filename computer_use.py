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

import base64
import logging
import os
import tempfile
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
            # sips -Z scales the longest edge to MAX_SCALED_DIM and
            # preserves aspect ratio. Compute the resulting dims
            # analytically rather than re-probing: the ratio is exact and
            # avoids a second subprocess round-trip.
            if native_w >= native_h:
                scale = native_w / MAX_SCALED_DIM
                scaled_w = MAX_SCALED_DIM
                scaled_h = round(native_h / scale)
            else:
                scale = native_h / MAX_SCALED_DIM
                scaled_h = MAX_SCALED_DIM
                scaled_w = round(native_w / scale)

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
