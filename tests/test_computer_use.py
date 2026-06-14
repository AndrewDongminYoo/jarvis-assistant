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
