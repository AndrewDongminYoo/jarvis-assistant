# JARVIS Multilingual LLM Router — Implementation Plan

JARVIS needs multilingual voice support and an extensible LLM backend. The implementation will move Anthropic-specific calls behind a task-aware router, wire both server conversation and planner calls through that router, and add Korean-first speech recognition with multilingual TTS.

## Scope

- In: multilingual speech recognition setting, ElevenLabs/macOS TTS language handling, `llm_router.py`, `server.py` and `planner.py` router migration, provider fallback, `.env.example`, dependency updates, pytest coverage.
- Out: model-name environment overrides, streaming LLM responses, non-Chrome speech recognition guarantees, full settings UI redesign.

## Action items

- [ ] Add `openai>=1.0.0,<2.0` and `pytest` to `pyproject.toml`, then refresh `uv.lock` with `uv sync`.
- [ ] Add pytest coverage for router fallback, all-provider failure, route priority parsing, missing-key provider exclusion, unknown-task fallback, `_task_type()`, and planner routing.
- [ ] Add `llm_router.py` with `LLMProvider`, `AnthropicProvider`, `OpenAIProvider`, `GeminiProvider`, and `LLMRouter`.
- [ ] Use fixed model defaults from the spec: Anthropic Haiku for voice/plan/narrate, Anthropic Sonnet for work, OpenAI `gpt-4o-mini` for voice/plan/narrate, OpenAI `gpt-4o` for work, Gemini Flash for voice/plan/narrate, and Gemini Pro for work.
- [ ] Parse `JARVIS_VOICE_PROVIDERS`, `JARVIS_WORK_PROVIDERS`, `JARVIS_PLAN_PROVIDERS`, and `JARVIS_NARRATE_PROVIDERS`; skip providers without required API keys.
- [ ] Refactor `server.py` to remove the direct `AsyncAnthropic` client, route first responses by `_task_type(text)`, and route action-result narration with `task="narrate"`.
- [ ] Refactor `planner.py` so `get_clarifying_questions()` and `generate_plan()` use the shared router with `task="plan"`.
- [ ] Update `server.py` prompt and TTS: add user-language matching instructions, switch ElevenLabs to `eleven_multilingual_v2`, and select macOS `Yuna` for Korean or `Daniel` otherwise.
- [ ] Update `frontend/src/voice.ts` so `startListening()` reads `jarvis_recognition_lang` from localStorage each call, defaulting to `ko-KR`.
- [ ] Update `frontend/src/settings.ts` with a language `<select>` for `ko-KR`, `en-US`, `ja-JP`, and `zh-CN`.
- [ ] Update `.env.example` with optional OpenAI/Gemini keys and provider route variables.
- [ ] Run `uv run pytest`, `uv run python -m compileall server.py planner.py llm_router.py`, `cd frontend && pnpm build`, and `trunk check` where available.
- [ ] Manually QA in Chrome via `scripts/start.sh`: Korean speech, English speech, mixed speech, settings changes, Korean TTS, macOS fallback voice, and provider fallback by starting without Anthropic.

## Open questions

- None. User decisions: include `planner.py` in router migration, keep model names fixed to the spec defaults, and use `pytest` where it is the best fit.
