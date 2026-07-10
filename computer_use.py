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
import re
import tempfile
from collections.abc import Callable
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


class DisplayScale(float):
    origin_x: float
    origin_y: float
    display_id: int | None

    def __new__(
        cls,
        scale: float,
        origin: tuple[float, float] = (0.0, 0.0),
        display_id: int | None = None,
    ):
        value = float.__new__(cls, scale)
        value.origin_x = origin[0]
        value.origin_y = origin[1]
        value.display_id = display_id
        return value


ToolProgressCallback = Callable[[dict, dict], None]

_RISKY_TYPE_FRAGMENTS = (
    "rm -rf",
    "sudo rm",
    "diskutil erase",
    "mkfs",
    "dd if=",
    "shutdown -h",
    "reboot",
)
_RISKY_TEXT_KEYWORDS = (
    "pay",
    "payment",
    "transfer",
    "bank",
    "password",
    "송금",
    "결제",
    "이체",
    "비밀번호",
)
_BLOCKED_KEY_SPECS = frozenset(
    {
        "cmd+q",
        "command+q",
        "cmd+w",
        "command+w",
        "cmd+shift+q",
        "command+shift+q",
    }
)


def _matching_risky_text_fragment(text: str) -> str | None:
    normalized = " ".join(text.casefold().split())
    for fragment in _RISKY_TYPE_FRAGMENTS:
        if fragment in normalized:
            return fragment
    for keyword in _RISKY_TEXT_KEYWORDS:
        if keyword.isascii():
            if re.search(rf"\b{re.escape(keyword)}\b", normalized):
                return keyword
        elif keyword in normalized:
            return keyword
    return None


def _emit_tool_progress(
    progress_callback: ToolProgressCallback | None,
    params: dict,
    outcome: dict,
) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(params, outcome)
    except Exception as e:  # noqa: BLE001
        log.warning("Computer Use progress callback failed: %s", e)


def _safety_block_reason(action: str, params: dict) -> str | None:
    if action == "type":
        text = str(params.get("text", ""))
        fragment = _matching_risky_text_fragment(text)
        if fragment is not None:
            return (
                "Blocked risky Computer Use action 'type': refusing to type "
                f"text containing {fragment!r}: {text}"
            )
        return None
    if action in ("key", "hold_key"):
        spec = _translate_key_spec(str(params.get("text", "")))
        fragment = _matching_risky_text_fragment(spec)
        if fragment is not None:
            return (
                f"Blocked risky Computer Use action '{action}': refusing to "
                f"send text containing {fragment!r}: {spec}"
            )
        if spec in _BLOCKED_KEY_SPECS:
            return (
                f"Blocked risky Computer Use action '{action}': refusing to "
                f"send {spec!r}."
            )
    return None


def _capture_selected_display(
    display_id: int | None,
) -> Optional[tuple[str, int, int, float]]:
    if display_id is None:
        return _capture_screenshot()
    return _capture_screenshot(display_id=display_id)


def _model() -> str:
    """Return the Claude model id to drive the Computer Use loop."""
    return os.getenv("JARVIS_COMPUTER_MODEL", DEFAULT_MODEL)


def _client():
    """Production Anthropic client factory. Tests monkeypatch this."""
    import anthropic  # type: ignore

    return anthropic.Anthropic()


def run_computer_goal(
    goal: str,
    progress_callback: ToolProgressCallback | None = None,
    display_id: int | None = None,
) -> str:
    """Drive Anthropic Computer Use until the model produces a final text
    answer or `MAX_TURNS` triggers. Returns the final spoken result.
    """
    if not goal or not goal.strip():
        return "Missing goal for Computer Use."

    shot = _capture_selected_display(display_id)
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

    for _turn in range(MAX_TURNS):
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
        tool_uses = [
            b for b in response.content if getattr(b, "type", "") == "tool_use"
        ]
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
            action = str(params.get("action", ""))
            block_reason = _safety_block_reason(action, params)
            if block_reason is None:
                outcome = _execute_action(
                    action=action, params=params, scale=current_scale
                )
            else:
                outcome = {"type": "text", "text": block_reason}
            _emit_tool_progress(progress_callback, params, outcome)
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


def _logical_display_size() -> Optional[tuple[int, int]]:
    """Return the main display's size in *logical points* via Quartz.

    `screencapture` produces an image in physical pixels (2x on a Retina
    display), but Quartz CGEvent mouse events are posted in the global
    logical-point coordinate space. The two differ by the backing scale
    factor (DPR). We need the logical size to map model coordinates back
    correctly. Separate function so tests can monkeypatch it.

    Returns (width_pt, height_pt) or None on failure.
    """
    try:
        from Quartz import CGDisplayBounds, CGMainDisplayID  # type: ignore

        bounds = CGDisplayBounds(CGMainDisplayID())
        return int(round(bounds.size.width)), int(round(bounds.size.height))
    except Exception as e:  # noqa: BLE001
        log.warning("logical display size probe failed: %s", e)
        return None


