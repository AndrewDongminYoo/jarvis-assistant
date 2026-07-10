import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mail_access  # noqa: E402


def test_send_mail_builds_escaped_applescript(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ok = mail_access.send_mail('anna"quote@example.com', 'hello "there" \\ path')

    assert ok is True  # nosec B101
    args, kwargs = calls[0]
    assert args[:2] == ["osascript", "-e"]  # nosec B101
    script = args[2]
    assert 'address:"anna\\"quote@example.com"' in script  # nosec B101
    assert 'content:"hello \\"there\\" \\\\ path"' in script  # nosec B101
    assert kwargs["timeout"] == mail_access.APPLESCRIPT_TIMEOUT  # nosec B101


def test_send_mail_rejects_empty_recipient_or_body(monkeypatch):
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("subprocess.run must not run for invalid mail")

    monkeypatch.setattr(subprocess, "run", must_not_run)

    assert mail_access.send_mail("", "hello") is False  # nosec B101
    assert mail_access.send_mail("anna@example.com", " ") is False  # nosec B101
