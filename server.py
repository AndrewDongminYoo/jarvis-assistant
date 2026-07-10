# JARVIS — Built from CLAUDE.md by Taoufik · instagram.com/taoufik.ai
"""JARVIS FastAPI voice assistant server."""

import asyncio
import base64
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from llm_router import LLMRouter
from memory import Memory

load_dotenv()
log = logging.getLogger("jarvis")
logging.basicConfig(level=logging.INFO)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEFAULT_ELEVENLABS_VOICE_ID = "UgBBYS2sOqTuMpoF3BR0"  # George
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE_ID)
USER_NAME = (
    os.getenv("USER_NAME", "sir").split(",")[0].strip()
)  # "Dongmin,Yu" -> "Dongmin"
PORT = int(os.getenv("PORT", "8340"))
SSL_CERT = Path("cert.pem")
SSL_KEY = Path("key.pem")

_router = LLMRouter.from_env()
_mem = Memory()


# ---------------------------------------------------------------------------
# Pending Actions
# ---------------------------------------------------------------------------


@dataclass
class PendingAction:
    action: str
    history: list[dict]
    asked_at: float
    expires_in: float = 30.0

    def expired(self) -> bool:
        return time.time() - self.asked_at > self.expires_in


_pending: dict[str, PendingAction] = {}


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------


def _now_local_label() -> str:
    """Return today's date and time in the server's local timezone, formatted
    for the LLM system prompt. Anchored on the host clock (KST for the user)
    so relative phrases like '내일' / 'tomorrow' resolve against the right
    day instead of the model's training-cutoff default.
    """
    now = datetime.now().astimezone()
    return now.strftime("%A, %B %d, %Y %H:%M %Z")


def _build_system_prompt() -> str:
    facts = _mem.facts_as_context()
    name = USER_NAME if USER_NAME and USER_NAME.lower() != "sir" else "sir"
    facts_block = f"\n\n{facts}" if facts else ""
    now_label = _now_local_label()
    return f"""You are JARVIS, a British AI butler assistant running on macOS.

The current local time is {now_label}. Anchor every relative date or time
phrase (today, tomorrow, 내일, 오늘, "this Friday", etc.) against this
timestamp, not against your training-cutoff default.

Personality: Precise, dry wit, subtly sardonic, unwaveringly helpful. British vocabulary.
Voice: Concise — max 2-3 sentences. No markdown. You are speaking aloud.
Address the user as '{name}'.
Respond in the user's language. Mix Korean and English naturally — like a bilingual speaker would. 사용자가 한국어로 말하면 한국어로, 영어면 영어로, 혼용하면 자연스럽게 혼용하여 답하세요.

Embed ONE action tag per response when system access is needed:
  [ACTION:CALENDAR]                      — upcoming calendar events
  [ACTION:MAIL]                          — unread mail summary
  [ACTION:MAIL:SEARCH:query]             — search mail
  [ACTION:MAIL:SEND:recipient::body]     — send an email after user confirmation
  [ACTION:NOTES:LIST]                    — list note titles
  [ACTION:NOTES:READ:title]              — read a note
  [ACTION:NOTES:CREATE:title::content]   — create a note
  [ACTION:TERMINAL:command]              — run shell command in Terminal
  [ACTION:BROWSE:url]                    — browse a URL
  [ACTION:SEARCH:query]                  — web search
  [ACTION:WORK:task]                     — dispatch to Claude Code
  [ACTION:PLAN:description]              — start a planning session with clarifying questions
  [ACTION:PLAN_ANSWER:task::answers]     — produce the numbered plan once user has answered
  [ACTION:UI:FOCUS:app_name]             — activate an app (Chrome, Slack, Mail…)
  [ACTION:UI:OBSERVE]                    — read the frontmost app's UI
  [ACTION:UI:CLICK:role::label]          — click a tier-A element by its OBSERVE role/label
  [ACTION:UI:TYPE:text]                  — type the given text into the focused field
  [ACTION:UI:KEY:cmd+t]                  — send a keystroke (cmd/shift/alt/ctrl + char or named key)
  [ACTION:UI:SCROLL:direction::amount]   — scroll the frontmost window (direction: up|down|left|right, amount: lines)
  [ACTION:COMPUTER:goal]                 — vision-grounded fallback (Anthropic Computer Use); use only when UI:* can't reach the target. Prefix goal with @N to target display N (1 = main), e.g. [ACTION:COMPUTER:@2 click Export]
  [ACTION:REMEMBER:fact]                 — remember a user fact
  [ACTION:FORGET:fact_id]               — forget a stored fact
  [ACTION:RECALL:query]                  — search prior conversation
  [ACTION:TASK:CREATE:title]             — add a pending task
  [ACTION:TASK:LIST]                     — list pending tasks
  [ACTION:TASK:DONE:task_id]             — mark a task as done

Prefer UI:OBSERVE before acting on UI. The click target's role/label come from the OBSERVE output's vocabulary. Reach for COMPUTER only when the app doesn't expose AX (Figma canvases, web embeds, games) — it is slower and costlier than UI:* and runs the screen, so reserve it for genuine fallbacks.
{facts_block}
"""


