import asyncio
import base64
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from memory import Memory  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, msg: dict) -> None:
        self.sent.append(msg)


# ---------------------------------------------------------------------------
# _task_type
# ---------------------------------------------------------------------------


def test_task_type_defaults_to_voice():
    assert server._task_type("hello there") == "voice"  # nosec B101


def test_task_type_recognizes_english_work_keywords():
    assert server._task_type("build a CLI") == "work"  # nosec B101
    assert server._task_type("implement OAuth") == "work"  # nosec B101


def test_task_type_recognizes_korean_work_keywords():
    assert server._task_type("CLI 만들어줘") == "work"  # nosec B101
    assert server._task_type("OAuth 구현해줘") == "work"  # nosec B101


def test_task_type_recognizes_plan_keywords():
    assert server._task_type("plan my trip") == "plan"  # nosec B101
    assert server._task_type("여행 계획 짜줘") == "plan"  # nosec B101


# ---------------------------------------------------------------------------
# ACTION_RE
# ---------------------------------------------------------------------------


def test_action_regex_extracts_simple_tag():
    m = server.ACTION_RE.search("Right away. [ACTION:CALENDAR]")
    assert m is not None  # nosec B101
    assert m.group(1) == "CALENDAR"  # nosec B101


def test_action_regex_extracts_tag_with_payload():
    m = server.ACTION_RE.search("[ACTION:NOTES:CREATE:title::body]")
    assert m is not None  # nosec B101
    assert m.group(1) == "NOTES:CREATE:title::body"  # nosec B101


def test_action_regex_ignores_unclosed_tag():
    assert server.ACTION_RE.search("[ACTION:CALENDAR") is None  # nosec B101


def test_action_regex_strips_only_the_tag():
    raw = "Good morning. [ACTION:CALENDAR] Right away."
    spoken = server.ACTION_RE.sub("", raw).strip()
    assert spoken == "Good morning.  Right away."  # nosec B101


# ---------------------------------------------------------------------------
# _send_audio_chunks
# ---------------------------------------------------------------------------


def test_send_audio_chunks_skips_when_audio_is_none():
    ws = FakeWS()
    run(server._send_audio_chunks(ws, None))
    assert ws.sent == []  # nosec B101


def test_send_audio_chunks_sends_single_frame_for_small_audio():
    ws = FakeWS()
    audio = b"x" * 1000
    run(server._send_audio_chunks(ws, audio))
    assert len(ws.sent) == 1  # nosec B101
    assert ws.sent[0]["type"] == "audio"  # nosec B101
    assert base64.b64decode(ws.sent[0]["data"]) == audio  # nosec B101


def test_send_audio_chunks_splits_on_chunk_size():
    ws = FakeWS()
    audio = b"y" * (16384 * 2 + 100)
    run(server._send_audio_chunks(ws, audio))
    assert len(ws.sent) == 3  # nosec B101
    rebuilt = b"".join(base64.b64decode(m["data"]) for m in ws.sent)
    assert rebuilt == audio  # nosec B101


# ---------------------------------------------------------------------------
# dispatch_action — sqlite-backed branches with a temp Memory
# ---------------------------------------------------------------------------


def _swap_in_temp_memory(monkeypatch) -> Memory:
    tmp = tempfile.mkdtemp()
    mem = Memory(db_path=Path(tmp) / "test.db")
    monkeypatch.setattr(server, "_mem", mem)
    return mem


def test_dispatch_remember_persists_fact(monkeypatch):
    mem = _swap_in_temp_memory(monkeypatch)
    result = run(server.dispatch_action("REMEMBER:user prefers metric"))
    assert "Remembered" in result  # nosec B101
    facts = mem.list_facts()
    assert len(facts) == 1  # nosec B101
    assert facts[0]["fact"] == "user prefers metric"  # nosec B101


def test_dispatch_forget_removes_fact(monkeypatch):
    mem = _swap_in_temp_memory(monkeypatch)
    fact_id = mem.add_fact("temporary")
    result = run(server.dispatch_action(f"FORGET:{fact_id}"))
    assert result == "Fact forgotten."  # nosec B101
    assert mem.list_facts() == []  # nosec B101


