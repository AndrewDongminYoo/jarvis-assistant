import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class FakeRouter:
    """Returns scripted responses one at a time."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, *, task, messages, system, max_tokens):
        self.calls.append({"task": task, "messages": list(messages)})
        return self.responses.pop(0)


def test_action_loop_natural_termination_no_action_tag(monkeypatch):
    fake = FakeRouter(["Just a chat reply."])
    monkeypatch.setattr(server, "_router", fake)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            task="voice",
            max_steps=1,
        )
    )
    assert raw == "Just a chat reply."  # nosec B101
    assert steps == []  # nosec B101
    assert pending is None  # nosec B101


def test_action_loop_runs_one_safe_action(monkeypatch):
    fake = FakeRouter(["Checking. [ACTION:CALENDAR]"])
    monkeypatch.setattr(server, "_router", fake)

    async def fake_dispatch(tag):
        assert tag == "CALENDAR"  # nosec B101
        return "no events today"

    monkeypatch.setattr(server, "dispatch_action", fake_dispatch)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "any meetings?"}],
            system="sys",
            task="voice",
            max_steps=1,
        )
    )
    assert pending is None  # nosec B101
    assert steps == [("CALENDAR", "no events today")]  # nosec B101


def test_action_loop_max_steps_one_stops_after_first_action(monkeypatch):
    fake = FakeRouter(
        [
            "Step 1. [ACTION:CALENDAR]",
            "Step 2. [ACTION:CALENDAR]",  # should NOT be reached at max_steps=1
        ]
    )
    monkeypatch.setattr(server, "_router", fake)

    async def fake_dispatch(tag):
        return "result"

    monkeypatch.setattr(server, "dispatch_action", fake_dispatch)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "x"}],
            system="sys",
            task="voice",
            max_steps=1,
        )
    )
    assert len(steps) == 1  # nosec B101
    assert len(fake.responses) == 1  # one unused — confirms loop stopped  # nosec B101


def test_handle_message_dispatches_safe_action(monkeypatch):
    fake_router = FakeRouter(["Checking. [ACTION:CALENDAR]", "No events today."])
    monkeypatch.setattr(server, "_router", fake_router)

    async def fake_dispatch(tag):
        assert tag == "CALENDAR"  # nosec B101
        return "0 events"

    monkeypatch.setattr(server, "dispatch_action", fake_dispatch)

    async def fake_synth(_):
        return b""

    monkeypatch.setattr(server, "synthesize", fake_synth)

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    ws = FakeWS()
    run(server.handle_message(ws, "any meetings?"))

    types = [m["type"] for m in ws.sent]
    assert "thinking" in types  # nosec B101
    assert "text" in types  # nosec B101
    assert types[-1] == "done"  # nosec B101
    text_msg = next(m for m in ws.sent if m["type"] == "text")
    assert "No events today" in text_msg["content"]  # nosec B101


def test_action_loop_confirm_returns_pending(monkeypatch):
    fake = FakeRouter(["Sending. [ACTION:MAIL:SEND:a@b.com::hi]"])
    monkeypatch.setattr(server, "_router", fake)

    async def must_not_be_called(tag):
        raise AssertionError(f"dispatch should not run for CONFIRM, got {tag}")

    monkeypatch.setattr(server, "dispatch_action", must_not_be_called)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "send mail to a"}],
            system="sys",
            task="voice",
            max_steps=1,
        )
    )
    assert pending is not None  # nosec B101
    assert pending.action == "MAIL:SEND:a@b.com::hi"  # nosec B101
    assert steps == []  # nosec B101


def test_action_loop_blocked_records_step_and_continues(monkeypatch):
    fake = FakeRouter(
        [
            "Running. [ACTION:TERMINAL:sudo rm -rf /]",
            "I'll stop here.",
        ]
    )
    monkeypatch.setattr(server, "_router", fake)

    async def must_not_be_called(tag):
        raise AssertionError("dispatch should not run for BLOCKED")

    monkeypatch.setattr(server, "dispatch_action", must_not_be_called)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "wipe disk"}],
            system="sys",
            task="voice",
            max_steps=2,
        )
    )
    assert pending is None  # nosec B101
    assert len(steps) == 1  # nosec B101
    assert steps[0][0] == "TERMINAL:sudo rm -rf /"  # nosec B101
    assert "blocked" in steps[0][1].lower()  # nosec B101


def test_handle_message_confirm_emits_pending_and_no_dispatch(monkeypatch):
    fake_router = FakeRouter(["Sending. [ACTION:MAIL:SEND:a@b.com::hi]"])
    monkeypatch.setattr(server, "_router", fake_router)

    async def must_not_be_called(_):
        raise AssertionError("dispatch must not run for CONFIRM")

    monkeypatch.setattr(server, "dispatch_action", must_not_be_called)

    async def fake_synth(_):
        return b""

    monkeypatch.setattr(server, "synthesize", fake_synth)

    server._pending.clear()

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    ws = FakeWS()
    run(server.handle_message(ws, "send mail to a"))

    assert len(server._pending) == 1  # nosec B101
    text_msg = next(m for m in ws.sent if m["type"] == "text")
    assert (
        "?" in text_msg["content"] or "proceed" in text_msg["content"].lower()
    )  # nosec B101


def test_handle_message_pending_yes_executes_action(monkeypatch):
    fake_router = FakeRouter(["Mail sent."])  # narrate pass
    monkeypatch.setattr(server, "_router", fake_router)

    called = {}

    async def fake_dispatch(tag):
        called["tag"] = tag
        return "sent"

    monkeypatch.setattr(server, "dispatch_action", fake_dispatch)

    async def fake_synth(_):
        return b""

    monkeypatch.setattr(server, "synthesize", fake_synth)

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    ws = FakeWS()
    server._pending.clear()
    server._pending[server._ws_id(ws)] = server.PendingAction(
        action="MAIL:SEND:a@b.com::hi",
        history=[{"role": "user", "content": "send mail"}],
        asked_at=__import__("time").time(),
    )

    run(server.handle_message(ws, "yes"))

    assert called["tag"] == "MAIL:SEND:a@b.com::hi"  # nosec B101
    assert server._pending == {}  # nosec B101


def test_handle_message_pending_no_cancels(monkeypatch):
    monkeypatch.setattr(server, "_router", FakeRouter([]))

    async def must_not_be_called(_):
        raise AssertionError("dispatch must not run on cancellation")

    monkeypatch.setattr(server, "dispatch_action", must_not_be_called)

    async def fake_synth(_):
        return b""

    monkeypatch.setattr(server, "synthesize", fake_synth)

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    ws = FakeWS()
    server._pending.clear()
    server._pending[server._ws_id(ws)] = server.PendingAction(
        action="MAIL:SEND:a@b.com::hi",
        history=[],
        asked_at=__import__("time").time(),
    )

    run(server.handle_message(ws, "no, cancel"))

    text_msg = next(m for m in ws.sent if m["type"] == "text")
    assert (
        "cancel" in text_msg["content"].lower() or "취소" in text_msg["content"]
    )  # nosec B101
    assert server._pending == {}  # nosec B101


def test_handle_message_pending_expired_falls_through(monkeypatch):
    import time as _time

    fake_router = FakeRouter(["Just chatting."])
    monkeypatch.setattr(server, "_router", fake_router)

    async def must_not_be_called(_):
        raise AssertionError("expired pending must not dispatch")

    monkeypatch.setattr(server, "dispatch_action", must_not_be_called)

    async def fake_synth(_):
        return b""

    monkeypatch.setattr(server, "synthesize", fake_synth)

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    ws = FakeWS()
    server._pending.clear()
    server._pending[server._ws_id(ws)] = server.PendingAction(
        action="MAIL:SEND:a@b.com::hi",
        history=[],
        asked_at=_time.time() - 120.0,
        expires_in=30.0,
    )

    run(server.handle_message(ws, "anyway, what's the weather"))

    assert server._pending == {}  # nosec B101
    text_msg = next(m for m in ws.sent if m["type"] == "text")
    assert "Just chatting" in text_msg["content"]  # nosec B101


def test_action_loop_runs_two_safe_steps(monkeypatch):
    fake = FakeRouter(
        [
            "Focusing. [ACTION:UI:FOCUS:Chrome]",
            "Searching. [ACTION:SEARCH:python asyncio]",
            "Found docs about asyncio.",
        ]
    )
    monkeypatch.setattr(server, "_router", fake)

    async def fake_dispatch(tag):
        return f"ran {tag}"

    monkeypatch.setattr(server, "dispatch_action", fake_dispatch)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "look up asyncio"}],
            system="sys",
            task="voice",
            max_steps=5,
        )
    )
    assert pending is None  # nosec B101
    assert [s[0] for s in steps] == [
        "UI:FOCUS:Chrome",
        "SEARCH:python asyncio",
    ]  # nosec B101
    assert raw == "Found docs about asyncio."  # nosec B101


def test_action_loop_breaks_on_repeated_action(monkeypatch):
    fake = FakeRouter(
        [
            "Looking. [ACTION:CALENDAR]",
            "Looking again. [ACTION:CALENDAR]",
            "Should not be reached.",
        ]
    )
    monkeypatch.setattr(server, "_router", fake)

    calls = []

    async def fake_dispatch(tag):
        calls.append(tag)
        return "0 events"

    monkeypatch.setattr(server, "dispatch_action", fake_dispatch)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "what's on?"}],
            system="sys",
            task="voice",
            max_steps=5,
        )
    )
    assert len(calls) == 1  # second call short-circuited  # nosec B101
    assert len(steps) == 1  # nosec B101
    assert pending is None  # nosec B101
    assert len(fake.responses) == 1  # third response never consumed  # nosec B101