# ---------------------------------------------------------------------------
# TTS Pipeline
# ---------------------------------------------------------------------------


async def _tts_elevenlabs(text: str) -> Optional[bytes]:
    if not ELEVENLABS_API_KEY:
        return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as c:
        try:
            r = await c.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.content
        except Exception as e:
            log.warning("ElevenLabs TTS error: %s", e)
            return None


def _detect_lang(text: str) -> str:
    return "ko" if any("가" <= char <= "힣" for char in text) else "en"


def _tts_macos(text: str) -> None:
    import subprocess

    voice = "Yuna" if _detect_lang(text) == "ko" else "Daniel"
    subprocess.run(["say", "-v", voice, text], timeout=60)


async def synthesize(text: str) -> Optional[bytes]:
    audio = await _tts_elevenlabs(text)
    if audio:
        return audio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _tts_macos, text)
    return None


async def _send_audio_chunks(ws: WebSocket, audio: Optional[bytes]) -> None:
    if not audio:
        return
    chunk_size = 16384
    for i in range(0, len(audio), chunk_size):
        encoded = base64.b64encode(audio[i : i + chunk_size]).decode()
        await ws.send_json({"type": "audio", "data": encoded})


# ---------------------------------------------------------------------------
# Action Tag Parser
# ---------------------------------------------------------------------------

ACTION_RE = re.compile(r"\[ACTION:([^\]]+)\]")
MAX_STEPS = 5


@dataclass(frozen=True)
class ActionResult:
    text: str
    status: Literal["completed", "failed", "blocked"] = "completed"


StepCallback = Callable[[str, ActionResult], Awaitable[None]]
ComputerProgressCallback = Callable[[dict, dict], None]


def _step_kind(tag: str) -> str:
    head, _, tail = tag.partition(":")
    if head.upper() == "UI" and tail:
        sub, _, _rest = tail.partition(":")
        return f"UI:{sub.upper()}"
    return head.upper()


def _step_summary(tag: str, result: ActionResult) -> str:
    if tag.upper().startswith("COMPUTER:TOOL:"):
        return result.text
    kind = _step_kind(tag)
    if result.status == "blocked":
        return f"{kind} blocked."
    if result.status == "failed":
        return f"{kind} failed."
    return f"{kind} completed."


def _computer_progress_result(params: dict, outcome: dict) -> tuple[str, ActionResult]:
    action = str(params.get("action") or "tool")
    text = str(outcome.get("text") or f"{action} completed.")
    lowered = text.lower()
    if lowered.startswith("blocked"):
        status: Literal["completed", "failed", "blocked"] = "blocked"
    elif lowered.startswith("failed") or " failed" in lowered:
        status = "failed"
    else:
        status = "completed"
    return (
        f"COMPUTER:TOOL:{action}",
        ActionResult(f"Computer Use {action}: {text}", status=status),
    )