def test_dispatch_forget_handles_invalid_id(monkeypatch):
    _swap_in_temp_memory(monkeypatch)
    result = run(server.dispatch_action("FORGET:not-a-number"))
    assert "Invalid" in result  # nosec B101


def test_dispatch_recall_returns_matches(monkeypatch):
    mem = _swap_in_temp_memory(monkeypatch)
    mem.add_exchange("user", "remind me about Tokyo trip")
    mem.add_exchange("assistant", "noted")
    result = run(server.dispatch_action("RECALL:Tokyo"))
    assert "Tokyo" in result  # nosec B101


def test_dispatch_recall_returns_empty_message_when_no_hits(monkeypatch):
    _swap_in_temp_memory(monkeypatch)
    result = run(server.dispatch_action("RECALL:nonexistent"))
    assert "No prior conversation" in result  # nosec B101


def test_dispatch_task_create_then_list(monkeypatch):
    _swap_in_temp_memory(monkeypatch)
    create = run(server.dispatch_action("TASK:CREATE:buy groceries"))
    assert "buy groceries" in create  # nosec B101
    listing = run(server.dispatch_action("TASK:LIST"))
    assert "buy groceries" in listing  # nosec B101


def test_dispatch_task_done_marks_completed(monkeypatch):
    mem = _swap_in_temp_memory(monkeypatch)
    create = run(server.dispatch_action("TASK:CREATE:write report"))
    task_id = int(create.split("#")[1].split(" ")[0])
    done = run(server.dispatch_action(f"TASK:DONE:{task_id}"))
    assert "marked done" in done  # nosec B101
    pending = mem.list_tasks("pending")
    assert pending == []  # nosec B101


def test_dispatch_unknown_action_returns_message():
    result = run(server.dispatch_action("MYSTERY"))
    assert "Unknown action" in result  # nosec B101


def test_dispatch_plan_answer_rejects_missing_separator(monkeypatch):
    _swap_in_temp_memory(monkeypatch)
    result = run(server.dispatch_action("PLAN_ANSWER:just-task-no-answers"))
    assert "::" in result  # nosec B101


def test_dispatch_action_routes_ui_focus(monkeypatch):
    import gui_actions

    called = {}

    def fake_focus(name):
        called["name"] = name
        return "Focused Chrome."

    monkeypatch.setattr(gui_actions, "focus_app", fake_focus)
    result = run(server.dispatch_action("UI:FOCUS:Chrome"))
    assert called["name"] == "Chrome"  # nosec B101
    assert result == "Focused Chrome."  # nosec B101


def test_dispatch_action_routes_ui_observe(monkeypatch):
    import gui_actions

    monkeypatch.setattr(
        gui_actions,
        "observe_frontmost",
        lambda: 'window "Inbox"\n  button "Send"',
    )
    result = run(server.dispatch_action("UI:OBSERVE"))
    assert "Inbox" in result and "Send" in result  # nosec B101


def test_dispatch_action_unknown_ui_subkind_returns_message():
    result = run(server.dispatch_action("UI:WHATEVER"))
    assert "Unknown UI action" in result  # nosec B101


def test_system_prompt_mentions_ui_focus_and_ui_observe():
    prompt = server._build_system_prompt()
    assert "UI:FOCUS" in prompt  # nosec B101
    assert "UI:OBSERVE" in prompt  # nosec B101


def test_system_prompt_embeds_current_local_time(monkeypatch):
    """The prompt must anchor today's date so relative phrases like
    "내일" / "tomorrow" resolve against the host clock, not the model's
    training-cutoff default.
    """
    fake_label = "Tuesday, May 12, 2026 08:42 KST"
    monkeypatch.setattr(server, "_now_local_label", lambda: fake_label)
    prompt = server._build_system_prompt()
    assert fake_label in prompt  # nosec B101
    assert "Anchor every relative date" in prompt  # nosec B101


