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

    async def fake_dispatch(tag, *args, **kwargs):
        assert tag == "CALENDAR"  # nosec B101
        return server.ActionResult("no events today")

    monkeypatch.setattr(server, "_dispatch_action_result", fake_dispatch)

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

    async def fake_dispatch(tag, *args, **kwargs):
        return server.ActionResult("result")

    monkeypatch.setattr(server, "_dispatch_action_result", fake_dispatch)

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
    # max_steps=5 means the action loop may call the LLM multiple times:
    # 1. First call returns action → execute → loop again
    # 2. Second call returns no action → loop terminates
    # 3. Narration call to summarize the result
    fake_router = FakeRouter(["Checking. [ACTION:CALENDAR]", "OK.", "No events today."])
    monkeypatch.setattr(server, "_router", fake_router)

    async def fake_dispatch(tag, *args, **kwargs):
        assert tag == "CALENDAR"  # nosec B101
        return server.ActionResult("0 events")

    monkeypatch.setattr(server, "_dispatch_action_result", fake_dispatch)

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


def test_handle_message_emits_step_after_safe_action(monkeypatch):
    fake_router = FakeRouter(["Checking. [ACTION:CALENDAR]", "OK.", "No events today."])
    monkeypatch.setattr(server, "_router", fake_router)

    async def fake_dispatch(tag, *args, **kwargs):
        assert tag == "CALENDAR"  # nosec B101
        return server.ActionResult("0 events")

    monkeypatch.setattr(server, "_dispatch_action_result", fake_dispatch)

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
    assert types[:2] == ["thinking", "step"]  # nosec B101
    step_msg = next(m for m in ws.sent if m["type"] == "step")
    assert step_msg == {  # nosec B101
        "type": "step",
        "kind": "CALENDAR",
        "summary": "CALENDAR completed.",
    }


def test_handle_message_emits_failed_step_for_validation_result(monkeypatch):
    fake_router = FakeRouter(["Trying. [ACTION:UI:CLICK:onlyrole]", "Understood."])
    monkeypatch.setattr(server, "_router", fake_router)

    async def fake_synth(_):
        return b""

    monkeypatch.setattr(server, "synthesize", fake_synth)

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    ws = FakeWS()
    run(server.handle_message(ws, "click it"))

    step_msg = next(m for m in ws.sent if m["type"] == "step")
    assert step_msg == {  # nosec B101
        "type": "step",
        "kind": "UI:CLICK",
        "summary": "UI:CLICK failed.",
    }


def test_handle_message_emits_failed_step_for_empty_recall(monkeypatch):
    fake_router = FakeRouter(["Trying. [ACTION:RECALL:]", "Understood."])
    monkeypatch.setattr(server, "_router", fake_router)

    async def fake_synth(_):
        return b""

    monkeypatch.setattr(server, "synthesize", fake_synth)

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    ws = FakeWS()
    run(server.handle_message(ws, "recall nothing"))

    step_msg = next(m for m in ws.sent if m["type"] == "step")
    assert step_msg == {  # nosec B101
        "type": "step",
        "kind": "RECALL",
        "summary": "RECALL failed.",
    }


def test_handle_message_confirmed_computer_emits_internal_tool_step(monkeypatch):
    import time as _time

    import computer_use

    fake_router = FakeRouter(["Computer work finished."])
    monkeypatch.setattr(server, "_router", fake_router)

    def fake_run(goal, progress_callback=None, display_id=None):
        assert goal == "click the visible button"  # nosec B101
        assert progress_callback is not None  # nosec B101
        progress_callback(
            {"action": "left_click", "coordinate": [10, 20]},
            {"type": "text", "text": "left_click at (10, 20)"},
        )
        return "Clicked it."

    monkeypatch.setattr(computer_use, "run_computer_goal", fake_run)

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
        action="COMPUTER:click the visible button",
        history=[],
        asked_at=_time.time(),
    )

    run(server.handle_message(ws, "yes"))

    steps = [m for m in ws.sent if m["type"] == "step"]
    assert len(steps) == 2  # nosec B101
    assert steps[0]["kind"] == "COMPUTER"  # nosec B101
    assert "left_click" in steps[0]["summary"]  # nosec B101
    assert steps[1] == {  # nosec B101
        "type": "step",
        "kind": "COMPUTER",
        "summary": "COMPUTER completed.",
    }