def _computer_progress_callback(
    on_step: StepCallback | None,
) -> ComputerProgressCallback | None:
    if on_step is None:
        return None
    loop = asyncio.get_running_loop()

    def emit(params: dict, outcome: dict) -> None:
        tag, result = _computer_progress_result(params, outcome)
        future = asyncio.run_coroutine_threadsafe(on_step(tag, result), loop)
        try:
            future.result(timeout=5)
        except Exception as e:  # noqa: BLE001
            log.warning("Computer Use step emission failed: %s", e)

    return emit


_COMPUTER_DISPLAY_RE = re.compile(r"^@([1-9]\d*)\s+(.+)$", re.DOTALL)


def _parse_computer_goal(goal: str) -> tuple[str, int | None]:
    """Split an optional leading ``@<n>`` display selector off a COMPUTER goal.

    ``@2 click Export`` → ``("click Export", 2)``, where ``n`` is a 1-based
    display index (1 = main display). A missing or malformed prefix (no digits,
    a leading zero, or a goal that legitimately starts with ``@name``) returns
    ``(goal, None)`` so the action defaults to the main display and ordinary
    goals are left intact.
    """
    m = _COMPUTER_DISPLAY_RE.match(goal.strip())
    if not m:
        return goal.strip(), None
    return m.group(2).strip(), int(m.group(1))


async def dispatch_action(tag: str) -> str:
    return (await _dispatch_action_result(tag)).text


