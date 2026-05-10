# JARVIS — Structure Audit & Alignment Fixes

**Context:** The initial build (voice assistant, multilingual support, LLM router) is complete. This plan captures discrepancies found during a backend/frontend structure review against `CLAUDE.md` and `README.md`, and lists the minimal fixes needed to make the codebase fully aligned with its own documentation.

---

## Audit Summary

### What is well-aligned ✅

| Area                                                   | Status                                         |
| ------------------------------------------------------ | ---------------------------------------------- |
| `llm_router.py` Protocol + providers + routing table   | Matches README spec exactly                    |
| Logging format (`task=voice provider=openai ...`)      | Matches README example                         |
| `server.py` bilingual prompt + `_detect_lang()`        | Implemented per design                         |
| `server.py` `eleven_multilingual_v2` model             | Implemented                                    |
| `voice.ts` `ko-KR` default + localStorage lang key     | Implemented                                    |
| `wake.ts` Korean+English patterns                      | Match README wake phrase list                  |
| `session.ts` `canStartWakeListening` guards            | Match README wake lifecycle                    |
| `main.ts` wake-phrase state machine                    | No-audio-done → resume listening works         |
| `settings.ts` language selector, `ko-KR` default       | Implemented                                    |
| `planner.py` uses `LLMRouter`                          | Uses router, not direct Anthropic client       |
| `pyproject.toml` `openai>=1.0.0,<2.0`                  | Added correctly                                |
| `tests/test_llm_router.py` coverage                    | Router, task routing, Korean keywords, logging |
| `DEFAULT_ELEVENLABS_VOICE_ID = "UgBBYS2sOqTuMpoF3BR0"` | Matches README                                 |

---

## Discrepancies Found

### 1. `pyproject.toml` — missing `python-dotenv` (CRITICAL)

`server.py:21` calls `from dotenv import load_dotenv` but `python-dotenv` is not in `pyproject.toml` dependencies.

**Fix:** Add `python-dotenv>=1.0.0,<2.0` to `[project] dependencies`.

**File:** `pyproject.toml`

---

### 2. `main.py` — dead `uv init` stub (HIGH)

`main.py` contains only `def main(): print("Hello from jarvis!")`. It is not referenced anywhere, not mentioned in `CLAUDE.md` or `README.md`, and conflicts with `server.py` as the backend entry point.

**Fix:** Delete `main.py`.

**File:** `main.py`

---

### 3. `settings.ts` — two no-op fields (HIGH)

`jarvis_backend_url` and `jarvis_user_name` are rendered as settings inputs and saved to `localStorage`, but:

- `ws.ts` hardcodes `${location.host}/ws/voice` — never reads `jarvis_backend_url`
- `USER_NAME` is read from `.env` server-side — never reads `jarvis_user_name` from browser

These fields display false affordance to the user.

**Fix:** Remove both fields from `settings.ts`. The `jarvis_recognition_lang` language selector (already implemented) is the only meaningful browser-side setting.

**File:** `frontend/src/settings.ts`

---

### 4. `server.py:118` — deprecated `asyncio.get_event_loop()` (MEDIUM)

`asyncio.get_event_loop()` is deprecated in Python 3.10+ and raises a DeprecationWarning in 3.12/3.13. Since `synthesize()` is called from within a running async context, use `asyncio.get_running_loop()` instead.

**Fix:** `loop = asyncio.get_event_loop()` → `loop = asyncio.get_running_loop()`

**File:** `server.py:118`

---

### 5. `.env.example` + `README.md` — unimplemented wake-key vars (MEDIUM)

`.env.example` lists three env vars that no code uses:

```env
JARVIS_WAKE_KEY=
JARVIS_WAKE_URL=https://localhost:8340/api/wake
JARVIS_CLAP_THRESHOLD=0.30
```

`README.md`'s Configuration section also lists these. Wake detection is done entirely in the browser via `wake.ts` + Web Speech API — there is no server-side clap/key detection.

**Fix:** Remove these three vars from `.env.example`. Remove or mark them "not yet implemented" in `README.md`.

**Files:** `.env.example`, `README.md`

---

### 6. `.gitignore` — untracked build transcript (LOW)

`2026-04-22-215421-jarvis-voice-ai-assistant-build-from-scratch.txt` is untracked (per `git status`). It is a build log artifact that should not be committed.

**Fix:** Add `*.txt` or the specific filename to `.gitignore`.

**File:** `.gitignore`

---

## Critical Files

| File                       | Change                                                        |
| -------------------------- | ------------------------------------------------------------- |
| `pyproject.toml`           | Add `python-dotenv>=1.0.0,<2.0`                               |
| `main.py`                  | Delete                                                        |
| `frontend/src/settings.ts` | Remove `jarvis_backend_url` and `jarvis_user_name` fields     |
| `server.py`                | Line 118: `get_event_loop()` → `get_running_loop()`           |
| `.env.example`             | Remove 3 unimplemented wake-key vars                          |
| `README.md`                | Remove unimplemented wake-key vars from Configuration section |
| `.gitignore`               | Add entry for build transcript `.txt` file                    |

---

## Verification

```bash
# Backend: all deps resolvable, imports clean, tests pass
uv sync
uv run python -m compileall server.py planner.py llm_router.py
uv run pytest

# Frontend: TypeScript clean, wake + session tests pass
cd frontend
pnpm build
pnpm exec tsc --module NodeNext --moduleResolution NodeNext --target ES2020 --outDir /tmp/jarvis-wake-tests src/wake.ts test/wake.test.ts
node /tmp/jarvis-wake-tests/test/wake.test.js
pnpm exec tsc --module NodeNext --moduleResolution NodeNext --target ES2020 --outDir /tmp/jarvis-session-tests src/session.ts test/session.test.ts
node /tmp/jarvis-session-tests/test/session.test.js
```

Expected: no errors, all tests pass. `python-dotenv` resolves without error in `uv sync`.
