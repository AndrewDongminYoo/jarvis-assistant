import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import actions  # noqa: E402


class FakeSubprocess:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.calls: list[list[str]] = []

    def run(self, args, capture_output=True, text=True, timeout=None):
        self.calls.append(list(args))
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout)


def _patch(monkeypatch, returncode=0, stdout=""):
    fake = FakeSubprocess(returncode=returncode, stdout=stdout)
    monkeypatch.setattr(actions.subprocess, "run", fake.run)
    return fake


def test_open_terminal_without_command_activates_app(monkeypatch):
    fake = _patch(monkeypatch)
    assert actions.open_terminal("") is True  # nosec B101
    assert fake.calls[0][:2] == ["osascript", "-e"]  # nosec B101
    assert 'tell app "Terminal" to activate' == fake.calls[0][2]  # nosec B101


def test_open_terminal_with_command_runs_do_script(monkeypatch):
    fake = _patch(monkeypatch)
    actions.open_terminal("ls -la")
    script = fake.calls[0][2]
    assert 'do script "ls -la"' in script  # nosec B101


def test_open_terminal_escapes_double_quotes(monkeypatch):
    fake = _patch(monkeypatch)
    actions.open_terminal('echo "hi"')
    script = fake.calls[0][2]
    assert 'echo \\"hi\\"' in script  # nosec B101


def test_open_chrome_with_url_uses_open_location(monkeypatch):
    fake = _patch(monkeypatch)
    actions.open_chrome("https://example.com")
    assert 'open location "https://example.com"' == fake.calls[0][2]  # nosec B101


def test_open_chrome_without_url_activates_chrome(monkeypatch):
    fake = _patch(monkeypatch)
    actions.open_chrome("")
    assert (  # nosec B101
        'tell application "Google Chrome" to activate' == fake.calls[0][2]
    )


def test_show_notification_escapes_quotes(monkeypatch):
    fake = _patch(monkeypatch)
    actions.show_notification('Hi "you"', 'msg "body"')
    script = fake.calls[0][2]
    assert 'with title "Hi \\"you\\""' in script  # nosec B101
    assert 'display notification "msg \\"body\\""' in script  # nosec B101


def test_osascript_returns_false_on_nonzero_exit(monkeypatch):
    _patch(monkeypatch, returncode=1)
    assert actions.open_terminal("") is False  # nosec B101


def test_osascript_uses_module_timeout_constant(monkeypatch):
    captured: dict = {}

    def fake_run(args, capture_output=True, text=True, timeout=None):
        captured["timeout"] = timeout
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(actions.subprocess, "run", fake_run)
    actions.open_terminal("")
    assert captured["timeout"] == actions.APPLESCRIPT_TIMEOUT  # nosec B101