def _logical_display_bounds(display_id: int) -> Optional[tuple[int, int, int, int]]:
    if display_id <= 0:
        return None
    try:
        from AppKit import NSScreen
        from Quartz import CGDisplayBounds

        screens = NSScreen.screens()
        if display_id > len(screens):
            return None
        screen_number = (
            screens[display_id - 1].deviceDescription().get("NSScreenNumber")
        )
        if screen_number is None:
            return None
        bounds = CGDisplayBounds(int(screen_number))
        return (
            int(round(bounds.origin.x)),
            int(round(bounds.origin.y)),
            int(round(bounds.size.width)),
            int(round(bounds.size.height)),
        )
    except (ImportError, AttributeError, IndexError, TypeError, ValueError) as e:
        log.warning("logical display bounds probe failed: %s", e)
        return None


def _capture_screenshot(
    display_id: int | None = None,
) -> Optional[tuple[str, int, int, float]]:
    """Capture the main display, downscale if needed, return
    (base64_png, scaled_width, scaled_height, scale_factor).

    `scale_factor = logical_dim / scaled_dim` maps a model-supplied
    coordinate (in the downscaled image space we send to the model) back
    into the global *logical-point* space that Quartz CGEvent mouse
    events use. On a Retina display the captured image is in physical
    pixels (e.g. 2880px wide) while CGEvent expects logical points (e.g.
    1440), so the factor must fold in the backing scale factor — using
    physical pixels here would post clicks at ~2x the intended position.

    Returns None if screencapture fails (Screen Recording permission
    likely missing) or any subprocess raises.
    """
    import subprocess

    path = _screenshot_path()
    try:
        capture_command = ["screencapture", "-x"]
        if display_id is not None:
            capture_command.extend(["-D", str(display_id)])
        capture_command.append(path)
        r = subprocess.run(
            capture_command,
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
            ratio = MAX_SCALED_DIM / max(native_w, native_h)
            scaled_w = (
                MAX_SCALED_DIM if native_w >= native_h else round(native_w * ratio)
            )
            scaled_h = (
                MAX_SCALED_DIM if native_h > native_w else round(native_h * ratio)
            )

        # Map the sent-image width to logical points (CGEvent space). The
        # aspect ratio is preserved across physical -> sent and physical
        # -> logical, so a single scalar from width suffices.
        if display_id is not None:
            logical_bounds = _logical_display_bounds(display_id)
            if logical_bounds is not None and logical_bounds[2] > 0:
                origin_x, origin_y, logical_w, _logical_h = logical_bounds
                scale = DisplayScale(
                    logical_w / scaled_w,
                    (float(origin_x), float(origin_y)),
                    display_id,
                )
            else:
                scale = DisplayScale(native_w / scaled_w, display_id=display_id)
        else:
            logical = _logical_display_size()
            if logical is not None and logical[0] > 0:
                scale = DisplayScale(logical[0] / scaled_w)
            else:
                # No logical size available: assume the capture is already in
                # logical space (DPR=1). Correct on non-Retina; degraded but
                # no worse than ignoring DPR on Retina.
                scale = DisplayScale(native_w / scaled_w)

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


def _logical_point(x: float, y: float, scale: float) -> tuple[float, float]:
    return (
        float(getattr(scale, "origin_x", 0.0)) + (x * float(scale)),
        float(getattr(scale, "origin_y", 0.0)) + (y * float(scale)),
    )


def _scale_display_id(scale: float) -> int | None:
    display_id = getattr(scale, "display_id", None)
    if isinstance(display_id, int):
        return display_id
    return None


def _cg_create_mouse_event(source, event_type, point, button):
    """Production CGEvent factory. Tests monkeypatch this."""
    from Quartz import CGEventCreateMouseEvent  # type: ignore

    return CGEventCreateMouseEvent(source, event_type, point, button)


def _cg_post_event(tap, event) -> None:
    """Production CGEvent poster. Tests monkeypatch this."""
    from Quartz import CGEventPost  # type: ignore

    CGEventPost(tap, event)


def _cg_create_event(source):
    from Quartz import CGEventCreate  # type: ignore

    return CGEventCreate(source)


def _cg_event_location(event):
    from Quartz import CGEventGetLocation  # type: ignore

    return CGEventGetLocation(event)


def _cursor_position() -> Optional[tuple[float, float]]:
    try:
        event = _cg_create_event(None)
        if event is None:
            return None
        point = _cg_event_location(event)
        return float(point.x), float(point.y)
    except Exception as e:  # noqa: BLE001
        log.warning("cursor_position failed: %s", e)
        return None


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

        native = _logical_point(x, y, scale)
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
            "right": (
                kCGEventRightMouseDown,
                kCGEventRightMouseUp,
                kCGMouseButtonRight,
            ),
            "middle": (
                kCGEventOtherMouseDown,
                kCGEventOtherMouseUp,
                kCGMouseButtonCenter,
            ),
        }
        down, up, btn = mapping.get(button, mapping["left"])
        native = _logical_point(x, y, scale)
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

        start_native = _logical_point(start_x, start_y, scale)
        end_native = _logical_point(end_x, end_y, scale)
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


