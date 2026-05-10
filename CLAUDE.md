# CLAUDE.md

This file is for coding agents working in this repository. `README.md` is the
runtime source of truth for product behavior. `JARVIS.md` is a local/private
source prompt that may contain sensitive values and must not be committed.

## Project Shape

JARVIS is a voice-first macOS assistant.

- Backend: FastAPI in `server.py`
- LLM routing: `llm_router.py`
- Memory: SQLite/FTS in `memory.py`
- macOS integrations: AppleScript helpers in `calendar_access.py`,
  `mail_access.py`, `notes_access.py`, and `actions.py`
- Work/planning integrations: `work_mode.py`, `planner.py`
- Frontend: Vite + TypeScript + Three.js under `frontend/src`
- Browser speech: Web Speech API in Chrome
- TTS: ElevenLabs first, macOS `say` fallback

## Source Of Truth

Before changing behavior, read `README.md`, especially:

- Voice activation and wake phrases
- Default ElevenLabs voice ID
- LLM routing observability
- Setup and verification commands

If behavior changes, update `README.md` in the same change. Do not make
`JARVIS.md` authoritative again; it is intentionally private and ignored.

## Security Rules

- Do not commit `.env`, `JARVIS.md`, database files, cert/key files, or API keys.
- Use placeholder values in docs, for example `your-anthropic-key-here`.
- Do not log user transcripts, prompt bodies, API keys, or full model responses.
- LLM logs should include task/provider/model, success or failure, latency, and
  response length only.

## Development Commands

Backend checks:

```bash
uv run pytest
uv run python -m compileall server.py planner.py llm_router.py
```

Run a single backend test (by node ID or `-k` filter):

```bash
uv run pytest tests/test_llm_router.py::test_router_falls_back_on_failure
uv run pytest -k "fallback" -x
```

Frontend checks:

```bash
cd frontend
pnpm build
pnpm exec tsc --module NodeNext --moduleResolution NodeNext --target ES2020 --outDir /tmp/jarvis-wake-tests src/wake.ts test/wake.test.ts
node /tmp/jarvis-wake-tests/test/wake.test.js
pnpm exec tsc --module NodeNext --moduleResolution NodeNext --target ES2020 --outDir /tmp/jarvis-session-tests src/session.ts test/session.test.ts
node /tmp/jarvis-session-tests/test/session.test.js
```

Frontend tests are plain `node` scripts compiled by `tsc` — there is no Jest/Vitest runner. Each `test/*.test.ts` file is self-executing; run a single one by compiling+executing only that pair.

Repository lint:

```bash
trunk check
```

Run locally:

```bash
scripts/start.sh
```

Then open `http://localhost:5173` in Chrome. The backend listens on `PORT` (default `8340`) and serves the built frontend from `/app` when `frontend/dist/` exists; in dev, Vite serves `5173` and proxies are not used — the frontend connects to the backend WebSocket directly.

## Cross-File Architecture

These flows require reading multiple files at once and are not derivable from any single module:

### Two-pass action dispatch (`server.py` ↔ `llm_router.py`)

`handle_message` runs the LLM **twice** for any response that contains an action tag:

1. First pass — `_task_type(text)` classifies the user utterance into `voice` / `work` / `plan` by keyword (English + Korean: `build|code|구현` → work, `plan|계획` → plan, otherwise `voice`). The router picks the task-specific model.
2. The response is scanned by `ACTION_RE` for `[ACTION:KIND:...]`. If found, `dispatch_action` runs the corresponding integration (calendar, mail, notes, terminal, browse, search, work, plan, remember, forget, recall, task) and produces a system result string.
3. Second pass — when an action produced output, the router is called again with `task="narrate"`, feeding back the original assistant turn + a `[SYSTEM RESULT]` user turn, asking for a 1–2 sentence spoken summary. The `narrate` task uses cheaper/faster models on purpose (`claude-haiku`, `gpt-4o-mini`, `gemini-2.0-flash`).

When changing system-prompt action tags in `server.py`, the parser, the dispatcher, and the README action list must move together.

### LLM routing knobs (`llm_router.py`)

- Tasks are fixed: `voice`, `work`, `plan`, `narrate`. Per-task model maps live in `ANTHROPIC_MODELS` / `OPENAI_MODELS` / `GEMINI_MODELS` — **`work` is the only task that uses the large-context tier** (sonnet / gpt-4o / gemini-pro).
- Provider order per task is overridable via env (`JARVIS_VOICE_PROVIDERS` etc.). Missing API keys → provider silently dropped from that route.
- `LLMRouter.from_env` is the production entry; tests use the `routes=` kwarg to inject fakes (see `tests/test_llm_router.py`).

### WebSocket protocol (`server.py` ↔ `frontend/src/ws.ts`, `voice.ts`)

`/ws/voice` is a JSON-message channel. Inbound types: `transcript` (`{text}`), `ping`. Outbound types in order per turn: `thinking` → `text` → `audio` (base64-chunked, 16 KiB) → `done`, or `error`. Audio chunks may be absent if ElevenLabs failed and macOS `say` was used server-side; the frontend must still treat `done` as the cue to resume wake listening.

### Frontend state machine (`main.ts` → `wake.ts` → `session.ts`)

`wake.ts` is a **pure** parser: given a transcript, it returns either "wake-only" (arm the assistant) or "wake + command" (immediate dispatch). `session.ts` owns transitions between `idle → armed → thinking → speaking → idle`. Recognition is paused while `thinking`/`speaking` and re-armed on `done`. Keep `wake.ts` pure and side-effect-free so its unit test stays meaningful.

## Implementation Notes

- The app requires one initial click to unlock browser microphone/audio
  permissions. After that, wake listening should continue automatically.
- Wake phrases are parsed in `frontend/src/wake.ts`.
- Frontend listening state transitions are guarded by `frontend/src/session.ts`.
- Keep wake parsing as a pure function with lightweight tests.
- Keep LLM routing behavior covered with `tests/test_llm_router.py`.
- The default ElevenLabs voice ID must stay aligned with `README.md`.

## Attribution

The original JARVIS build prompt credited Taoufik at
`instagram.com/taoufik.ai`. Preserve existing attribution comments and metadata
that are already present in generated files.
