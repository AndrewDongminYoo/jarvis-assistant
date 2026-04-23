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

Frontend checks:

```bash
cd frontend
pnpm build
pnpm exec tsc --module NodeNext --moduleResolution NodeNext --target ES2020 --outDir /tmp/jarvis-wake-tests src/wake.ts test/wake.test.ts
node /tmp/jarvis-wake-tests/test/wake.test.js
pnpm exec tsc --module NodeNext --moduleResolution NodeNext --target ES2020 --outDir /tmp/jarvis-session-tests src/session.ts test/session.test.ts
node /tmp/jarvis-session-tests/test/session.test.js
```

Repository lint:

```bash
trunk check
```

Run locally:

```bash
scripts/start.sh
```

Then open `http://localhost:5173` in Chrome.

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
