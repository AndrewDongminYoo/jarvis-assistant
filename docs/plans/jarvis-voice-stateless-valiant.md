# JARVIS Voice Assistant — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete voice-first AI assistant for macOS — speech-in/speech-out with a British butler personality, Three.js particle orb, and macOS system integrations via AppleScript.

**Architecture:** Browser captures speech via Web Speech API, sends transcript over WebSocket to FastAPI, FastAPI queries Claude Haiku (max 250 tokens) and streams the response, parses `[ACTION:X]` tags to trigger AppleScript/Playwright/Claude Code integrations, synthesizes speech via ElevenLabs (with macOS `say` fallback), and streams base64 audio back to the browser. SQLite with FTS5 stores conversation history and user facts.

**Tech Stack:** Python 3.11 · FastAPI · Anthropic SDK · ElevenLabs HTTP API · SQLite FTS5 · Playwright · AppleScript · Vite · TypeScript · Three.js · Web Speech API · Web Audio API

---

## Pre-Flight Checklist

Before implementing, confirm:

- [ ] `ANTHROPIC_API_KEY` available (console.anthropic.com)
- [ ] `ELEVENLABS_API_KEY` available
- [ ] Python 3.11+ installed (`python3 --version`)
- [ ] Node 18+ installed (`node --version`)
- [ ] Google Chrome installed (Web Speech API)
- [ ] `openssl` available (`openssl version`)

---

## File Map

```plaintext
jarvis/
├── .env.example          # API keys template
├── .env                  # (gitignored) actual keys
├── .gitignore
├── requirements.txt
├── server.py             # FastAPI entry-point (~2300 lines)
├── memory.py             # SQLite + FTS5 memory system
├── calendar_access.py    # AppleScript -> Apple Calendar
├── mail_access.py        # AppleScript -> Apple Mail (read-only)
├── notes_access.py       # AppleScript -> Apple Notes
├── actions.py            # AppleScript system actions
├── browser.py            # Playwright web browsing
├── work_mode.py          # claude CLI sessions
├── planner.py            # conversational task planning
├── data/
│   └── ambient/          # reserved for future audio assets
├── scripts/
│   └── start.sh          # convenience launcher
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── src/
        ├── index.html
        ├── style.css
        ├── ws.ts         # WebSocket client + auto-reconnect
        ├── voice.ts      # Speech input + audio playback queue
        ├── orb.ts        # Three.js audio-reactive particle orb
        ├── main.ts       # State machine (idle/listening/thinking/speaking)
        └── settings.ts   # Settings panel
```

---

## WebSocket Protocol Reference

All messages are JSON text frames.

**Client to Server:**

```json
{ "type": "transcript", "text": "What's on my calendar today?" }
{ "type": "ping" }
{ "type": "abort" }
```

**Server to Client:**

```json
{ "type": "pong" }
{ "type": "thinking" }
{ "type": "text",  "content": "Good morning, sir." }
{ "type": "audio", "data": "<base64 mp3 chunk>" }
{ "type": "done" }
{ "type": "error", "message": "..." }
```

---

## Action Tag Grammar

Claude embeds these in its text response. Server strips them before TTS.

| Tag                                    | Effect                                         |
| -------------------------------------- | ---------------------------------------------- |
| `[ACTION:CALENDAR]`                    | Read upcoming events from Apple Calendar       |
| `[ACTION:MAIL]`                        | Read unread Apple Mail count + subjects        |
| `[ACTION:MAIL:SEARCH:query]`           | Search Apple Mail                              |
| `[ACTION:NOTES:LIST]`                  | List note titles in Apple Notes                |
| `[ACTION:NOTES:READ:title]`            | Read a specific note                           |
| `[ACTION:NOTES:CREATE:title::content]` | Create new Apple Note                          |
| `[ACTION:TERMINAL:command]`            | Run command in new Terminal window             |
| `[ACTION:BROWSE:url]`                  | Visit URL with Playwright and return page text |
| `[ACTION:SEARCH:query]`                | DuckDuckGo search + return top results         |
| `[ACTION:WORK:task_description]`       | Start `claude -p --continue` session           |
| `[ACTION:PLAN:description]`            | Trigger planner module for multi-step task     |
| `[ACTION:REMEMBER:fact]`               | Persist a user fact to memory                  |
| `[ACTION:FORGET:fact_id]`              | Delete a stored fact                           |

---

## Task 1: Project Scaffold

**Files:**

