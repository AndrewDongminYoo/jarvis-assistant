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