def _mouse_button(x: float, y: float, scale: float, *, pressed: bool) -> bool:
    """Post a single left-button down OR up event at scaled (x, y).

    Used for `left_mouse_down` / `left_mouse_up`, which the model emits
    to compose fine-grained press-hold-release sequences (selection,
    custom drags) that a one-shot click can't express.
    """
    try:
        from Quartz import (  # type: ignore
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGHIDEventTap,
            kCGMouseButtonLeft,
        )

        event_type = kCGEventLeftMouseDown if pressed else kCGEventLeftMouseUp
        native = _logical_point(x, y, scale)
        event = _cg_create_mouse_event(None, event_type, native, kCGMouseButtonLeft)
        if event is None:
            return False
        _cg_post_event(kCGHIDEventTap, event)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("mouse_button failed: %s", e)
        return False


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


# US-ANSI virtual key codes for held keys (CGEvent keyboard events).
# Letters/digits live here; named keys reuse gui_actions._NAMED_KEY_CODES.
_VIRTUAL_KEYCODES: dict[str, int] = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "o": 31,
    "u": 32,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "k": 40,
    "n": 45,
    "m": 46,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "5": 23,
    "6": 22,
    "7": 26,
    "8": 28,
    "9": 25,
    "0": 29,
}

# Modifier names → their own virtual key codes (for holding a bare modifier).
_MODIFIER_KEYCODES: dict[str, int] = {
    "command": 55,
    "cmd": 55,
    "shift": 56,
    "option": 58,
    "opt": 58,
    "alt": 58,
    "control": 59,
    "ctrl": 59,
    "fn": 63,
}
_MODIFIER_NAMES = frozenset(_MODIFIER_KEYCODES)


def _resolve_hold_key(spec: str) -> tuple[Optional[int], list[str]]:
    """Resolve a translated key spec to (virtual_keycode, modifier_names).

    Returns (None, []) if the key can't be mapped to a virtual key code.
    A lone modifier (e.g. "shift") resolves to that modifier's own key
    code with no extra flags.
    """
    import gui_actions

    parts = [p for p in spec.split("+") if p]
    if not parts:
        return None, []
    *mods, key = parts
    for m in mods:
        if m not in _MODIFIER_NAMES:
            return None, []
    if not mods and key in _MODIFIER_KEYCODES:
        return _MODIFIER_KEYCODES[key], []
    keycode = (
        _VIRTUAL_KEYCODES.get(key)
        or gui_actions._NAMED_KEY_CODES.get(key)
        or _MODIFIER_KEYCODES.get(key)
    )
    if keycode is None:
        return None, []
    return keycode, mods


def _cg_create_keyboard_event(keycode: int, key_down: bool):
    """Production CGEvent keyboard factory. Tests monkeypatch this."""
    from Quartz import CGEventCreateKeyboardEvent  # type: ignore

    return CGEventCreateKeyboardEvent(None, keycode, key_down)


def _cg_set_flags(event, flags) -> None:
    """Production CGEvent flag setter. Tests monkeypatch this."""
    from Quartz import CGEventSetFlags  # type: ignore

    CGEventSetFlags(event, flags)