- Create: `.gitignore`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `data/ambient/.gitkeep`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p data/ambient scripts helpers frontend/src
```

- [ ] **Step 2: Create .gitignore**

```gitignore
.env
.env.local
node_modules/
.venv/
venv/
__pycache__/
*.pyc
*.db
*.db-shm
*.db-wal
data/*.jsonl
data/active_session.json
data/.jarvis_output.txt
*.pem
dist/
.vite/
frontend/.vite/
.DS_Store
.vscode/
.idea/
```

- [ ] **Step 3: Create .env.example**

```env
# Required API Keys
ANTHROPIC_API_KEY=your-anthropic-key-here
ELEVENLABS_API_KEY=your-elevenlabs-key-here

# Optional: ElevenLabs voice model (defaults to "George" British voice)
# ELEVENLABS_VOICE_ID=UgBBYS2sOqTuMpoF3BR0

# Optional: Your name
# USER_NAME=Andrew

# Optional: Specific Apple Calendar accounts
# CALENDAR_ACCOUNTS=ydm2790@gmail.com,dm.yu@teamremited.com
```

- [ ] **Step 4: Create requirements.txt**

```plaintext
anthropic>=0.39.0,<1.0
httpx>=0.27.0,<1.0
fastapi>=0.115.0,<1.0
uvicorn[standard]>=0.32.0,<1.0
pydantic>=2.0.0,<3.0
websockets>=13.0,<16.0
playwright>=1.40.0,<2.0
pyyaml>=6.0,<7.0
sounddevice>=0.4.6,<1.0
numpy>=1.26.0,<3.0
python-dotenv>=1.0.0,<2.0
```

- [ ] **Step 5: Create frontend/package.json**

```json
{
  "name": "jarvis-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "vite": "^6.0.0"
  },
  "dependencies": {
    "@types/three": "^0.183.1",
    "three": "^0.183.2"
  }
}
```

- [ ] **Step 6: Create frontend/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}
```

- [ ] **Step 7: Create frontend/vite.config.ts**

```typescript
import { defineConfig } from "vite";

export default defineConfig({
  root: "src",
  server: {
    port: 5173,
    proxy: {
      "/ws": {
        target: "https://localhost:8340",
        ws: true,
        secure: false,
      },
      "/api": {
        target: "https://localhost:8340",
        secure: false,
      },
    },
  },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
```

- [ ] **Step 8: Commit scaffold**

```bash
git add .gitignore .env.example requirements.txt frontend/ data/ scripts/ helpers/
git commit -m "chore: project scaffold for JARVIS voice assistant"
```

---

## Task 2: memory.py — SQLite Three-Tier Memory

**Files:**

- Create: `memory.py`

Key design: three memory tiers — (1) in-process `recent` list for fast context retrieval, (2) SQLite messages table for full conversation log, (3) SQLite facts table for persistent user facts. FTS5 virtual table enables full-text search across conversation history.

- [ ] **Step 1: Write memory.py**

```python
# memory.py — JARVIS SQLite three-tier memory system
import sqlite3
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/jarvis.db")
MAX_RECENT = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    role    TEXT NOT NULL,
    content TEXT NOT NULL,
    ts      REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content, content=messages, content_rowid=id
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TABLE IF NOT EXISTS facts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fact    TEXT NOT NULL UNIQUE,
    ts      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title   TEXT NOT NULL,
    status  TEXT NOT NULL DEFAULT 'pending',
    ts      REAL NOT NULL
);
"""

class Memory:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.recent: list[dict] = []

    def add_exchange(self, role: str, content: str) -> None:
        self.recent.append({"role": role, "content": content})
        if len(self.recent) > MAX_RECENT:
            self.recent = self.recent[-MAX_RECENT:]
        self.conn.execute(
            "INSERT INTO messages (role, content, ts) VALUES (?,?,?)",
            (role, content, time.time()),
        )
        self.conn.commit()

    def get_recent(self) -> list[dict]:
        return list(self.recent)

    def clear_recent(self) -> None:
        self.recent = []

    def add_fact(self, fact: str) -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO facts (fact, ts) VALUES (?,?)",
            (fact, time.time()),
        )
        self.conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = self.conn.execute("SELECT id FROM facts WHERE fact=?", (fact,)).fetchone()
        return row[0] if row else -1

    def delete_fact(self, fact_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM facts WHERE id=?", (fact_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_facts(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, fact, ts FROM facts ORDER BY ts DESC"
        ).fetchall()
        return [{"id": r[0], "fact": r[1], "ts": r[2]} for r in rows]

    def facts_as_context(self) -> str:
        facts = self.list_facts()
        if not facts:
            return ""
        lines = "\n".join(f"- {f['fact']}" for f in facts)
        return f"Known facts about the user:\n{lines}"

    def search(self, query: str, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            """SELECT m.id, m.role, m.content, m.ts
               FROM messages_fts fts
               JOIN messages m ON fts.rowid = m.id
               WHERE messages_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [{"id": r[0], "role": r[1], "content": r[2], "ts": r[3]} for r in rows]

    def add_task(self, title: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO tasks (title, status, ts) VALUES (?,?,?)",
            (title, "pending", time.time()),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore

    def update_task_status(self, task_id: int, status: str) -> bool:
        cur = self.conn.execute(
            "UPDATE tasks SET status=? WHERE id=?", (status, task_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def list_tasks(self, status: Optional[str] = None) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT id, title, status, ts FROM tasks WHERE status=? ORDER BY ts DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, title, status, ts FROM tasks ORDER BY ts DESC"
            ).fetchall()
        return [{"id": r[0], "title": r[1], "status": r[2], "ts": r[3]} for r in rows]
```

- [ ] **Step 2: Smoke test**

```bash
python3 -c "
from memory import Memory
m = Memory()
m.add_exchange('user', 'Hello JARVIS')
m.add_exchange('assistant', 'Good day, sir.')
fid = m.add_fact('User prefers Earl Grey tea')
print('fact id:', fid)
print('context:', m.facts_as_context())
print('recent count:', len(m.get_recent()))
results = m.search('JARVIS')
print('fts results:', len(results))
print('ALL TESTS PASSED')
"
```

Expected: `ALL TESTS PASSED`

- [ ] **Step 3: Commit**

```bash
git add memory.py
git commit -m "feat: SQLite three-tier memory with FTS5 (memory.py)"
```

---

## Task 3: AppleScript Modules — Calendar, Mail, Notes

**Files:**

- Create: `calendar_access.py`
- Create: `mail_access.py`
- Create: `notes_access.py`

- [ ] **Step 1: Create calendar_access.py**

```python
# calendar_access.py — Read Apple Calendar via AppleScript with background cache
import subprocess
import threading
import time

_cache: dict = {"events": [], "updated_at": 0.0}
_lock = threading.Lock()
CACHE_TTL = 300

APPLESCRIPT = """
set resultList to {}
set todayStart to (current date)
set hours of todayStart to 0
set minutes of todayStart to 0
set seconds of todayStart to 0
set weekEnd to todayStart + (7 * days)
tell application "Calendar"
    repeat with aCal in calendars
        repeat with ev in (every event of aCal whose start date >= todayStart and start date <= weekEnd)
            set evStart to start date of ev
            set evTitle to summary of ev
            set resultList to resultList & {evTitle & " | " & (evStart as string)}
        end repeat
    end repeat
end tell
return resultList
"""

def _run(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=15)
    return r.stdout.strip()

def _fetch_events() -> list[dict]:
    raw = _run(APPLESCRIPT)
    events: list[dict] = []
    if raw:
        for item in raw.split(", "):
            parts = item.strip().split(" | ")
            if len(parts) == 2:
                events.append({"title": parts[0], "start": parts[1]})
    return events

def _refresh_cache() -> None:
    events = _fetch_events()
    with _lock:
        _cache["events"] = events
        _cache["updated_at"] = time.time()

def get_upcoming_events(force: bool = False) -> list[dict]:
    with _lock:
        age = time.time() - _cache["updated_at"]
    if force or age > CACHE_TTL:
        _refresh_cache()
    with _lock:
        return list(_cache["events"])

def get_events_summary() -> str:
    events = get_upcoming_events()
    if not events:
        return "Your calendar is clear for the next 7 days, sir."
    lines = [f"- {e['title']} at {e['start']}" for e in events[:10]]
    return "Upcoming events:\n" + "\n".join(lines)

def start_background_refresh() -> None:
    def _loop() -> None:
        while True:
            try:
                _refresh_cache()
            except Exception:
                pass
            time.sleep(CACHE_TTL)
    threading.Thread(target=_loop, daemon=True).start()
```

- [ ] **Step 2: Create mail_access.py**

```python
# mail_access.py — Read-only Apple Mail access via AppleScript
import subprocess

def _run(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=15)
    return r.stdout.strip()

def get_unread_count() -> int:
    raw = _run('tell application "Mail" to return unread count of inbox')
    try:
        return int(raw)
    except ValueError:
        return 0

def get_recent_subjects(limit: int = 5) -> list[str]:
    script = f"""
tell application "Mail"
    set results to {{}}
    set counter to 0
    repeat with m in messages of inbox
        if counter >= {limit} then exit repeat
        set results to results & {{subject of m}}
        set counter to counter + 1
    end repeat
    return results
end tell
"""
    raw = _run(script)
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else []

def search_mail(query: str, limit: int = 5) -> list[dict]:
    escaped = query.replace('"', '\\"')
    script = f"""
tell application "Mail"
    set results to {{}}
    set counter to 0
    set msgs to (messages of inbox whose subject contains "{escaped}" or sender contains "{escaped}")
    repeat with m in msgs
        if counter >= {limit} then exit repeat
        set results to results & {{subject of m & " | " & sender of m}}
        set counter to counter + 1
    end repeat
    return results
end tell
"""
    raw = _run(script)
    items: list[dict] = []
    if raw:
        for line in raw.split(","):
            parts = line.strip().split(" | ")
            if len(parts) == 2:
                items.append({"subject": parts[0], "sender": parts[1]})
    return items

def get_mail_summary() -> str:
    count = get_unread_count()
    if count == 0:
        return "Your inbox is clear, sir."
    subjects = get_recent_subjects()
    lines = "\n".join(f"- {s}" for s in subjects)
    return f"You have {count} unread messages. Recent subjects:\n{lines}"
```

- [ ] **Step 3: Create notes_access.py**

```python
# notes_access.py — Apple Notes: read and create via AppleScript (no edit/delete)
import subprocess
from typing import Optional

def _run(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=15)
    return r.stdout.strip()

def list_note_titles(limit: int = 20) -> list[str]:
    script = f"""
tell application "Notes"
    set results to {{}}
    set counter to 0
    repeat with n in notes
        if counter >= {limit} then exit repeat
        set results to results & {{name of n}}
        set counter to counter + 1
    end repeat
    return results
end tell
"""
    raw = _run(script)
    return [t.strip() for t in raw.split(",") if t.strip()] if raw else []

def read_note(title: str) -> Optional[str]:
    escaped = title.replace('"', '\\"')
    script = f"""
tell application "Notes"
    set matched to (notes whose name is "{escaped}")
    if length of matched > 0 then return body of item 1 of matched
    return ""
end tell
"""
    raw = _run(script)
    return raw if raw else None

def create_note(title: str, content: str) -> bool:
    et = title.replace('"', '\\"')
    ec = content.replace('"', '\\"').replace("\n", "\\n")
    script = f'tell application "Notes" to make new note with properties {{name:"{et}", body:"{ec}"}}'
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=15)
    return r.returncode == 0
```

- [ ] **Step 4: Smoke test**

```bash
python3 -c "
from calendar_access import get_events_summary
from mail_access import get_mail_summary
from notes_access import list_note_titles
print('Calendar:', get_events_summary()[:80])
print('Mail:', get_mail_summary()[:80])
print('Notes:', list_note_titles()[:3])
print('ALL PASSED')
"
```

- [ ] **Step 5: Commit**

```bash
git add calendar_access.py mail_access.py notes_access.py
git commit -m "feat: AppleScript modules for Calendar, Mail, Notes"
```

---

## Task 4: actions.py + browser.py

**Files:**

- Create: `actions.py`
- Create: `browser.py`

- [ ] **Step 1: Create actions.py**

```python
# actions.py — System-level AppleScript actions for JARVIS
import subprocess

def _osascript(script: str) -> tuple[bool, str]:
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=15)
    return r.returncode == 0, r.stdout.strip()

def open_terminal(command: str = "") -> bool:
    if command:
        escaped = command.replace('"', '\\"')
        script = f'tell app "Terminal" to do script "{escaped}"'
    else:
        script = 'tell app "Terminal" to activate'
    ok, _ = _osascript(script)
    return ok

def open_chrome(url: str = "") -> bool:
    script = (f'open location "{url}"' if url
              else 'tell application "Google Chrome" to activate')
    ok, _ = _osascript(script)
    return ok

def show_notification(title: str, message: str) -> bool:
    et = title.replace('"', '\\"')
    em = message.replace('"', '\\"')
    ok, _ = _osascript(f'display notification "{em}" with title "{et}"')
    return ok

def speak_macos(text: str, voice: str = "Daniel") -> None:
    subprocess.run(["say", "-v", voice, text], timeout=60)
```

- [ ] **Step 2: Create browser.py**

```python
# browser.py — Playwright-based web browsing for JARVIS
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser

_browser: Optional[Browser] = None
_pw = None

async def _get_browser() -> Browser:
    global _browser, _pw
    if _browser is None or not _browser.is_connected():
        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(headless=True)
    return _browser

async def browse_url(url: str, max_chars: int = 3000) -> str:
    browser = await _get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        text = await page.inner_text("body")
        return text[:max_chars]
    except Exception as e:
        return f"Failed to load {url}: {e}"
    finally:
        await page.close()

async def search_web(query: str, max_results: int = 5) -> list[dict]:
    browser = await _get_browser()
    page = await browser.new_page()
    try:
        encoded = query.replace(" ", "+")
        await page.goto(
            f"https://duckduckgo.com/html/?q={encoded}",
            timeout=15000, wait_until="domcontentloaded"
        )
        results: list[dict] = []
        for item in (await page.query_selector_all(".result"))[:max_results]:
            title_el = await item.query_selector(".result__title")
            url_el = await item.query_selector(".result__url")
            snippet_el = await item.query_selector(".result__snippet")
            results.append({
                "title":   await title_el.inner_text()   if title_el   else "",
                "url":     await url_el.inner_text()     if url_el     else "",
                "snippet": await snippet_el.inner_text() if snippet_el else "",
            })
        return results
    except Exception as e:
        return [{"title": "Error", "url": "", "snippet": str(e)}]
    finally:
        await page.close()

async def search_summary(query: str) -> str:
    results = await search_web(query)
    if not results:
        return f"No results found for: {query}"
    return "\n\n".join(
        f"- {r['title']}\n  {r['snippet']}\n  {r['url']}" for r in results
    )
```

- [ ] **Step 3: Smoke test**

```bash
python3 -c "
from actions import show_notification
show_notification('JARVIS Test', 'actions.py OK')
print('actions: OK')
"
python3 -c "
import asyncio
from browser import search_summary
print(asyncio.run(search_summary('Python FastAPI'))[:200])
print('browser: OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add actions.py browser.py
git commit -m "feat: system actions and Playwright browser module"
```

---

## Task 5: work_mode.py + planner.py

**Files:**

- Create: `work_mode.py`
- Create: `planner.py`

- [ ] **Step 1: Create work_mode.py**

```python
# work_mode.py — Persistent Claude Code sessions via claude CLI
import subprocess
import os
import uuid
from pathlib import Path

SESSIONS_DIR = Path("data/work_sessions")

def start_task(task_description: str) -> str:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_id = str(uuid.uuid4())[:8]
    output_file = SESSIONS_DIR / f"{session_id}.txt"
    prompt = f"Task: {task_description}\n\nPlease complete this task step by step."
    subprocess.Popen(
        ["claude", "-p", prompt],
        stdout=open(output_file, "w"),
        stderr=subprocess.STDOUT,
        cwd=os.getcwd(),
    )
    return (
        f"I've dispatched Claude Code to handle that, sir. "
        f"Session {session_id} is running in the background."
    )

def get_session_output(session_id: str) -> str:
    output_file = SESSIONS_DIR / f"{session_id}.txt"
    if not output_file.exists():
        return f"Session {session_id} not found."
    return output_file.read_text()[-2000:]
```

- [ ] **Step 2: Create planner.py**

```python
# planner.py — Conversational task planning with clarifying questions
import os
from anthropic import Anthropic

_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

SYSTEM = (
    "You are JARVIS's planning module. "
    "For any complex task: first ask 3-5 targeted clarifying questions. "
    "Once you have answers, produce a concise numbered plan. "
    "Keep language brief — this output will be spoken aloud."
)

def get_clarifying_questions(task: str) -> str:
    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"User wants to: {task}\n\nAsk clarifying questions."}],
    )
    return resp.content[0].text  # type: ignore

def generate_plan(task: str, answers: str) -> str:
    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=SYSTEM,
        messages=[
            {"role": "user", "content": f"Task: {task}"},
            {"role": "assistant", "content": "Here are my clarifying questions."},
            {"role": "user", "content": f"Answers: {answers}\n\nNow produce the numbered plan."},
        ],
    )
    return resp.content[0].text  # type: ignore
```

- [ ] **Step 3: Commit**

```bash
git add work_mode.py planner.py
git commit -m "feat: work mode and planner modules"
```

---

## Task 6: server.py — FastAPI Server

**Files:**

- Create: `server.py`

Build server.py in five logical sections assembled into one file.

### Section A — Imports, Config, System Prompt

```python
# JARVIS — Built from CLAUDE.md by Taoufik · instagram.com/taoufik.ai
"""JARVIS FastAPI voice assistant server."""
import asyncio
import base64
import logging
import os
import re
import ssl
from pathlib import Path
from typing import Optional

import httpx
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
log = logging.getLogger("jarvis")
logging.basicConfig(level=logging.INFO)

ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
USER_NAME = os.getenv("USER_NAME", "sir")
PORT = int(os.getenv("PORT", "8340"))
SSL_CERT = Path("cert.pem")
SSL_KEY  = Path("key.pem")

anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

def _build_system_prompt() -> str:
    from memory import Memory
    facts = Memory().facts_as_context()
    name = USER_NAME if USER_NAME and USER_NAME != "sir" else "sir"
    facts_block = f"\n\n{facts}" if facts else ""
    return f"""You are JARVIS, a British AI butler assistant running on macOS.

Personality: Precise, dry wit, subtly sardonic, unwaveringly helpful. British vocabulary.
Voice: Concise — max 2-3 sentences. No markdown. You are speaking aloud.
Address the user as '{name}'.

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
  [ACTION:PLAN:description]              — task planning session
  [ACTION:REMEMBER:fact]                 — remember a user fact
  [ACTION:FORGET:fact_id]               — forget a stored fact
{facts_block}
"""
```

### Section B — TTS Pipeline

```python
async def _tts_elevenlabs(text: str) -> Optional[bytes]:
    if not ELEVENLABS_API_KEY:
        return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2",
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

def _tts_macos(text: str) -> None:
    import subprocess
    subprocess.run(["say", "-v", "Daniel", text], timeout=60)

async def synthesize(text: str) -> Optional[bytes]:
    audio = await _tts_elevenlabs(text)
    if audio:
        return audio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _tts_macos, text)
    return None
```

### Section C — Action Tag Parser

```python
ACTION_RE = re.compile(r"\[ACTION:([^\]]+)\]")

async def dispatch_action(tag: str) -> str:
    parts = tag.split(":", 2)
    kind = parts[0].upper()

    if kind == "CALENDAR":
        from calendar_access import get_events_summary
        return get_events_summary()

    if kind == "MAIL":
        if len(parts) >= 3 and parts[1].upper() == "SEARCH":
            from mail_access import search_mail
            items = search_mail(parts[2])
            return ("\n".join(f"- {i['subject']} from {i['sender']}" for i in items)
                    if items else "No matching mail found.")
        from mail_access import get_mail_summary
        return get_mail_summary()

    if kind == "NOTES":
        sub = parts[1].upper() if len(parts) > 1 else "LIST"
        if sub == "LIST":
            from notes_access import list_note_titles
            titles = list_note_titles()
            return ("Your notes: " + ", ".join(titles)) if titles else "No notes found."
        if sub == "READ" and len(parts) > 2:
            from notes_access import read_note
            body = read_note(parts[2])
            return body if body else f"Note '{parts[2]}' not found."
        if sub == "CREATE" and len(parts) > 2:
            from notes_access import create_note
            title, _, content = parts[2].partition("::")
            ok = create_note(title.strip(), content.strip())
            return f"Note '{title.strip()}' created." if ok else "Failed to create note."

    if kind == "TERMINAL":
        from actions import open_terminal
        cmd = parts[1] if len(parts) > 1 else ""
        open_terminal(cmd)
        return f"Terminal opened{' with: ' + cmd if cmd else ''}."

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
        return get_clarifying_questions(":".join(parts[1:]))

    if kind == "REMEMBER":
        from memory import Memory
        fact = ":".join(parts[1:])
        Memory().add_fact(fact)
        return f"Remembered: {fact}"

    if kind == "FORGET":
        from memory import Memory
        try:
            Memory().delete_fact(int(parts[1]))
            return "Fact forgotten."
        except (ValueError, IndexError):
            return "Invalid fact ID."

    return f"Unknown action: {kind}"
```

### Section D — FastAPI App, WebSocket Handler, LLM Logic

```python
app = FastAPI(title="JARVIS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_dist = Path("frontend/dist")
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")

from memory import Memory
_mem = Memory()

async def handle_message(ws: WebSocket, text: str) -> None:
    await ws.send_json({"type": "thinking"})
    messages = _mem.get_recent()
    messages.append({"role": "user", "content": text})

    try:
        resp = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=_build_system_prompt(),
            messages=messages,
        )
        raw = resp.content[0].text  # type: ignore
    except Exception as e:
        log.error("Claude error: %s", e)
        await ws.send_json({"type": "error", "message": "Claude API error"})
        return

    # Dispatch action if present
    action_result = ""
    m = ACTION_RE.search(raw)
    if m:
        try:
            action_result = await dispatch_action(m.group(1))
        except Exception as e:
            log.error("Action dispatch error: %s", e)
            action_result = "Action failed."

    # Strip action tags from spoken text
    spoken = ACTION_RE.sub("", raw).strip()

    # Follow-up narration when action produced content
    if action_result:
        follow_msgs = list(messages) + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": f"[SYSTEM RESULT]\n{action_result}\n\nNarrate in 1-2 sentences."},
        ]
        try:
            f = await anthropic_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                system=_build_system_prompt(),
                messages=follow_msgs,
            )
            spoken = f.content[0].text  # type: ignore
        except Exception:
            spoken = action_result

    _mem.add_exchange("user", text)
    _mem.add_exchange("assistant", spoken)

    await ws.send_json({"type": "text", "content": spoken})

    audio = await synthesize(spoken)
    if audio:
        chunk = 16384
        for i in range(0, len(audio), chunk):
            encoded = base64.b64encode(audio[i : i + chunk]).decode()
            await ws.send_json({"type": "audio", "data": encoded})

    await ws.send_json({"type": "done"})

@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket) -> None:
    await ws.accept()
    log.info("Client connected")
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "transcript":
                t = (msg.get("text") or "").strip()
                if t:
                    await handle_message(ws, t)
            elif msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        log.info("Client disconnected")
    except Exception as e:
        log.error("WS error: %s", e)
```

### Section E — REST API + Entry Point

```python
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
```

- [ ] **Step 1: Create server.py** by assembling all five sections A–E in order into a single file.

- [ ] **Step 2: Verify import**

```bash
python3 -c "import server; print('server.py import OK')"
```

Expected: `server.py import OK`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: FastAPI server with WebSocket, Claude Haiku, ElevenLabs TTS, action dispatch"
```

---

## Task 7: Frontend — index.html + style.css

**Files:**

- Create: `frontend/src/index.html`
- Create: `frontend/src/style.css`

- [ ] **Step 1: Create frontend/src/index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="author" content="Taoufik — instagram.com/taoufik.ai" />
    <title>JARVIS</title>
    <link rel="stylesheet" href="./style.css" />
  </head>
  <body>
    <canvas id="orb-canvas"></canvas>
    <div id="ui">
      <div id="status">Click to begin</div>
      <div id="transcript"></div>
      <div id="response"></div>
    </div>
    <div id="settings-panel" class="hidden"></div>
    <button id="settings-btn" title="Settings">&#9881;</button>
    <script type="module" src="./main.ts"></script>
  </body>
</html>
```

- [ ] **Step 2: Create frontend/src/style.css**

```css
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  background: #000;
  color: #e0e0e0;
  font-family: "SF Mono", "Fira Code", monospace;
  overflow: hidden;
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

#orb-canvas {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
}

#ui {
  position: relative;
  z-index: 10;
  text-align: center;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px;
  max-width: 600px;
}

#status {
  font-size: 0.75rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #666;
  transition: color 0.3s;
}
#status.listening {
  color: #4af;
}
#status.thinking {
  color: #fa4;
}
#status.speaking {
  color: #4fa;
}
#status.error {
  color: #f44;
}

#transcript {
  font-size: 0.9rem;
  color: #aaa;
  min-height: 1.5em;
}
#response {
  font-size: 1rem;
  color: #e0e0e0;
  min-height: 2em;
  line-height: 1.6;
}

#settings-btn {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 20;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #999;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 1rem;
  transition: background 0.2s;
}
#settings-btn:hover {
  background: rgba(255, 255, 255, 0.12);
}

#settings-panel {
  position: fixed;
  inset: 0;
  z-index: 30;
  background: rgba(0, 0, 0, 0.92);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 32px;
}
#settings-panel.hidden {
  display: none;
}

.settings-label {
  font-size: 0.8rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  display: block;
  margin-bottom: 4px;
}

.settings-input {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #e0e0e0;
  border-radius: 6px;
  padding: 8px 12px;
  font-family: inherit;
  font-size: 0.9rem;
  width: 100%;
}

.settings-group {
  width: 100%;
  max-width: 400px;
}

#settings-close {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #999;
  border-radius: 8px;
  padding: 8px 20px;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.85rem;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.html frontend/src/style.css
git commit -m "feat: frontend HTML shell and dark CSS theme"
```

---

## Task 8: Frontend — ws.ts + voice.ts

**Files:**

- Create: `frontend/src/ws.ts`
- Create: `frontend/src/voice.ts`

- [ ] **Step 1: Create frontend/src/ws.ts**

```typescript
// ws.ts — WebSocket client with typed routing and auto-reconnect
type Handler = (msg: Record<string, unknown>) => void;
const handlers = new Map<string, Handler[]>();
let socket: WebSocket | null = null;
let delay = 1000;

export function on(type: string, h: Handler): void {
  if (!handlers.has(type)) handlers.set(type, []);
  handlers.get(type)!.push(h);
}

export function send(msg: Record<string, unknown>): void {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(msg));
}

function dispatch(type: string, msg: Record<string, unknown>): void {
  handlers.get(type)?.forEach((h) => h(msg));
  handlers.get("*")?.forEach((h) => h(msg));
}

export function connect(): void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${proto}://${location.host}/ws/voice`);

  socket.onopen = () => {
    delay = 1000;
    dispatch("connected", {});
  };
  socket.onclose = () => {
    dispatch("disconnected", {});
    setTimeout(() => {
      delay = Math.min(delay * 2, 30000);
      connect();
    }, delay);
  };
  socket.onerror = () => socket?.close();
  socket.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data as string) as Record<string, unknown>;
      dispatch((msg.type as string) || "unknown", msg);
    } catch {
      /* ignore */
    }
  };
}
```

- [ ] **Step 2: Create frontend/src/voice.ts**

```typescript
// voice.ts — Web Speech API capture + Web Audio playback queue
import { send } from "./ws.ts";

