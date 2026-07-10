# Tech Stack

## Backend

- Python `>=3.13` (`.python-version`), package manager **uv** (`uv.lock`, `pyproject.toml`).
- FastAPI + uvicorn[standard] + websockets; pydantic v2; httpx.
- LLM SDKs: `anthropic` (<1.0), `openai` (<2.0); Gemini via httpx. Playwright for browser.
- macOS-native: `pyobjc-framework-ApplicationServices` + `-Cocoa` (Accessibility APIs in `gui_actions.py`); AppleScript via subprocess elsewhere.
- Audio: `sounddevice` + `numpy`. Config: `python-dotenv` (`.env`, template `.env.example`).
- Tests: `pytest` (dev group). Default `addopts = -m 'not macos'` — `macos` marker = live Accessibility-permission integration tests, skipped by default.

## LLM routing (`llm_router.py`)

- Fixed tasks: `voice`, `work`, `plan`, `narrate`. Per-provider model maps: `ANTHROPIC_MODELS`/`OPENAI_MODELS`/`GEMINI_MODELS`.
- `work` is the ONLY task on the large-context tier (sonnet / gpt-4o / gemini-pro). `narrate` uses cheap/fast tier (haiku / gpt-4o-mini / gemini-2.0-flash) on purpose.
- Provider order overridable per task via env (`JARVIS_VOICE_PROVIDERS`, etc.). Missing API key → provider silently dropped.
- `LLMRouter.from_env` = prod entry; tests inject fakes via `routes=` kwarg.

## Frontend (`frontend/`)

- Vite 8 + TypeScript 6 + Three.js 0.184. Package manager **pnpm@10.33.0** (pinned in package.json).
- No Jest/Vitest: `test/*.test.ts` are self-executing plain node scripts compiled by `tsc`. See `mem:suggested_commands`.

## TTS / speech

- TTS: ElevenLabs first, macOS `say` fallback. Browser STT: Web Speech API (Chrome only).