def _hold_key(spec: str, duration: float) -> bool:
    """Press the keys in `spec`, hold for `duration` seconds, release.

    Uses CGEvent keyboard events (System Events `keystroke` is atomic and
    can't hold). Returns False if the spec can't be resolved.
    """
    import time

    keycode, mod_names = _resolve_hold_key(spec)
    if keycode is None:
        return False
    try:
        from Quartz import (  # type: ignore
            kCGEventFlagMaskAlternate,
            kCGEventFlagMaskCommand,
            kCGEventFlagMaskControl,
            kCGEventFlagMaskShift,
            kCGHIDEventTap,
        )

        flag_map = {
            "cmd": kCGEventFlagMaskCommand,
            "command": kCGEventFlagMaskCommand,
            "shift": kCGEventFlagMaskShift,
            "ctrl": kCGEventFlagMaskControl,
            "control": kCGEventFlagMaskControl,
            "alt": kCGEventFlagMaskAlternate,
            "opt": kCGEventFlagMaskAlternate,
            "option": kCGEventFlagMaskAlternate,
        }
        flags = 0
        for m in mod_names:
            flags |= flag_map.get(m, 0)

        down = _cg_create_keyboard_event(keycode, True)
        if down is None:
            return False
        if flags:
            _cg_set_flags(down, flags)
        _cg_post_event(kCGHIDEventTap, down)

        time.sleep(max(0.0, duration))

        up = _cg_create_keyboard_event(keycode, False)
        if up is None:
            return False
        if flags:
            _cg_set_flags(up, flags)
        _cg_post_event(kCGHIDEventTap, up)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("hold_key failed: %s", e)
        return False


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
        shot = _capture_selected_display(_scale_display_id(scale))
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
        if not _mouse_move(coord[0], coord[1], scale):
            return {
                "type": "text",
                "text": f"failed to move cursor to ({coord[0]}, {coord[1]})",
            }
        return {"type": "text", "text": f"moved cursor to ({coord[0]}, {coord[1]})"}

    if action in (
        "left_click",
        "right_click",
        "middle_click",
        "double_click",
        "triple_click",
    ):
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
        if not _mouse_click(coord[0], coord[1], scale, button=button, count=count):
            return {
                "type": "text",
                "text": f"failed {action} at ({coord[0]}, {coord[1]})",
            }
        return {
            "type": "text",
            "text": f"{action} at ({coord[0]}, {coord[1]})",
        }

    if action == "left_click_drag":
        start = params.get("start_coordinate") or [0, 0]
        end = coord
        if not _mouse_drag(start[0], start[1], end[0], end[1], scale):
            return {"type": "text", "text": f"failed to drag from {start} to {end}"}
        return {
            "type": "text",
            "text": f"dragged from {start} to {end}",
        }

    if action in ("left_mouse_down", "left_mouse_up"):
        pressed = action == "left_mouse_down"
        if not _mouse_button(coord[0], coord[1], scale, pressed=pressed):
            return {
                "type": "text",
                "text": f"failed {action} at ({coord[0]}, {coord[1]})",
            }
        return {
            "type": "text",
            "text": f"{action} at ({coord[0]}, {coord[1]})",
        }

    if action == "hold_key":
        spec = _translate_key_spec(str(params.get("text", "")))
        duration = float(params.get("duration", 1.0))
        if _hold_key(spec, duration):
            return {"type": "text", "text": f"held {spec} for {duration}s"}
        return {"type": "text", "text": f"unsupported key spec: {spec}"}

    if action == "type":
        text = str(params.get("text", ""))
        escaped = gui_actions._escape_applescript_string(text)
        if not gui_actions._run_system_events(f'keystroke "{escaped}"'):
            return {"type": "text", "text": f"failed to type: {text}"}
        return {"type": "text", "text": f"typed: {text}"}

    if action == "key":
        spec = _translate_key_spec(str(params.get("text", "")))
        char, key_code, modifiers = gui_actions._parse_key_spec(spec)
        mod_clause = " using {" + ", ".join(modifiers) + "}" if modifiers else ""
        if char is not None:
            applescript = f'keystroke "{char}"' + mod_clause
        elif key_code is not None:
            applescript = f"key code {key_code}" + mod_clause
        else:
            return {"type": "text", "text": f"unsupported key spec: {spec}"}
        if not gui_actions._run_system_events(applescript):
            return {"type": "text", "text": f"failed to send key: {spec}"}
        return {"type": "text", "text": f"sent key: {spec}"}

    if action == "scroll":
        direction = str(params.get("scroll_direction", "down")).lower()
        amount = int(params.get("scroll_amount", 1))
        if not gui_actions._scroll_via_cgevent(direction, amount):
            return {
                "type": "text",
                "text": f"failed to scroll {direction} {amount} line(s)",
            }
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
        position = _cursor_position()
        if position is None:
            return {"type": "text", "text": "cursor_position unavailable"}
        x, y = position
        origin_x = float(getattr(scale, "origin_x", 0.0))
        origin_y = float(getattr(scale, "origin_y", 0.0))
        return {
            "type": "text",
            "text": f"cursor_position at ({(x - origin_x) / scale}, {(y - origin_y) / scale})",
        }

    return {"type": "text", "text": f"unsupported action: {action}"}