def test_now_local_label_uses_host_timezone():
    """Smoke check: the label includes a four-digit year and a weekday name.
    We don't pin the exact value because the host clock changes; we just
    verify the formatting contract.
    """
    import re as _re

    label = server._now_local_label()
    assert _re.search(r"\b20\d{2}\b", label), label  # year  # nosec B101
    assert _re.search(  # weekday  # nosec B101
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),",
        label,
    ), label


def test_dispatch_action_routes_ui_click(monkeypatch):
    import gui_actions

    called = {}

    def fake_click(role, label):
        called["args"] = (role, label)
        return "Clicked button: Send."

    monkeypatch.setattr(gui_actions, "click_element", fake_click)
    result = run(server.dispatch_action("UI:CLICK:button::Send"))
    assert called["args"] == ("button", "Send")  # nosec B101
    assert "Clicked" in result  # nosec B101


def test_dispatch_action_routes_ui_type(monkeypatch):
    import gui_actions

    called = {}

    def fake_type(text):
        called["text"] = text
        return f"Typed: {text}"

    monkeypatch.setattr(gui_actions, "type_text", fake_type)
    result = run(server.dispatch_action("UI:TYPE:hello world"))
    assert called["text"] == "hello world"  # nosec B101
    assert "hello world" in result  # nosec B101


def test_dispatch_action_routes_ui_key(monkeypatch):
    import gui_actions

    called = {}

    def fake_key(spec):
        called["spec"] = spec
        return f"Sent {spec}."

    monkeypatch.setattr(gui_actions, "send_key", fake_key)
    result = run(server.dispatch_action("UI:KEY:cmd+t"))
    assert called["spec"] == "cmd+t"  # nosec B101
    assert "cmd+t" in result  # nosec B101


def test_dispatch_action_routes_ui_scroll(monkeypatch):
    import gui_actions

    called = {}

    def fake_scroll(direction, amount):
        called["args"] = (direction, amount)
        return f"Scrolled {direction} {amount} line(s)."

    monkeypatch.setattr(gui_actions, "scroll", fake_scroll)
    result = run(server.dispatch_action("UI:SCROLL:down::3"))
    assert called["args"] == ("down", 3)  # nosec B101
    assert "Scrolled" in result  # nosec B101


def test_dispatch_action_ui_scroll_non_numeric_amount_errors():
    result = run(server.dispatch_action("UI:SCROLL:down::abc"))
    assert "amount" in result.lower() or "integer" in result.lower()  # nosec B101


def test_dispatch_action_ui_click_missing_separator_errors():
    """UI:CLICK requires role::label; a missing :: should be rejected with a
    clear message rather than dispatched with empty label."""
    result = run(server.dispatch_action("UI:CLICK:onlyrole"))
    assert "::" in result or "label" in result.lower()  # nosec B101


def test_dispatch_action_ui_click_empty_label_rejected_before_dispatch(monkeypatch):
    """UI:CLICK:button:: would otherwise dispatch click_element with an empty
    label, which matches every element via substring containment and lets a
    malformed model output fire on an arbitrary button (potentially a risky
    one like Send/Delete that safety.classify would have escalated to
    CONFIRM if the label had been present)."""
    import gui_actions

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("click_element must not run for empty label")

    monkeypatch.setattr(gui_actions, "click_element", must_not_run)
    result = run(server.dispatch_action("UI:CLICK:button::"))
    assert "non-empty" in result.lower() or "needs" in result.lower()  # nosec B101


def test_dispatch_action_ui_click_empty_role_rejected_before_dispatch(monkeypatch):
    import gui_actions

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("click_element must not run for empty role")

    monkeypatch.setattr(gui_actions, "click_element", must_not_run)
    result = run(server.dispatch_action("UI:CLICK:::Send"))
    assert "non-empty" in result.lower() or "needs" in result.lower()  # nosec B101


def test_system_prompt_mentions_all_phase_5_tags():
    prompt = server._build_system_prompt()
    for tag in ("UI:CLICK", "UI:TYPE", "UI:KEY", "UI:SCROLL"):
        assert tag in prompt, tag  # nosec B101