def test_action_loop_reuses_observe_snapshot_for_followup_click(monkeypatch):
    import gui_actions

    fake = FakeRouter(
        [
            "Observing. [ACTION:UI:OBSERVE]",
            "Clicking. [ACTION:UI:CLICK:button::Open]",
            "Done.",
        ]
    )
    monkeypatch.setattr(server, "_router", fake)
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)

    root = {
        "role": "AXWindow",
        "children": [{"role": "AXButton", "title": "Open"}],
    }
    frontmost_calls = []

    def fake_frontmost_app():
        frontmost_calls.append("called")
        if len(frontmost_calls) > 1:
            raise AssertionError("cached click should not call _frontmost_app again")
        return {"name": "Finder", "pid": 42, "root": root}

    monkeypatch.setattr(gui_actions, "_frontmost_app", fake_frontmost_app)
    monkeypatch.setattr(gui_actions, "_frontmost_app_identity", lambda: ("Finder", 42))
    monkeypatch.setattr(gui_actions, "_press_via_ax", lambda _element: True)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "open it"}],
            system="sys",
            task="voice",
            max_steps=5,
        )
    )

    assert raw == "Done."  # nosec B101
    assert pending is None  # nosec B101
    assert [step[0] for step in steps] == [  # nosec B101
        "UI:OBSERVE",
        "UI:CLICK:button::Open",
    ]
    # Single frontmost lookup proves the follow-up CLICK reused the OBSERVE
    # snapshot instead of walking the AX tree again.
    assert frontmost_calls == ["called"]  # nosec B101


def test_observe_snapshot_does_not_leak_across_action_loops(monkeypatch):
    """The blocker fix: the OBSERVE cache is a per-loop local, so a CLICK in a
    SEPARATE loop turn never reuses a prior turn's snapshot."""
    import gui_actions

    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    root = {
        "role": "AXWindow",
        "children": [{"role": "AXButton", "title": "Open"}],
    }
    frontmost_calls = []

    def fake_frontmost_app():
        frontmost_calls.append("called")
        return {"name": "Finder", "pid": 42, "root": root}

    monkeypatch.setattr(gui_actions, "_frontmost_app", fake_frontmost_app)
    monkeypatch.setattr(gui_actions, "_frontmost_app_identity", lambda: ("Finder", 42))
    monkeypatch.setattr(gui_actions, "_press_via_ax", lambda _element: True)

    # Turn 1: OBSERVE only — populates that loop's local cache, which then dies.
    monkeypatch.setattr(
        server, "_router", FakeRouter(["Observing. [ACTION:UI:OBSERVE]", "Done."])
    )
    run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "look"}],
            system="sys",
            task="voice",
            max_steps=5,
        )
    )
    assert frontmost_calls == ["called"]  # nosec B101

    # Turn 2: CLICK only — a fresh loop, so it must do its own frontmost lookup.
    monkeypatch.setattr(
        server,
        "_router",
        FakeRouter(["Clicking. [ACTION:UI:CLICK:button::Open]", "Done."]),
    )
    run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "open it"}],
            system="sys",
            task="voice",
            max_steps=5,
        )
    )
    assert frontmost_calls == ["called", "called"]  # nosec B101


