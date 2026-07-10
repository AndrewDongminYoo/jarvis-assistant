# Core

JARVIS: voice-first macOS assistant. Python FastAPI backend + Vite/TS/Three.js frontend.
Git root is the project dir (NOT `$HOME`); `~/CLAUDE.md` is a separate dotfiles repo — ignore it here.

## Sources of truth

- `README.md` = runtime/product behavior (wake phrases, default ElevenLabs voice ID, routing observability, setup). Update it in the SAME change as behavior changes.
- `CLAUDE.md` (project root) = agent guidance + cross-file architecture that no single module reveals.
- `JARVIS.md` = private source prompt, may hold secrets, gitignored — never commit, never make authoritative.

## Backend source map (project root, flat `.py` files)

- `server.py` — FastAPI app, `/ws/voice` WebSocket, bounded action loop (`handle_message`, `_run_action_loop`, `_dispatch_action_result`, `_task_type`; `MAX_STEPS=5`, `ACTION_RE`).
- `llm_router.py` — provider routing per task (`voice`/`work`/`plan`/`narrate`). See `mem:tech_stack`.
- `memory.py` — SQLite/FTS persistence. `safety.py` — action `classify` (safe/confirm). `planner.py`, `work_mode.py`.
- macOS integrations via AppleScript: `calendar_access.py`, `mail_access.py`, `notes_access.py`, `actions.py`.
- Accessibility (pyobjc): `gui_actions.py`. Anthropic Computer Use fallback: `computer_use.py`. `browser.py` (Playwright).

## Frontend source map (`frontend/src/`)

- State machine: `main.ts` → `wake.ts` (PURE parser, keep side-effect-free + tested) → `session.ts` (idle→armed→thinking→speaking→idle).
- `ws.ts`/`voice.ts` WebSocket + Web Speech API; `orb.ts`/`clap.ts` Three.js visuals; `settings.ts`.

## Invariants

- Action-tag changes touch parser + dispatcher + README action list TOGETHER.
- WS outbound order per turn: `thinking` → optional `step` → `text` → `audio` (base64, 16 KiB chunks) → `done` | `error`. `done` always re-arms wake even if `audio` absent (macOS `say` fallback).
- Never log transcripts, prompt bodies, API keys, or full model responses (see `mem:conventions`).

## Detail memories

`mem:tech_stack`, `mem:suggested_commands`, `mem:conventions`, `mem:task_completion`.
Onboarding/style rules for memories themselves: `mem:memory_maintenance`.