async def _dispatch_action_result(
    tag: str,
    computer_progress_callback: ComputerProgressCallback | None = None,
    ui_context: dict | None = None,
) -> ActionResult:
    parts = tag.split(":", 2)
    kind = parts[0].upper()

    if kind == "CALENDAR":
        from calendar_access import get_events_summary

        return ActionResult(await asyncio.to_thread(get_events_summary))

    if kind == "MAIL":
        sub = parts[1].upper() if len(parts) > 1 else ""
        if not sub:
            from mail_access import get_mail_summary

            return ActionResult(await asyncio.to_thread(get_mail_summary))
        if len(parts) >= 3 and sub == "SEARCH":
            from mail_access import search_mail

            items = await asyncio.to_thread(search_mail, parts[2])
            return ActionResult(
                "\n".join(f"- {i['subject']} from {i['sender']}" for i in items)
                if items
                else "No matching mail found."
            )
        if len(parts) >= 3 and sub == "SEND":
            from mail_access import send_mail

            recipient, sep, body = parts[2].partition("::")
            if not sep:
                return ActionResult("MAIL:SEND needs recipient::body.", status="failed")
            recipient_clean = recipient.strip()
            body_clean = body.strip()
            if not recipient_clean or not body_clean:
                return ActionResult(
                    "MAIL:SEND needs a non-empty recipient and body.",
                    status="failed",
                )
            ok = await asyncio.to_thread(send_mail, recipient_clean, body_clean)
            return ActionResult(
                (f"Mail sent to {recipient_clean}." if ok else "Failed to send mail."),
                status="completed" if ok else "failed",
            )
        return ActionResult(f"Unknown MAIL action: {sub}", status="failed")

    if kind == "NOTES":
        sub = parts[1].upper() if len(parts) > 1 else "LIST"
        if sub == "LIST":
            from notes_access import list_note_titles

            titles = await asyncio.to_thread(list_note_titles)
            return ActionResult(
                ("Your notes: " + ", ".join(titles)) if titles else "No notes found."
            )
        if sub == "READ" and len(parts) > 2:
            from notes_access import read_note

            body = await asyncio.to_thread(read_note, parts[2])
            if body:
                return ActionResult(body)
            return ActionResult(f"Note '{parts[2]}' not found.", status="failed")
        if sub == "CREATE" and len(parts) > 2:
            from notes_access import create_note

            title, _, content = parts[2].partition("::")
            ok = await asyncio.to_thread(create_note, title.strip(), content.strip())
            return ActionResult(
                f"Note '{title.strip()}' created." if ok else "Failed to create note.",
                status="completed" if ok else "failed",
            )

    if kind == "TERMINAL":
        from actions import open_terminal

        cmd = parts[1] if len(parts) > 1 else ""
        await asyncio.to_thread(open_terminal, cmd)
        return ActionResult(f"Terminal opened{': ' + cmd if cmd else ''}.")

    if kind == "BROWSE":
        from browser import browse_url

        text = await browse_url(parts[1] if len(parts) > 1 else "")
        return ActionResult(
            text,
            status="failed" if text.startswith("Failed to load ") else "completed",
        )

    if kind == "SEARCH":
        from browser import format_search_results, search_results_failed, search_web

        query = ":".join(parts[1:])
        results = await search_web(query)
        return ActionResult(
            format_search_results(query, results),
            status="failed" if search_results_failed(results) else "completed",
        )

    if kind == "WORK":
        from work_mode import start_task

        return ActionResult(start_task(":".join(parts[1:])))

    if kind == "PLAN":
        from planner import get_clarifying_questions

        return ActionResult(await get_clarifying_questions(":".join(parts[1:])))

    if kind == "PLAN_ANSWER":
        from planner import generate_plan

        payload = ":".join(parts[1:])
        task, sep, answers = payload.partition("::")
        if not sep or not task.strip() or not answers.strip():
            return ActionResult(
                "Plan answer needs both task and answers separated by '::'.",
                status="failed",
            )
        return ActionResult(await generate_plan(task.strip(), answers.strip()))

    if kind == "REMEMBER":
        fact = ":".join(parts[1:])
        await asyncio.to_thread(_mem.add_fact, fact)
        return ActionResult(f"Remembered: {fact}")

    if kind == "FORGET":
        try:
            await asyncio.to_thread(_mem.delete_fact, int(parts[1]))
            return ActionResult("Fact forgotten.")
        except (ValueError, IndexError):
            return ActionResult("Invalid fact ID.", status="failed")

    if kind == "RECALL":
        query = ":".join(parts[1:]).strip()
        if not query:
            return ActionResult("Recall query was empty.", status="failed")
        hits = await asyncio.to_thread(_mem.search, query)
        if not hits:
            return ActionResult(f"No prior conversation matches '{query}'.")
        lines = [f"- ({h['role']}) {h['content']}" for h in hits[:5]]
        return ActionResult("Recalled exchanges:\n" + "\n".join(lines))

    if kind == "TASK":
        sub = parts[1].upper() if len(parts) > 1 else "LIST"
        if sub == "LIST":
            tasks = await asyncio.to_thread(_mem.list_tasks, "pending")
            if not tasks:
                return ActionResult("No pending tasks, sir.")
            lines = [f"- #{t['id']} {t['title']}" for t in tasks[:10]]
            return ActionResult("Pending tasks:\n" + "\n".join(lines))
        if sub == "CREATE" and len(parts) > 2:
            title = parts[2].strip()
            if not title:
                return ActionResult("Task title was empty.", status="failed")
            task_id = await asyncio.to_thread(_mem.add_task, title)
            return ActionResult(f"Task #{task_id} added: {title}")
        if sub == "DONE" and len(parts) > 2:
            try:
                task_id = int(parts[2])
            except ValueError:
                return ActionResult("Invalid task ID.", status="failed")
            ok = await asyncio.to_thread(_mem.update_task_status, task_id, "done")
            return ActionResult(
                (
                    f"Task #{task_id} marked done."
                    if ok
                    else f"Task #{task_id} not found."
                ),
                status="completed" if ok else "failed",
            )

    if kind == "UI":
        sub = parts[1].upper() if len(parts) > 1 else ""
        if sub == "FOCUS":
            from gui_actions import focus_app

            target = parts[2] if len(parts) > 2 else ""
            text = await asyncio.to_thread(focus_app, target)
            return ActionResult(
                text,
                status="completed" if text.startswith("Focused ") else "failed",
            )
        if sub == "OBSERVE":
            from gui_actions import observe_frontmost_snapshot

            text, snapshot = await asyncio.to_thread(observe_frontmost_snapshot)
            if ui_context is not None:
                # Snapshot is None on any failure, so a failed observe leaves no
                # reusable root for a follow-up CLICK.
                ui_context["observation"] = snapshot
            return ActionResult(
                text,
                status=(
                    "failed"
                    if not text
                    or text.startswith("Couldn't ")
                    or text.startswith("No frontmost app")
                    or " no inspectable UI " in text
                    else "completed"
                ),
            )
        if sub == "CLICK":
            from gui_actions import click_element

            payload = parts[2] if len(parts) > 2 else ""
            role, sep, label = payload.partition("::")
            if not sep:
                return ActionResult("UI:CLICK needs role::label.", status="failed")
            role_clean = role.strip()
            label_clean = label.strip()
            if not role_clean or not label_clean:
                # An empty label would match every element via substring
                # search and bypass safety.classify's risky-label guard.
                return ActionResult(
                    "UI:CLICK needs a non-empty role and label.",
                    status="failed",
                )
            observation = ui_context.get("observation") if ui_context else None
            text = await asyncio.to_thread(
                click_element, role_clean, label_clean, observation
            )
            return ActionResult(
                text,
                status="completed" if text.startswith("Clicked ") else "failed",
            )
        if sub == "TYPE":
            from gui_actions import type_text

            text = parts[2] if len(parts) > 2 else ""
            result = await asyncio.to_thread(type_text, text)
            return ActionResult(
                result,
                status="completed" if result.startswith("Typed: ") else "failed",
            )
        if sub == "KEY":
            from gui_actions import send_key

            spec = parts[2] if len(parts) > 2 else ""
            text = await asyncio.to_thread(send_key, spec)
            return ActionResult(
                text,
                status="completed" if text.startswith("Sent ") else "failed",
            )
        if sub == "SCROLL":
            from gui_actions import scroll

            payload = parts[2] if len(parts) > 2 else ""
            direction, sep, amount_str = payload.partition("::")
            if not sep:
                return ActionResult(
                    "UI:SCROLL needs direction::amount.",
                    status="failed",
                )
            try:
                amount = int(amount_str.strip())
            except ValueError:
                return ActionResult(
                    f"UI:SCROLL amount must be an integer, got '{amount_str}'.",
                    status="failed",
                )
            text = await asyncio.to_thread(scroll, direction.strip(), amount)
            return ActionResult(
                text,
                status="completed" if text.startswith("Scrolled ") else "failed",
            )
        return ActionResult(f"Unknown UI action: {sub}", status="failed")

    if kind == "COMPUTER":
        from computer_use import run_computer_goal

        goal = parts[1] if len(parts) > 1 else ""
        if len(parts) > 2:
            goal = goal + ":" + parts[2]
        goal, display_id = _parse_computer_goal(goal)
        if not goal:
            return ActionResult("COMPUTER needs a non-empty goal.", status="failed")
        text = await asyncio.to_thread(
            run_computer_goal,
            goal,
            computer_progress_callback,
            display_id,
        )
        return ActionResult(
            text,
            status=(
                "failed"
                if text.startswith("Missing goal")
                or text.startswith("Computer Use failed:")
                else "completed"
            ),
        )

    return ActionResult(f"Unknown action: {kind}", status="failed")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(title="JARVIS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_dist = Path("frontend/dist")
if _dist.exists():
    app.mount("/app", StaticFiles(directory=str(_dist), html=True), name="static")


def _task_type(text: str) -> str:
    lower = text.lower()
    if any(
        keyword in lower
        for keyword in ("build", "code", "implement", "작성", "만들어", "구현")
    ):
        return "work"
    if any(
        keyword in lower for keyword in ("plan", "steps", "outline", "계획", "단계")
    ):
        return "plan"
    return "voice"


def _format_confirm_prompt(raw: str, action: str) -> str:
    prose = ACTION_RE.sub("", raw).strip()
    if prose:
        return f"{prose} 진행할까요? / Proceed? (yes/no)"
    return f"Run action `{action}`? Say yes or no."


def _ws_id(ws: WebSocket) -> str:
    return f"{id(ws):x}"


async def _run_action_loop(
    *,
    messages: list[dict],
    system: str,
    task: str,
    max_steps: int,
    on_step: StepCallback | None = None,
) -> tuple[str, list[tuple[str, str]], "PendingAction | None"]:
    """Run a bounded ReAct loop.

    Returns (final_raw_from_last_call, executed_steps, pending_for_confirm).
    Termination: (a) LLM returns no action tag, (b) safety CONFIRM (pending
    returned), (c) max_steps reached.
    """
    import safety  # local import to keep top-of-file lean

    history = list(messages)
    steps: list[tuple[str, str]] = []
    # Per-turn UI observation cache, owned entirely by this loop. UI:OBSERVE
    # populates it; the immediately-following UI:CLICK reuses it; any other
    # step clears it. Being a loop-local means concurrent websocket turns can
    # never clear or consume each other's snapshot.
    ui_context: dict = {}
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
        if steps and steps[-1][0] == tag:
            return raw, steps, None
        decision = safety.classify(tag)
        if decision is safety.Decision.CONFIRM:
            pending = PendingAction(
                action=tag,
                history=history,
                asked_at=time.time(),
            )
            return raw, steps, pending
        if decision is safety.Decision.BLOCKED:
            result = ActionResult(f"blocked: {safety.reason(tag)}", status="blocked")
        else:
            try:
                if _step_kind(tag) == "COMPUTER":
                    result = await _dispatch_action_result(
                        tag,
                        _computer_progress_callback(on_step),
                    )
                else:
                    result = await _dispatch_action_result(tag, ui_context=ui_context)
            except Exception as e:  # noqa: BLE001
                log.error("Action dispatch error: %s", e)
                result = ActionResult(f"error: {e}", status="failed")
        # Only a successful OBSERVE keeps its snapshot for the next CLICK; every
        # other step (CLICK consume, FOCUS, TYPE, non-UI, blocked, …) drops it.
        if _step_kind(tag) != "UI:OBSERVE":
            ui_context.pop("observation", None)
        steps.append((tag, result.text))
        if on_step is not None:
            await on_step(tag, result)
        history = history + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": f"[SYSTEM RESULT]\n{result.text}"},
        ]
    return raw, steps, None


