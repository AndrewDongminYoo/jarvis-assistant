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

Default route priority:

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

## Configuration

Create `.env` from `.env.example` and fill in the keys you use.

```env
ANTHROPIC_API_KEY=your-anthropic-key-here
OPENAI_API_KEY=your-openai-key-here
GEMINI_API_KEY=your-gemini-key-here
ELEVENLABS_API_KEY=your-elevenlabs-key-here

# Optional. Defaults to George.
ELEVENLABS_VOICE_ID=UgBBYS2sOqTuMpoF3BR0

# Optional provider priority overrides.
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