type LevelCb = (v: number) => void;
let recognition: SpeechRecognition | null = null;
let ctx: AudioContext | null = null;
let analyser: AnalyserNode | null = null;
const queue: AudioBuffer[] = [];
let playing = false;
let levelCb: LevelCb | null = null;
let rafId: number | null = null;

export function onLevel(cb: LevelCb): void {
  levelCb = cb;
}

function tickLevel(): void {
  if (!analyser || !levelCb) return;
  const data = new Uint8Array(analyser.frequencyBinCount);
  function loop(): void {
    analyser!.getByteFrequencyData(data);
    levelCb!(data.reduce((a, b) => a + b, 0) / data.length / 255);
    rafId = requestAnimationFrame(loop);
  }
  rafId = requestAnimationFrame(loop);
}

function stopLevel(): void {
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
}

async function getCtx(): Promise<AudioContext> {
  if (!ctx) {
    ctx = new AudioContext();
    analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.connect(ctx.destination);
  }
  return ctx;
}

function playNext(): void {
  if (!ctx || !analyser || queue.length === 0) {
    playing = false;
    stopLevel();
    window.dispatchEvent(new Event("jarvis:speech-end"));
    return;
  }
  playing = true;
  tickLevel();
  const src = ctx.createBufferSource();
  src.buffer = queue.shift()!;
  src.connect(analyser);
  src.onended = playNext;
  src.start();
}