async def handle_message(ws: WebSocket, text: str) -> None:
    await ws.send_json({"type": "thinking"})

    import safety  # local import

    wsid = _ws_id(ws)

    async def send_step(tag: str, result: ActionResult) -> None:
        await ws.send_json(
            {
                "type": "step",
                "kind": _step_kind(tag),
                "summary": _step_summary(tag, result),
            }
        )

    pending_existing = _pending.pop(wsid, None)
    if pending_existing is not None and not pending_existing.expired():
        # Negative-first: if the reply contains any cancel/stop token, cancel —
        # even when an affirmative token is also present (e.g. "no go",
        # "yes, cancel"). Erring toward cancellation is the safer default
        # for risky-action confirmations.
        if safety.is_negative(text):
            spoken = "Cancelled. / 취소했어요."
            _mem.add_exchange("user", text)
            _mem.add_exchange("assistant", spoken)
            await ws.send_json({"type": "text", "content": spoken})
            audio = await synthesize(spoken)
            await _send_audio_chunks(ws, audio)
            await ws.send_json({"type": "done"})
            return
        if safety.is_affirmative(text):
            try:
                if _step_kind(pending_existing.action) == "COMPUTER":
                    result = await _dispatch_action_result(
                        pending_existing.action,
                        _computer_progress_callback(send_step),
                    )
                else:
                    result = await _dispatch_action_result(pending_existing.action)
            except Exception as e:  # noqa: BLE001
                log.error("Confirmed action failed: %s", e)
                result = ActionResult(f"error: {e}", status="failed")
            await send_step(pending_existing.action, result)
            follow_msgs = pending_existing.history + [
                {
                    "role": "user",
                    "content": (
                        f"[SYSTEM RESULT]\n{result.text}\n\n"
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
                spoken = result.text
            _mem.add_exchange("user", text)
            _mem.add_exchange("assistant", spoken)
            await ws.send_json({"type": "text", "content": spoken})
            audio = await synthesize(spoken)
            await _send_audio_chunks(ws, audio)
            await ws.send_json({"type": "done"})
            return
        # neither yes nor no — drop pending (already popped), fall through to normal handling

    messages = _mem.get_recent()
    messages.append({"role": "user", "content": text})

    try:
        raw, steps, pending = await _run_action_loop(
            messages=messages,
            system=_build_system_prompt(),
            task=_task_type(text),
            max_steps=MAX_STEPS,
            on_step=send_step,
        )
    except Exception as e:  # noqa: BLE001
        log.error("LLM router error: %s", e)
        await ws.send_json({"type": "error", "message": "LLM provider error"})
        return

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

    spoken = ACTION_RE.sub("", raw).strip()

    if steps:
        follow_msgs = list(messages) + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    f"[SYSTEM RESULT]\n{steps[-1][1]}\n\n" "Narrate in 1-2 sentences."
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


async def handle_today_report(ws: WebSocket) -> None:
    await ws.send_json({"type": "thinking"})

    from calendar_access import get_events_summary
    from mail_access import get_mail_summary

    events, mail = await asyncio.gather(
        asyncio.to_thread(get_events_summary),
        asyncio.to_thread(get_mail_summary),
    )

    try:
        spoken = await _router.complete(
            task="narrate",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"[CALENDAR]\n{events}\n\n[MAIL]\n{mail}\n\n"
                        "Brief morning summary in 2-3 sentences. British butler style."
                    ),
                }
            ],
            system=_build_system_prompt(),
            max_tokens=200,
        )
    except Exception as e:
        log.error("Today report router error: %s", e)
        await ws.send_json({"type": "error", "message": "LLM provider error"})
        return

    _mem.add_exchange("assistant", spoken)
    await ws.send_json({"type": "text", "content": spoken})

    audio = await synthesize(spoken)
    await _send_audio_chunks(ws, audio)

    await ws.send_json({"type": "done"})