def test_intervening_action_clears_observe_snapshot(monkeypatch):
    """OBSERVE -> FOCUS -> CLICK: the intervening FOCUS drops the snapshot, so
    the CLICK re-fetches the frontmost app rather than reusing a stale root."""
    import gui_actions

    fake = FakeRouter(
        [
            "Observing. [ACTION:UI:OBSERVE]",
            "Focusing. [ACTION:UI:FOCUS:Finder]",
            "Clicking. [ACTION:UI:CLICK:button::Open]",
            "Done.",
        ]
    )
    monkeypatch.setattr(server, "_router", fake)
    monkeypatch.setattr(gui_actions, "_ax_is_trusted", lambda: True)
    monkeypatch.setattr(gui_actions, "focus_app", lambda name: f"Focused {name}.")

    root = {
        "role": "AXWindow",
        "children": [{"role": "AXButton", "title": "Open"}],
    }
    frontmost_calls = []

    def fake_frontmost_app():
        frontmost_calls.append("called")
        return {"name": "Finder", "pid": 42, "root": root}

    monkeypatch.setattr(gui_actions, "_frontmost_app", fake_frontmost_app)
    monkeypatch.setattr(gui_actions, "_frontmost_app_identity", lambda: ("Finder", 42))
    monkeypatch.setattr(gui_actions, "_press_via_ax", lambda _element: True)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "open it"}],
            system="sys",
            task="voice",
            max_steps=5,
        )
    )

    assert [step[0] for step in steps] == [  # nosec B101
        "UI:OBSERVE",
        "UI:FOCUS:Finder",
        "UI:CLICK:button::Open",
    ]
    # Two frontmost lookups: one for OBSERVE, one for the CLICK that could not
    # reuse the snapshot the FOCUS cleared.
    assert frontmost_calls == ["called", "called"]  # nosec B101


def test_action_results_mark_validation_failures():
    results = [
        run(server._dispatch_action_result("TASK:CREATE:")),
        run(server._dispatch_action_result("TASK:DONE:not-number")),
        run(server._dispatch_action_result("MAIL:SEND:a@b.com")),
    ]

    assert [r.status for r in results] == ["failed", "failed", "failed"]  # nosec B101


def test_action_result_marks_search_provider_error(monkeypatch):
    import browser

    async def fake_search(_query):
        return [{"title": "Error", "url": "", "snippet": "timeout"}]

    monkeypatch.setattr(browser, "search_web", fake_search)

    result = run(server._dispatch_action_result("SEARCH:asyncio"))

    assert result.status == "failed"  # nosec B101
    assert "timeout" in result.text  # nosec B101


def test_action_loop_confirm_returns_pending(monkeypatch):
    fake = FakeRouter(["Sending. [ACTION:MAIL:SEND:a@b.com::hi]"])
    monkeypatch.setattr(server, "_router", fake)

    async def must_not_be_called(tag):
        raise AssertionError(f"dispatch should not run for CONFIRM, got {tag}")

    monkeypatch.setattr(server, "_dispatch_action_result", must_not_be_called)

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

    monkeypatch.setattr(server, "_dispatch_action_result", must_not_be_called)

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

    monkeypatch.setattr(server, "_dispatch_action_result", must_not_be_called)

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

    async def fake_dispatch(tag, *args, **kwargs):
        called["tag"] = tag
        return server.ActionResult("sent")

    monkeypatch.setattr(server, "_dispatch_action_result", fake_dispatch)

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
    step_msg = next(m for m in ws.sent if m["type"] == "step")
    assert step_msg == {  # nosec B101
        "type": "step",
        "kind": "MAIL",
        "summary": "MAIL completed.",
    }
    assert server._pending == {}  # nosec B101


def test_handle_message_pending_no_cancels(monkeypatch):
    monkeypatch.setattr(server, "_router", FakeRouter([]))

    async def must_not_be_called(_):
        raise AssertionError("dispatch must not run on cancellation")

    monkeypatch.setattr(server, "_dispatch_action_result", must_not_be_called)

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


