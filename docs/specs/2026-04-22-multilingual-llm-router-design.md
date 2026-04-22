# JARVIS — Multilingual Support + LLM Router Design

**Date:** 2026-04-22  
**Status:** Approved

## Goal

1. Allow the user to speak Korean, English, or a natural mix of both — JARVIS recognizes the input and responds in the same language/mix.
2. Abstract the LLM backend behind a router that supports task-based provider selection and automatic fallback across Anthropic, OpenAI, and Google Gemini.

---

## Part 1: Multilingual Support

### Problem

`recognition.lang = "en-US"` in `voice.ts` blocks non-English speech recognition. ElevenLabs `eleven_turbo_v2` degrades on Korean text. The system prompt has no instruction for language-matching.

### Solution

**Speech recognition (`frontend/src/voice.ts`)**

- Change default `recognition.lang` from `"en-US"` to `"ko-KR"`.
- Chrome's `ko-KR` recognition handles natural Korean–English code-switching well.
- Read the lang value from `localStorage.getItem("jarvis_recognition_lang")` with `"ko-KR"` as fallback.
- `startListening()` uses the stored value each call.

**Settings panel (`frontend/src/settings.ts`)**

- Add a language `<select>` element with options: `ko-KR`, `en-US`, `ja-JP`, `zh-CN`.
- Stored under key `jarvis_recognition_lang` in localStorage.

**TTS — ElevenLabs (`server.py`)**

- Switch `model_id` from `"eleven_turbo_v2"` to `"eleven_multilingual_v2"`.
- No other ElevenLabs change needed; the same George voice handles Korean naturally with this model.

**TTS — macOS fallback (`server.py`)**

```python
def _detect_lang(text: str) -> str:
    return "ko" if any("가" <= c <= "힣" for c in text) else "en"

def _tts_macos(text: str) -> None:
    voice = "Yuna" if _detect_lang(text) == "ko" else "Daniel"
    subprocess.run(["say", "-v", voice, text], timeout=60)
```

**System prompt (`server.py` — `_build_system_prompt`)**
Add to the personality block:

> "Respond in the user's language. Mix Korean and English naturally — like a bilingual speaker would. 사용자가 한국어로 말하면 한국어로, 영어면 영어로, 혼용하면 자연스럽게 혼용하여 답하세요."

---

## Part 2: LLM Router

### Problem

`server.py` is tightly coupled to `AsyncAnthropic`. There is no fallback when Anthropic is unavailable, no way to route code-heavy tasks to a stronger model, and no way to add new providers without editing the core server logic.

### Solution

New file `llm_router.py` with a `LLMProvider` protocol and a `LLMRouter` that selects providers by task type and falls back automatically.

### Provider Abstraction

```python
class LLMProvider(Protocol):
    name: str
    async def complete(
        self,
        messages: list[dict],
        system: str,
        max_tokens: int,
    ) -> str: ...
```

Three concrete providers:

| Class               | SDK                                      | Default model               |
| ------------------- | ---------------------------------------- | --------------------------- |
| `AnthropicProvider` | `anthropic` (already installed)          | `claude-haiku-4-5-20251001` |
| `OpenAIProvider`    | `openai>=1.0`                            | `gpt-4o-mini`               |
| `GeminiProvider`    | `openai>=1.0` via OpenAI-compat endpoint | `gemini-2.0-flash`          |

`GeminiProvider` uses Google's OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`) so no extra SDK is required.

### Task Routing

```
"voice"   → [AnthropicProvider(haiku), OpenAIProvider(gpt-4o-mini), GeminiProvider(flash)]
"work"    → [OpenAIProvider(gpt-4o), AnthropicProvider(sonnet), GeminiProvider(pro)]
"narrate" → [AnthropicProvider(haiku), OpenAIProvider(gpt-4o-mini), GeminiProvider(flash)]
"plan"    → [AnthropicProvider(haiku), OpenAIProvider(gpt-4o-mini), GeminiProvider(flash)]
```

Providers not configured (missing API key) are skipped silently at startup.

### Fallback Logic

```python
async def complete(self, task: str, messages, system, max_tokens) -> str:
    errors = []
    for provider in self.routes.get(task, self.routes["voice"]):
        try:
            return await provider.complete(messages, system, max_tokens)
        except Exception as e:
            log.warning("Provider %s failed: %s", provider.name, e)
            errors.append(e)
    raise RuntimeError(f"All providers failed: {errors}")
```

### Task Type Determination (server.py)

Determined before the first LLM call based on the transcript + context:

```python
def _task_type(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in ("build", "code", "implement", "작성", "만들어", "구현")):
        return "work"
    if any(k in lower for k in ("plan", "steps", "outline", "계획", "단계")):
        return "plan"
    return "voice"
```

Follow-up narration calls always use `"narrate"`.

### Environment Variables

`.env.example` additions:

```env
# LLM Provider API Keys
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=AI...

# Provider priority per task (comma-separated; defaults shown)
# JARVIS_VOICE_PROVIDERS=anthropic,openai,gemini
# JARVIS_WORK_PROVIDERS=openai,anthropic,gemini
# JARVIS_PLAN_PROVIDERS=anthropic,openai,gemini
# JARVIS_NARRATE_PROVIDERS=anthropic,openai,gemini
```

### Dependency

`pyproject.toml` / `requirements.txt`: add `openai>=1.0.0,<2.0`.

---

## Files Changed

| File                       | Type   | Change                                                                   |
| -------------------------- | ------ | ------------------------------------------------------------------------ |
| `llm_router.py`            | New    | Provider protocol + 3 concrete providers + LLMRouter                     |
| `server.py`                | Modify | Use `LLMRouter`, multilingual TTS, updated system prompt, `_task_type()` |
| `frontend/src/voice.ts`    | Modify | Dynamic `recognition.lang` from localStorage                             |
| `frontend/src/settings.ts` | Modify | Add language `<select>` field                                            |
| `.env.example`             | Modify | New provider keys + routing env vars                                     |
| `pyproject.toml`           | Modify | Add `openai>=1.0.0,<2.0`                                                 |

---

## Verification

1. Start server + frontend dev server
2. Open `http://localhost:5173` in Chrome
3. Click → speak Korean → confirm Korean transcript appears, Korean audio plays back
4. Speak English → confirm English response
5. Speak mixed Korean/English sentence → confirm natural mixed response
6. Remove `ANTHROPIC_API_KEY` temporarily → confirm fallback to OpenAI (if configured)
7. Check server logs: `Provider anthropic failed` → `Provider openai succeeded`