def _on_handler_done(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("Handler task error: %s", exc)


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket) -> None:
    await ws.accept()
    log.info("Client connected")
    current: Optional[asyncio.Task] = None

    def cancel_current() -> bool:
        if current is not None and not current.done():
            current.cancel()
            return True
        return False

    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "transcript":
                cancel_current()
                text = (msg.get("text") or "").strip()
                if text:
                    current = asyncio.create_task(handle_message(ws, text))
                    current.add_done_callback(_on_handler_done)
            elif kind == "today-report":
                cancel_current()
                current = asyncio.create_task(handle_today_report(ws))
                current.add_done_callback(_on_handler_done)
            elif kind == "abort":
                if cancel_current():
                    await ws.send_json({"type": "done"})
            elif kind == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        log.info("Client disconnected")
        cancel_current()
    except Exception as e:
        log.error("WS error: %s", e)
        cancel_current()


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


@app.get("/api/status")
async def api_status():
    return {"status": "online", "version": "1.0.0"}


@app.get("/api/health")
async def api_health():
    return {"ok": True}


@app.get("/api/memory/facts")
async def api_facts():
    return {"facts": _mem.list_facts()}


@app.post("/api/memory/fact")
async def api_add_fact(body: dict):
    fact = (body.get("fact") or "").strip()
    if not fact:
        return JSONResponse({"error": "fact required"}, status_code=400)
    return {"id": _mem.add_fact(fact), "fact": fact}


@app.delete("/api/memory/fact/{fact_id}")
async def api_del_fact(fact_id: int):
    return {"ok": _mem.delete_fact(fact_id)}


@app.get("/api/memory/tasks")
async def api_tasks():
    return {"tasks": _mem.list_tasks()}


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    from calendar_access import start_background_refresh

    print("JARVIS server · Built from CLAUDE.md by Taoufik — instagram.com/taoufik.ai")
    start_background_refresh()
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=PORT,
        ssl_certfile=str(SSL_CERT) if SSL_CERT.exists() else None,
        ssl_keyfile=str(SSL_KEY) if SSL_KEY.exists() else None,
        log_level="info",
    )