def test_handle_message_ambiguous_confirmation_retains_pending(monkeypatch):
    import time as _time

    fake_router = FakeRouter(["must not be consumed"])
    monkeypatch.setattr(server, "_router", fake_router)

    async def must_not_dispatch(*_args, **_kwargs):
        raise AssertionError("ambiguous confirmation must not dispatch")

    monkeypatch.setattr(server, "_dispatch_action_result", must_not_dispatch)

    async def fake_synth(_):
        return b""

    monkeypatch.setattr(server, "synthesize", fake_synth)

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    ws = FakeWS()
    pending = server.PendingAction(
        action="MAIL:SEND:a@b.com::hi",
        history=[],
        asked_at=_time.time(),
    )
    connection_id = "ambiguous-confirmation"
    server._pending.clear()
    server._pending[connection_id] = pending

    run(server.handle_message(ws, "I need to go now", connection_id))

    assert fake_router.calls == []  # nosec B101
    assert server._pending[connection_id] is pending  # nosec B101
    assert server._pending[connection_id].asked_at == pending.asked_at  # nosec B101
    text_msg = next(msg for msg in ws.sent if msg["type"] == "text")
    assert "yes or no" in text_msg["content"].lower()  # nosec B101
    assert ws.sent[-1] == {"type": "done"}  # nosec B101


def test_handle_message_pending_expired_falls_through(monkeypatch):
    import time as _time

    fake_router = FakeRouter(["Just chatting."])
    monkeypatch.setattr(server, "_router", fake_router)

    async def must_not_be_called(_):
        raise AssertionError("expired pending must not dispatch")

    monkeypatch.setattr(server, "_dispatch_action_result", must_not_be_called)

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

    async def fake_dispatch(tag, *args, **kwargs):
        return server.ActionResult(f"ran {tag}")

    monkeypatch.setattr(server, "_dispatch_action_result", fake_dispatch)

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

    async def fake_dispatch(tag, *args, **kwargs):
        calls.append(tag)
        return server.ActionResult("0 events")

    monkeypatch.setattr(server, "_dispatch_action_result", fake_dispatch)

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


def test_action_loop_stops_at_max_steps(monkeypatch):
    fake = FakeRouter(
        [
            "Step A. [ACTION:UI:OBSERVE]",
            "Step B. [ACTION:UI:FOCUS:Chrome]",
            "Step C. [ACTION:SEARCH:python]",
            "Should not run.",
        ]
    )
    monkeypatch.setattr(server, "_router", fake)

    async def fake_dispatch(tag, *args, **kwargs):
        return server.ActionResult(f"ran {tag}")

    monkeypatch.setattr(server, "_dispatch_action_result", fake_dispatch)

    raw, steps, pending = run(
        server._run_action_loop(
            messages=[{"role": "user", "content": "do three things"}],
            system="sys",
            task="voice",
            max_steps=3,
        )
    )
    assert pending is None  # nosec B101
    assert len(steps) == 3  # nosec B101
    assert len(fake.responses) == 1  # fourth never consumed  # nosec B101


def test_handle_message_pending_conflicting_reply_cancels(monkeypatch):
    """When the reply matches BOTH detectors (e.g. "no go", "yes, cancel"),
    cancel wins. Erring toward cancellation is the safer default for risky
    actions.
    """
    import time as _time

    monkeypatch.setattr(server, "_router", FakeRouter([]))

    async def must_not_be_called(_):
        raise AssertionError("conflicting reply must not dispatch")

    monkeypatch.setattr(server, "_dispatch_action_result", must_not_be_called)

    async def fake_synth(_):
        return b""

    monkeypatch.setattr(server, "synthesize", fake_synth)

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    for reply in ("no go", "yes, cancel that", "그래 취소"):
        ws = FakeWS()
        server._pending.clear()
        server._pending[server._ws_id(ws)] = server.PendingAction(
            action="TERMINAL:rm important.txt",
            history=[],
            asked_at=_time.time(),
        )

        run(server.handle_message(ws, reply))

        assert server._pending == {}, reply  # nosec B101
        text_msg = next(m for m in ws.sent if m["type"] == "text")
        assert (
            "cancel" in text_msg["content"].lower() or "취소" in text_msg["content"]
        ), reply  # nosec B101
