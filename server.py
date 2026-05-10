# JARVIS — Built from CLAUDE.md by Taoufik · instagram.com/taoufik.ai
"""JARVIS FastAPI voice assistant server."""

import asyncio
import base64
import logging
import os
import re
from pathlib import Path
from typing import Optional

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
# System Prompt
# ---------------------------------------------------------------------------


def _build_system_prompt() -> str:
    facts = _mem.facts_as_context()
    name = USER_NAME if USER_NAME and USER_NAME.lower() != "sir" else "sir"
    facts_block = f"\n\n{facts}" if facts else ""
    return f"""You are JARVIS, a British AI butler assistant running on macOS.

Personality: Precise, dry wit, subtly sardonic, unwaveringly helpful. British vocabulary.
Voice: Concise — max 2-3 sentences. No markdown. You are speaking aloud.
Address the user as '{name}'.
Respond in the user's language. Mix Korean and English naturally — like a bilingual speaker would. 사용자가 한국어로 말하면 한국어로, 영어면 영어로, 혼용하면 자연스럽게 혼용하여 답하세요.

Embed ONE action tag per response when system access is needed:
  [ACTION:CALENDAR]                      — upcoming calendar events
  [ACTION:MAIL]                          — unread mail summary
  [ACTION:MAIL:SEARCH:query]             — search mail
  [ACTION:NOTES:LIST]                    — list note titles
  [ACTION:NOTES:READ:title]              — read a note
  [ACTION:NOTES:CREATE:title::content]   — create a note
  [ACTION:TERMINAL:command]              — run shell command in Terminal
  [ACTION:BROWSE:url]                    — browse a URL
  [ACTION:SEARCH:query]                  — web search
  [ACTION:WORK:task]                     — dispatch to Claude Code
  [ACTION:PLAN:description]              — start a planning session with clarifying questions
  [ACTION:PLAN_ANSWER:task::answers]     — produce the numbered plan once user has answered
  [ACTION:REMEMBER:fact]                 — remember a user fact
  [ACTION:FORGET:fact_id]               — forget a stored fact
  [ACTION:RECALL:query]                  — search prior conversation
  [ACTION:TASK:CREATE:title]             — add a pending task
  [ACTION:TASK:LIST]                     — list pending tasks
  [ACTION:TASK:DONE:task_id]             — mark a task as done
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


async def dispatch_action(tag: str) -> str:
    parts = tag.split(":", 2)
    kind = parts[0].upper()

    if kind == "CALENDAR":
        from calendar_access import get_events_summary

        return await asyncio.to_thread(get_events_summary)

    if kind == "MAIL":
        if len(parts) >= 3 and parts[1].upper() == "SEARCH":
            from mail_access import search_mail

            items = await asyncio.to_thread(search_mail, parts[2])
            return (
                "\n".join(f"- {i['subject']} from {i['sender']}" for i in items)
                if items
                else "No matching mail found."
            )
        from mail_access import get_mail_summary

        return await asyncio.to_thread(get_mail_summary)

    if kind == "NOTES":
        sub = parts[1].upper() if len(parts) > 1 else "LIST"
        if sub == "LIST":
            from notes_access import list_note_titles

            titles = await asyncio.to_thread(list_note_titles)
            return ("Your notes: " + ", ".join(titles)) if titles else "No notes found."
        if sub == "READ" and len(parts) > 2:
            from notes_access import read_note

            body = await asyncio.to_thread(read_note, parts[2])
            return body if body else f"Note '{parts[2]}' not found."
        if sub == "CREATE" and len(parts) > 2:
            from notes_access import create_note

            title, _, content = parts[2].partition("::")
            ok = await asyncio.to_thread(create_note, title.strip(), content.strip())
            return (
                f"Note '{title.strip()}' created." if ok else "Failed to create note."
            )

    if kind == "TERMINAL":
        from actions import open_terminal

        cmd = parts[1] if len(parts) > 1 else ""
        await asyncio.to_thread(open_terminal, cmd)
        return f"Terminal opened{': ' + cmd if cmd else ''}."

    if kind == "BROWSE":
        from browser import browse_url

        return await browse_url(parts[1] if len(parts) > 1 else "")

    if kind == "SEARCH":
        from browser import search_summary

        return await search_summary(":".join(parts[1:]))

    if kind == "WORK":
        from work_mode import start_task

        return start_task(":".join(parts[1:]))

    if kind == "PLAN":
        from planner import get_clarifying_questions

        return await get_clarifying_questions(":".join(parts[1:]))

    if kind == "PLAN_ANSWER":
        from planner import generate_plan

        payload = ":".join(parts[1:])
        task, sep, answers = payload.partition("::")
        if not sep or not task.strip() or not answers.strip():
            return "Plan answer needs both task and answers separated by '::'."
        return await generate_plan(task.strip(), answers.strip())

    if kind == "REMEMBER":
        fact = ":".join(parts[1:])
        await asyncio.to_thread(_mem.add_fact, fact)
        return f"Remembered: {fact}"

    if kind == "FORGET":
        try:
            await asyncio.to_thread(_mem.delete_fact, int(parts[1]))
            return "Fact forgotten."
        except (ValueError, IndexError):
            return "Invalid fact ID."

    if kind == "RECALL":
        query = ":".join(parts[1:]).strip()
        if not query:
            return "Recall query was empty."
        hits = await asyncio.to_thread(_mem.search, query)
        if not hits:
            return f"No prior conversation matches '{query}'."
        lines = [f"- ({h['role']}) {h['content']}" for h in hits[:5]]
        return "Recalled exchanges:\n" + "\n".join(lines)

    if kind == "TASK":
        sub = parts[1].upper() if len(parts) > 1 else "LIST"
        if sub == "LIST":
            tasks = await asyncio.to_thread(_mem.list_tasks, "pending")
            if not tasks:
                return "No pending tasks, sir."
            lines = [f"- #{t['id']} {t['title']}" for t in tasks[:10]]
            return "Pending tasks:\n" + "\n".join(lines)
        if sub == "CREATE" and len(parts) > 2:
            title = parts[2].strip()
            if not title:
                return "Task title was empty."
            task_id = await asyncio.to_thread(_mem.add_task, title)
            return f"Task #{task_id} added: {title}"
        if sub == "DONE" and len(parts) > 2:
            try:
                task_id = int(parts[2])
            except ValueError:
                return "Invalid task ID."
            ok = await asyncio.to_thread(_mem.update_task_status, task_id, "done")
            return (
                f"Task #{task_id} marked done." if ok else f"Task #{task_id} not found."
            )

    return f"Unknown action: {kind}"


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(title="JARVIS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


async def handle_message(ws: WebSocket, text: str) -> None:
    await ws.send_json({"type": "thinking"})
    messages = _mem.get_recent()
    messages.append({"role": "user", "content": text})

    try:
        raw = await _router.complete(
            task=_task_type(text),
            messages=messages,
            system=_build_system_prompt(),
            max_tokens=250,
        )
    except Exception as e:
        log.error("LLM router error: %s", e)
        await ws.send_json({"type": "error", "message": "LLM provider error"})
        return

    # Dispatch action tag if present
    action_result = ""
    m = ACTION_RE.search(raw)
    if m:
        try:
            action_result = await dispatch_action(m.group(1))
        except Exception as e:
            log.error("Action dispatch error: %s", e)
            action_result = "Action failed."

    # Strip action tags for TTS
    spoken = ACTION_RE.sub("", raw).strip()

    # Follow-up narration when action produced content
    if action_result:
        follow_msgs = list(messages) + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": f"[SYSTEM RESULT]\n{action_result}\n\nNarrate in 1-2 sentences.",
            },
        ]
        try:
            spoken = await _router.complete(
                task="narrate",
                messages=follow_msgs,
                system=_build_system_prompt(),
                max_tokens=150,
            )
        except Exception:
            spoken = action_result

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


@app.post("/api/wake")
async def api_wake():
    return {"status": "acknowledged"}


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
        host="0.0.0.0",
        port=PORT,
        ssl_certfile=str(SSL_CERT) if SSL_CERT.exists() else None,
        ssl_keyfile=str(SSL_KEY) if SSL_KEY.exists() else None,
        log_level="info",
    )
