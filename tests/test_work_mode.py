import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import work_mode  # noqa: E402


class FakePopen:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, cmd, stdout=None, stderr=None, cwd=None):
        if hasattr(stdout, "name"):
            stdout_path = stdout.name
            stdout.close()
        else:
            stdout_path = None
        self.calls.append({"cmd": list(cmd), "stdout": stdout_path, "cwd": cwd})
        return object()


def test_start_task_dispatches_claude_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(work_mode, "SESSIONS_DIR", tmp_path)
    fake = FakePopen()
    monkeypatch.setattr(work_mode.subprocess, "Popen", fake)

    msg = work_mode.start_task("Refactor the auth module")

    assert "dispatched Claude Code" in msg  # nosec B101
    assert len(fake.calls) == 1  # nosec B101
    cmd = fake.calls[0]["cmd"]
    assert cmd[0] == "claude"  # nosec B101
    assert cmd[1] == "-p"  # nosec B101
    assert "Refactor the auth module" in cmd[2]  # nosec B101


def test_start_task_writes_session_file_under_sessions_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(work_mode, "SESSIONS_DIR", tmp_path)
    fake = FakePopen()
    monkeypatch.setattr(work_mode.subprocess, "Popen", fake)

    msg = work_mode.start_task("anything")

    session_id = msg.split("Session ")[1].split(" ")[0]
    out_path = tmp_path / f"{session_id}.txt"
    assert fake.calls[0]["stdout"] == str(out_path)  # nosec B101


def test_get_session_output_missing_session():
    with tempfile.TemporaryDirectory():
        # different SESSIONS_DIR used purposefully — function checks the
        # default location, so we just verify the not-found path.
        result = work_mode.get_session_output("nonexistent-id-xyz")
        assert "not found" in result.lower()  # nosec B101


def test_get_session_output_returns_tail(monkeypatch, tmp_path):
    monkeypatch.setattr(work_mode, "SESSIONS_DIR", tmp_path)
    sid = "abc12345"
    body = "x" * 5000
    (tmp_path / f"{sid}.txt").write_text(body)
    out = work_mode.get_session_output(sid)
    assert len(out) == 2000  # nosec B101
    assert out == body[-2000:]  # nosec B101