export async function enqueueAudio(b64: string): Promise<void> {
  const actx = await getCtx();
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const buf = await actx.decodeAudioData(bytes.buffer);
  queue.push(buf);
  if (!playing) playNext();
}

export function startListening(): void {
  const SR =
    ((window as unknown as Record<string, unknown>)[
      "SpeechRecognition"
    ] as typeof SpeechRecognition) ??
    ((window as unknown as Record<string, unknown>)[
      "webkitSpeechRecognition"
    ] as typeof SpeechRecognition);
  if (!SR) {
    console.error("Web Speech API requires Chrome");
    return;
  }
  recognition?.stop();
  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "en-US";
  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript.trim();
    if (text) {
      window.dispatchEvent(
        new CustomEvent("jarvis:transcript", { detail: text }),
      );
      send({ type: "transcript", text });
    }
  };
  recognition.onend = () =>
    window.dispatchEvent(new Event("jarvis:recognition-end"));
  recognition.onerror = () =>
    window.dispatchEvent(new Event("jarvis:recognition-end"));
  recognition.start();
}

export function stopListening(): void {
  recognition?.stop();
  recognition = null;
}
export function initAudio(): Promise<AudioContext> {
  return getCtx();
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ws.ts frontend/src/voice.ts
git commit -m "feat: WebSocket client and voice input/output modules"
```

---

## Task 9: Frontend — orb.ts (Three.js particle orb)

**Files:**

- Create: `frontend/src/orb.ts`

Design: 3000 particles distributed on sphere surface via Fibonacci lattice. Each frame, a sin-based noise function perturbs each particle's distance from center based on elapsed time and current audio level. Color transitions smoothly between four state colors.

- [ ] **Step 1: Create frontend/src/orb.ts**

```typescript
// orb.ts — Three.js audio-reactive particle orb
import * as THREE from "three";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

const STATE_COLORS: Record<OrbState, THREE.Color> = {
  idle: new THREE.Color(0x1144aa),
  listening: new THREE.Color(0x44aaff),
  thinking: new THREE.Color(0xffaa44),
  speaking: new THREE.Color(0x44ffaa),
};

const N = 3000;
const R = 1.2;

let scene: THREE.Scene;
let camera: THREE.PerspectiveCamera;
let renderer: THREE.WebGLRenderer;
let pts: THREE.Points;
let base: Float32Array;
let live: Float32Array;
let cols: Float32Array;
let state: OrbState = "idle";
let level = 0;
let clock: THREE.Clock;

export function init(canvas: HTMLCanvasElement): void {
  clock = new THREE.Clock();
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(
    60,
    canvas.width / canvas.height,
    0.1,
    100,
  );
  camera.position.z = 4;

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x000000, 0);

  const geo = new THREE.BufferGeometry();
  base = new Float32Array(N * 3);
  live = new Float32Array(N * 3);
  cols = new Float32Array(N * 3);

  const phi = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N; i++) {
    const y = (1 - (i / (N - 1)) * 2) * R;
    const r = Math.sqrt(Math.max(R * R - y * y, 0));
    const t = phi * i;
    base[i * 3] = live[i * 3] = Math.cos(t) * r;
    base[i * 3 + 1] = live[i * 3 + 1] = y;
    base[i * 3 + 2] = live[i * 3 + 2] = Math.sin(t) * r;
  }

  geo.setAttribute("position", new THREE.BufferAttribute(live, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(cols, 3));

  pts = new THREE.Points(
    geo,
    new THREE.PointsMaterial({
      size: 0.012,
      vertexColors: true,
      transparent: true,
      opacity: 0.9,
      sizeAttenuation: true,
    }),
  );
  scene.add(pts);

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  requestAnimationFrame(tick);
}

