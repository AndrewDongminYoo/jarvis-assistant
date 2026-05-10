# JARVIS

JARVIS is a voice-first macOS assistant. The user speaks in Chrome, the browser
sends recognized text to a FastAPI backend over WebSocket, the backend routes
the request to an LLM provider, and JARVIS responds with text plus speech.

This file is the source of truth for runtime behavior. `JARVIS.md` is a
local/private source prompt that may contain sensitive values and must not be
committed.

## Architecture

```text
Microphone -> Web Speech API -> WebSocket -> FastAPI -> LLM Router -> TTS
                                               |
                                               v
                         AppleScript, browser, planner, and work integrations
```

| Layer              | Tech                                              |
| ------------------ | ------------------------------------------------- |
| Backend            | FastAPI, Python, WebSocket                        |
| Frontend           | Vite, TypeScript, Three.js                        |
| Speech input       | Chrome Web Speech API                             |
| LLM routing        | Anthropic, OpenAI, Gemini through `llm_router.py` |
| TTS                | ElevenLabs, with macOS `say` fallback             |
| Storage            | SQLite with FTS5                                  |
| macOS integrations | AppleScript helpers                               |

## Runtime Contract

### Voice Activation

JARVIS is a persistent voice assistant after the user grants microphone
permission in Chrome. The first click or tap on the page activates microphone
and audio permissions. After that, the user summons the assistant by voice
instead of clicking for every request.

Supported wake phrases:

- `Jarvis`
- `Hey Jarvis`
- `자비스`
- `헤이 자비스`

When the wake phrase and request are in one utterance, for example
`Jarvis, what's on my calendar?`, the frontend strips the wake phrase and sends
the remaining command to `/ws/voice`.

When the user says only the wake phrase, the frontend enters an armed listening
state and sends the next final utterance as the command.

JARVIS pauses listening while thinking or speaking, then resumes wake listening
automatically. If TTS fails and no browser audio is returned, the frontend still
returns to wake listening when the backend sends `done`.

### Default Voice

ElevenLabs is the primary TTS provider. The default British "George" voice ID
is:

```env
ELEVENLABS_VOICE_ID=UgBBYS2sOqTuMpoF3BR0
```

If `ELEVENLABS_VOICE_ID` is not set, the server must use that ID. If
ElevenLabs fails, macOS `say` remains the fallback.

### LLM Routing

The backend routes LLM requests through `llm_router.py`.
Each user turn is classified into one of four tasks before routing:

| Task      | Trigger                                                                   | Anthropic           | OpenAI        | Gemini             |
| --------- | ------------------------------------------------------------------------- | ------------------- | ------------- | ------------------ |
| `voice`   | Default for any utterance                                                 | `claude-haiku-4-5`  | `gpt-4o-mini` | `gemini-2.0-flash` |
| `work`    | Utterance contains `build`, `code`, `implement`, `작성`, `만들어`, `구현` | `claude-sonnet-4-5` | `gpt-4o`      | `gemini-2.0-pro`   |
| `plan`    | Utterance contains `plan`, `steps`, `outline`, `계획`, `단계`             | `claude-haiku-4-5`  | `gpt-4o-mini` | `gemini-2.0-flash` |
| `narrate` | Internal — second pass after an action runs (see Action Tags)             | `claude-haiku-4-5`  | `gpt-4o-mini` | `gemini-2.0-flash` |

Default provider order per task:

| Task      | Providers                 |
| --------- | ------------------------- |
| `voice`   | Anthropic, OpenAI, Gemini |
| `work`    | OpenAI, Anthropic, Gemini |
| `plan`    | Anthropic, OpenAI, Gemini |
| `narrate` | Anthropic, OpenAI, Gemini |

Providers without API keys are skipped. Failed providers are logged and the
router falls back to the next configured provider.

Server logs must show:

- task type
- provider name
- model name
- whether the provider succeeded or failed
- response latency and response length on success

Server logs must not include user transcripts, prompt bodies, API keys, or full
model responses.

Example:

```text
INFO:jarvis.llm_router:LLM request task=voice provider=openai model=gpt-4o-mini
INFO:jarvis.llm_router:LLM response task=voice provider=openai model=gpt-4o-mini duration_ms=842 chars=57
```

### Action Tags

The system prompt instructs the LLM to embed at most one action tag per
response when system access is needed. The backend strips the tag from spoken
output, runs the integration, then re-asks the router (`narrate` task) for a
1–2 sentence spoken summary of the result.

| Tag                                    | Effect                                       |
| -------------------------------------- | -------------------------------------------- |
| `[ACTION:CALENDAR]`                    | Upcoming events from Apple Calendar          |
| `[ACTION:MAIL]`                        | Unread mail summary from Apple Mail          |
| `[ACTION:MAIL:SEARCH:query]`           | Search mail by subject/sender                |
| `[ACTION:NOTES:LIST]`                  | List Apple Notes titles                      |
| `[ACTION:NOTES:READ:title]`            | Read a note body                             |
| `[ACTION:NOTES:CREATE:title::content]` | Create a new note                            |
| `[ACTION:TERMINAL:command]`            | Open Terminal and run a command              |
| `[ACTION:BROWSE:url]`                  | Browse a URL via Playwright                  |
| `[ACTION:SEARCH:query]`                | Web search summary                           |
| `[ACTION:WORK:task]`                   | Dispatch a task to Claude Code               |
| `[ACTION:PLAN:description]`            | Start a planning session with clarifying Qs  |
| `[ACTION:PLAN_ANSWER:task::answers]`   | Produce numbered plan once user has answered |
| `[ACTION:REMEMBER:fact]`               | Persist a user fact to memory                |
| `[ACTION:FORGET:fact_id]`              | Delete a stored fact by ID                   |
| `[ACTION:RECALL:query]`                | Full-text search prior conversation          |
| `[ACTION:TASK:CREATE:title]`           | Add a pending task                           |
| `[ACTION:TASK:LIST]`                   | List pending tasks                           |
| `[ACTION:TASK:DONE:task_id]`           | Mark a task as done                          |

