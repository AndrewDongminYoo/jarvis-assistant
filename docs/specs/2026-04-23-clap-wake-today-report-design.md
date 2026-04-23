# Clap Wake + Today Report — Design Spec

**Date:** 2026-04-23
**Status:** Approved

## Context

JARVIS currently wakes only via Web Speech API text phrases ("Jarvis", "자비스"). This adds a secondary wake path: two hand claps detected by the browser's Web Audio API. The first double-clap of each calendar day triggers a Today Report (calendar + mail briefing). All subsequent double-claps that day arm JARVIS for the next voice command.

---

## Architecture

```text
Microphone (getUserMedia)
    └─ MediaStreamSource
           └─ AnalyserNode (clap-specific, separate from voice.ts playback analyser)
                  └─ RMS polling (setInterval ~60fps)
                         └─ clap state machine
                                └─ jarvis:double-clap (CustomEvent on window)
                                       └─ main.ts handler
                                              ├─ first of day → send {type:"today-report"} via WebSocket
                                              └─ otherwise   → arm state → startWakeListening()
```

---

## Section 1: Clap Detection (`frontend/src/clap.ts`)

### Pure functions (testable, no side effects)

```typescript
function isClap(rms: number, durationMs: number): boolean;
function isDoubleClap(firstMs: number, secondMs: number): boolean;
```

| Parameter              | Value | Rationale                               |
| ---------------------- | ----- | --------------------------------------- |
| `THRESHOLD`            | 0.25  | RMS above this = peak start             |
| `CLAP_MAX_MS`          | 150   | Peak longer than this = voice, not clap |
| `DOUBLE_WINDOW_MIN_MS` | 80    | Below this = single peak artifact       |
| `DOUBLE_WINDOW_MAX_MS` | 800   | Above this = two separate claps         |
| `COOLDOWN_MS`          | 1000  | Ignore window after double-clap fires   |

### Clap state machine

```plaintext
idle
 └─ RMS > THRESHOLD, held < CLAP_MAX_MS
       → first_clap (save timestamp t1)
           ├─ next peak within [MIN, MAX] window → fire jarvis:double-clap → cooldown → idle
           └─ window expires → idle (reset)
```

### AudioContext sharing

`startClapDetection(audioCtx: AudioContext)` receives the AudioContext from `initAudio()` (voice.ts). A new `AnalyserNode` and `MediaStreamSource` are created on this shared context — avoids the browser's AudioContext instance limit. The mic stream is obtained via `navigator.mediaDevices.getUserMedia({ audio: true })`.

### Error handling

`getUserMedia` 실패(권한 거부, 기기 없음) 시 `console.warn`만 출력하고 조용히 종료 — 앱 나머지 기능에 영향 없음.

### Exported API

```typescript
export async function startClapDetection(audioCtx: AudioContext): Promise<void>;
export function stopClapDetection(): void;
// pure exports for testing:
export { isClap, isDoubleClap };
```

---

## Section 2: State Integration (`frontend/src/main.ts`)

### "First of day" logic

- localStorage key: `jarvis_today_report_date`
- Value format: `new Date().toDateString()` (e.g. `"Thu Apr 23 2026"`)
- No timer needed — date comparison at event time is sufficient

### Event handler

```typescript
window.addEventListener("jarvis:double-clap", () => {
  if (!activated) return;
  if (state === "thinking" || state === "speaking") return;

  const today = new Date().toDateString();
  if (localStorage.getItem("jarvis_today_report_date") !== today) {
    localStorage.setItem("jarvis_today_report_date", today);
    send({ type: "today-report" });
    transition("thinking");
  } else {
    armed = true;
    transition("listening", "Listening…");
    startWakeListening();
  }
});
```

### Lifecycle

`startClapDetection(audioCtx)` is called once in the `DOMContentLoaded` handler, immediately after `await initAudio()` (first click). Detection runs for the entire app lifetime — no start/stop per interaction.

---

## Section 3: Server (`server.py`)

### WebSocket message routing (addition)

```python
elif msg.get("type") == "today-report":
    await handle_today_report(ws)
```

### `handle_today_report(ws)`

```python
async def handle_today_report(ws: WebSocket) -> None:
    await ws.send_json({"type": "thinking"})

    from calendar_access import get_events_summary
    from mail_access import get_mail_summary

    events = get_events_summary()   # uses background cache
    mail   = get_mail_summary()

    spoken = await _router.complete(
        task="narrate",
        messages=[{
            "role": "user",
            "content": (
                f"[CALENDAR]\n{events}\n\n[MAIL]\n{mail}\n\n"
                "Brief morning summary in 2-3 sentences. British butler style."
            ),
        }],
        system=_build_system_prompt(),
        max_tokens=200,
    )

    _mem.add_exchange("assistant", spoken)
    await ws.send_json({"type": "text", "content": spoken})

    audio = await synthesize(spoken)
    if audio:
        chunk_size = 16384
        for i in range(0, len(audio), chunk_size):
            encoded = base64.b64encode(audio[i : i + chunk_size]).decode()
            await ws.send_json({"type": "audio", "data": encoded})

    await ws.send_json({"type": "done"})
```

Uses existing `narrate` router route (Anthropic Haiku → OpenAI → Gemini fallback). No new REST endpoint.

---

## Section 4: Tests

### `frontend/test/clap.test.ts` (pure function unit tests)

| Test                | Input               | Expected               |
| ------------------- | ------------------- | ---------------------- |
| strong short peak   | rms=0.30, dur=80ms  | `isClap` → true        |
| too quiet           | rms=0.10, dur=80ms  | `isClap` → false       |
| too long (voice)    | rms=0.40, dur=200ms | `isClap` → false       |
| valid double        | t1=0, t2=400ms      | `isDoubleClap` → true  |
| too slow            | t1=0, t2=900ms      | `isDoubleClap` → false |
| too fast (artifact) | t1=0, t2=30ms       | `isDoubleClap` → false |

### Manual integration checklist

| Scenario                      | Expected                           |
| ----------------------------- | ---------------------------------- |
| First double-clap of day      | Today Report narrated              |
| Second double-clap same day   | "Listening…" → next utterance sent |
| After midnight, first clap    | Today Report again                 |
| Clap during thinking/speaking | Ignored                            |
| Single clap only              | Ignored                            |

---

## File Map

| File                         | Change                                                        |
| ---------------------------- | ------------------------------------------------------------- |
| `frontend/src/clap.ts`       | New — clap detector module                                    |
| `frontend/test/clap.test.ts` | New — pure function tests                                     |
| `frontend/src/main.ts`       | Add `jarvis:double-clap` handler, call `startClapDetection`   |
| `server.py`                  | Add `today-report` WebSocket branch + `handle_today_report()` |

No changes to: `voice.ts`, `wake.ts`, `session.ts`, `ws.ts`, `orb.ts`, `llm_router.py`

---

## Verification

```bash
# Backend
uv run python -m compileall server.py
uv run pytest

# Frontend
cd frontend
pnpm build
pnpm exec tsc --module NodeNext --moduleResolution NodeNext --target ES2020 \
  --outDir /tmp/jarvis-clap-tests src/clap.ts test/clap.test.ts
node /tmp/jarvis-clap-tests/test/clap.test.js
```