function tick(): void {
  requestAnimationFrame(tick);
  const t = clock.getElapsedTime();
  const col = STATE_COLORS[state];

  const pulse = state === "idle" ? 0.04 * Math.sin(t * 1.2) : level * 0.5;

  for (let i = 0; i < N; i++) {
    const ox = base[i * 3],
      oy = base[i * 3 + 1],
      oz = base[i * 3 + 2];
    const noise =
      Math.sin(ox * 3 + t) * Math.cos(oy * 3 + t * 0.7) * 0.08 +
      pulse * Math.sin(i * 0.01 + t * 2);
    const s = 1 + noise;
    live[i * 3] = ox * s;
    live[i * 3 + 1] = oy * s;
    live[i * 3 + 2] = oz * s;
    const b = 0.7 + 0.3 * Math.abs(noise) + level * 0.3;
    cols[i * 3] = col.r * b;
    cols[i * 3 + 1] = col.g * b;
    cols[i * 3 + 2] = col.b * b;
  }

  (pts.geometry.attributes["position"] as THREE.BufferAttribute).needsUpdate =
    true;
  (pts.geometry.attributes["color"] as THREE.BufferAttribute).needsUpdate =
    true;
  pts.rotation.y = t * 0.1;
  pts.rotation.x = t * 0.04;
  renderer.render(scene, camera);
}