Stored facts are injected back into the system prompt on every turn, so the
assistant remains personalized across sessions.

### WebSocket Protocol

The frontend connects to `/ws/voice`. All messages are JSON.

Inbound (client → server):

| Type           | Payload    | Purpose                                   |
| -------------- | ---------- | ----------------------------------------- |
| `transcript`   | `{ text }` | A finalized recognized utterance          |
| `today-report` | —          | Trigger the morning calendar+mail summary |
| `abort`        | —          | Cancel the in-flight handler, if any      |
| `ping`         | —          | Liveness check                            |

Outbound (server → client) per turn, in order:

| Type       | Payload       | Notes                                           |
| ---------- | ------------- | ----------------------------------------------- |
| `thinking` | —             | Sent immediately on receipt of a transcript     |
| `text`     | `{ content }` | Final spoken text (action tags stripped)        |
| `audio`    | `{ data }`    | Base64 MP3 chunk, 16 KiB; zero or more frames   |
| `done`     | —             | Turn complete — frontend resumes wake listening |
| `error`    | `{ message }` | LLM/router failure; no `audio`/`done` follows   |
| `pong`     | —             | Reply to `ping`                                 |

`audio` may be omitted if ElevenLabs failed and the macOS `say` fallback ran
server-side. The frontend must therefore treat `done` — not the last `audio`
frame — as the signal to re-arm wake listening.

## REST API

| Method   | Path                         | Purpose                         |
| -------- | ---------------------------- | ------------------------------- |
| `GET`    | `/api/status`                | Service status and version      |
| `GET`    | `/api/health`                | Liveness probe                  |
| `GET`    | `/api/memory/facts`          | List persisted user facts       |
| `POST`   | `/api/memory/fact`           | Add a fact: `{ "fact": "..." }` |
| `DELETE` | `/api/memory/fact/{fact_id}` | Remove a fact by ID             |
| `GET`    | `/api/memory/tasks`          | List planner tasks              |

The built frontend is mounted at `/app` when `frontend/dist/` exists.

## Configuration

Create `.env` from `.env.example` and fill in the keys you use.

```env
ANTHROPIC_API_KEY=your-anthropic-key-here
OPENAI_API_KEY=your-openai-key-here
GEMINI_API_KEY=your-gemini-key-here
ELEVENLABS_API_KEY=your-elevenlabs-key-here

# Optional. Defaults to George.
ELEVENLABS_VOICE_ID=UgBBYS2sOqTuMpoF3BR0

# Optional provider priority overrides (comma-separated).
JARVIS_VOICE_PROVIDERS=anthropic,openai,gemini
JARVIS_WORK_PROVIDERS=openai,anthropic,gemini
JARVIS_PLAN_PROVIDERS=anthropic,openai,gemini
JARVIS_NARRATE_PROVIDERS=anthropic,openai,gemini

# Optional.
USER_NAME=Andrew
CALENDAR_ACCOUNTS=user@example.com

```

Do not commit `.env`, `JARVIS.md`, local database files, or generated cert/key
files.

## Run

Start both backend and frontend:

```bash
scripts/start.sh
```

Open Chrome:

```text
http://localhost:5173
```

Use the app:

1. Click the page once to grant microphone/audio permissions.
2. Say `Jarvis` or `자비스`.
3. Give a command, or say the wake phrase and command in one utterance.

Backend only:

```bash
python server.py
```

The backend listens on `PORT` (default `8340`). If `cert.pem` and `key.pem`
exist in the project root, it serves HTTPS; otherwise plain HTTP.

Frontend only:

```bash
cd frontend
pnpm dev
```

## Verification

Run backend tests:

```bash
uv run pytest
uv run python -m compileall server.py planner.py llm_router.py
```

Run frontend checks:

```bash
cd frontend
pnpm build
pnpm exec tsc --module NodeNext --moduleResolution NodeNext --target ES2020 --outDir /tmp/jarvis-wake-tests src/wake.ts test/wake.test.ts
node /tmp/jarvis-wake-tests/test/wake.test.js
pnpm exec tsc --module NodeNext --moduleResolution NodeNext --target ES2020 --outDir /tmp/jarvis-session-tests src/session.ts test/session.test.ts
node /tmp/jarvis-session-tests/test/session.test.js
```

Run repository lint:

```bash
trunk check
```

## File Map

```text
server.py                  FastAPI app, WebSocket protocol, actions, TTS
llm_router.py              Provider routing and fallback by task
planner.py                 Planning module using the shared router
memory.py                  SQLite memory and facts
calendar_access.py         Apple Calendar access
mail_access.py             Apple Mail access
notes_access.py            Apple Notes access
actions.py                 macOS system actions
browser.py                 Playwright browsing/search helpers
work_mode.py               Claude Code work sessions
frontend/src/main.ts       Frontend state machine
frontend/src/voice.ts      Web Speech API and audio playback
frontend/src/wake.ts       Wake phrase parser
frontend/src/session.ts    Wake listening state guards
frontend/src/ws.ts         WebSocket client
frontend/src/orb.ts        Three.js orb visualization
frontend/src/settings.ts   Settings panel
```

## Attribution

The original JARVIS build prompt credited Taoufik at
`instagram.com/taoufik.ai`. Existing attribution comments and metadata should be
preserved.