export function setState(s: OrbState): void {
  state = s;
}
export function setAudioLevel(v: number): void {
  level = v;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/orb.ts
git commit -m "feat: Three.js audio-reactive particle orb"
```

---

## Task 10: Frontend — main.ts + settings.ts

**Files:**

- Create: `frontend/src/main.ts`
- Create: `frontend/src/settings.ts`

Note: `settings.ts` uses `createElement` / `appendChild` exclusively — no `innerHTML` with dynamic content.

- [ ] **Step 1: Create frontend/src/main.ts**

```typescript
// main.ts — JARVIS frontend state machine
import { connect, on, send } from "./ws.ts";
import {
  startListening,
  stopListening,
  enqueueAudio,
  onLevel,
  initAudio,
} from "./voice.ts";
import { init as initOrb, setState, setAudioLevel } from "./orb.ts";
import { initSettings } from "./settings.ts";

type State = "idle" | "listening" | "thinking" | "speaking";

let state: State = "idle";
const statusEl = document.getElementById("status")!;
const transcriptEl = document.getElementById("transcript")!;
const responseEl = document.getElementById("response")!;

const STATUS_TEXT: Record<State, string> = {
  idle: "Click to begin",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

function transition(next: State): void {
  state = next;
  statusEl.textContent = STATUS_TEXT[next];
  statusEl.className = next === "idle" ? "" : next;
  setState(next);
}

function startSession(): void {
  if (state !== "idle") return;
  transition("listening");
  startListening();
}

on("connected", () => transition("idle"));
on("disconnected", () => {
  statusEl.textContent = "Reconnecting…";
  statusEl.className = "error";
});
on("thinking", () => {
  transition("thinking");
  stopListening();
});
on("text", (m) => {
  responseEl.textContent = (m["content"] as string) ?? "";
});
on("audio", (m) => {
  void enqueueAudio(m["data"] as string);
});
on("done", () => transition("idle"));
on("error", (m) => {
  statusEl.textContent = `Error: ${m["message"] as string}`;
  statusEl.className = "error";
});

window.addEventListener("jarvis:transcript", (e) => {
  transcriptEl.textContent = (e as CustomEvent<string>).detail;
});
window.addEventListener("jarvis:recognition-end", () => {
  if (state === "listening") send({ type: "abort" });
});
window.addEventListener("jarvis:speech-end", () => transition("idle"));

onLevel((v) => setAudioLevel(v));

window.addEventListener("DOMContentLoaded", async () => {
  const canvas = document.getElementById("orb-canvas") as HTMLCanvasElement;
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  initOrb(canvas);
  initSettings();
  connect();

  document.body.addEventListener("click", async (e) => {
    if ((e.target as HTMLElement).closest("#settings-panel, #settings-btn"))
      return;
    await initAudio();
    startSession();
  });
});
```

- [ ] **Step 2: Create frontend/src/settings.ts** (safe DOM, no innerHTML with user data)

```typescript
// settings.ts — Settings panel built with safe DOM methods
export function initSettings(): void {
  const panel = document.getElementById("settings-panel")!;
  const btn = document.getElementById("settings-btn")!;

  // Build heading
  const h2 = document.createElement("h2");
  h2.style.cssText =
    "font-size:1rem;letter-spacing:.2em;text-transform:uppercase;color:#888;";
  h2.textContent = "Settings";
  panel.appendChild(h2);

  // Build form fields
  const fields: {
    label: string;
    id: string;
    key: string;
    placeholder: string;
  }[] = [
    {
      label: "ElevenLabs Voice ID",
      id: "s-voice-id",
      key: "jarvis_voice_id",
      placeholder: "Leave blank for default (George)",
    },
    {
      label: "Your Name",
      id: "s-user-name",
      key: "jarvis_user_name",
      placeholder: "sir",
    },
    {
      label: "Backend URL",
      id: "s-backend-url",
      key: "jarvis_backend_url",
      placeholder: "https://localhost:8340",
    },
  ];

  const formWrap = document.createElement("div");
  formWrap.style.cssText =
    "display:flex;flex-direction:column;gap:12px;width:100%;max-width:400px;";

  fields.forEach(({ label, id, key, placeholder }) => {
    const group = document.createElement("div");
    group.className = "settings-group";

    const lbl = document.createElement("label");
    lbl.className = "settings-label";
    lbl.htmlFor = id;
    lbl.textContent = label;

    const inp = document.createElement("input");
    inp.type = "text";
    inp.id = id;
    inp.className = "settings-input";
    inp.placeholder = placeholder;

    const saved = localStorage.getItem(key);
    if (saved) inp.value = saved;
    inp.addEventListener("change", () => localStorage.setItem(key, inp.value));

    group.appendChild(lbl);
    group.appendChild(inp);
    formWrap.appendChild(group);
  });
  panel.appendChild(formWrap);

  const closeBtn = document.createElement("button");
  closeBtn.id = "settings-close";
  closeBtn.textContent = "Close";
  panel.appendChild(closeBtn);

  btn.addEventListener("click", () => panel.classList.remove("hidden"));
  closeBtn.addEventListener("click", () => panel.classList.add("hidden"));
  panel.addEventListener("click", (e) => {
    if (e.target === panel) panel.classList.add("hidden");
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/main.ts frontend/src/settings.ts
git commit -m "feat: frontend state machine and settings panel"
```

---

## Task 11: SSL Certs + Startup Script

**Files:**

- Create: `scripts/start.sh`

- [ ] **Step 1: Set up Python environment**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

- [ ] **Step 2: Copy and configure .env**

```bash
cp .env.example .env
# Edit .env: fill in ANTHROPIC_API_KEY and ELEVENLABS_API_KEY
```

- [ ] **Step 3: Install frontend deps**

```bash
cd frontend && npm install && cd ..
```

- [ ] **Step 4: Generate SSL certificate**

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem \
  -days 365 -nodes -subj '/CN=localhost'
```

- [ ] **Step 5: Create scripts/start.sh**

```bash
#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
python server.py &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"
cd frontend && npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"
cd ..
echo "JARVIS starting. Open http://localhost:5173 in Chrome."
wait
```

```bash
chmod +x scripts/start.sh
git add scripts/start.sh
git commit -m "chore: startup script and SSL setup instructions"
```

---

## Task 12: End-to-End Verification

- [ ] **Step 1: Start backend**

```bash
source .venv/bin/activate && python server.py
```

Expected console line: `JARVIS server · Built from CLAUDE.md by Taoufik — instagram.com/taoufik.ai`
Listening on `https://localhost:8340`.

- [ ] **Step 2: Start frontend**

In a second terminal:

```bash
cd frontend && npm run dev
```

Expected: `Local: http://localhost:5173/`

- [ ] **Step 3: Trust SSL in Chrome**

Navigate to `https://localhost:8340/api/health` → accept the self-signed cert warning.
Expected response: `{"ok":true}`

- [ ] **Step 4: Open app**

```bash
open http://localhost:5173
```

- [ ] **Step 5: Test golden path**

1. Click anywhere on the page → status → `Listening…`, orb turns blue-green
2. Say "Good morning, JARVIS"
3. Status cycles: `Thinking…` (yellow) → `Speaking…` (teal) → `Click to begin`
4. British voice response plays through speakers
5. Response text appears below orb

- [ ] **Step 6: Test system action**

Say: "What's on my calendar today?"
Expected: JARVIS reads Apple Calendar and narrates upcoming events.

- [ ] **Step 7: Test REST API**

```bash
curl -k https://localhost:8340/api/status
# {"status":"online","version":"1.0.0"}
curl -k https://localhost:8340/api/memory/facts
# {"facts":[]}
```

- [ ] **Step 8: Final commit + completion message**

```bash
git add -A
git commit -m "chore: complete JARVIS voice assistant build"
```

Print:

```log
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  JARVIS is ready.

  Built with this CLAUDE.md by Taoufik
  instagram.com/taoufik.ai
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Troubleshooting

| Symptom                       | Fix                                                       |
| ----------------------------- | --------------------------------------------------------- |
| Mic blocked in Chrome         | `chrome://settings/content/microphone` → allow localhost  |
| Web Speech API not working    | Must use Google Chrome (not Safari or Firefox)            |
| SSL cert error                | Visit `https://localhost:8340` first → Advanced → Proceed |
| ElevenLabs 401                | Check `ELEVENLABS_API_KEY` in `.env`                      |
| AppleScript permission denied | System Settings → Privacy → Automation → allow Terminal   |
| `python-dotenv` not found     | `pip install python-dotenv`                               |
| `playwright install` slow     | `playwright install chromium --with-deps`                 |
