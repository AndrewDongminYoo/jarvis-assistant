# Voice Command Guide

A practical reference for what to say to JARVIS. The system prompt teaches the
LLM to recognize these intents and emit the matching `[ACTION:...]` tag — the
backend strips the tag from the spoken response, runs the integration, then
narrates the result. You don't say the tags out loud; you say the natural
phrase and the LLM picks the tag.

For the wire-level grammar of every tag, see the **Action Tags** table in
`README.md`. This document is the user-facing companion: what to _speak_.

---

## Waking JARVIS

| Trigger                      | Effect                                                                     |
| ---------------------------- | -------------------------------------------------------------------------- |
| Say `Jarvis` alone           | Arms the assistant — next utterance is sent as the command                 |
| Say `Jarvis, <command>`      | Strips the wake phrase and dispatches the command in one turn              |
| `Hey Jarvis` / `헤이 자비스` | Same as above, common alternates                                           |
| `자비스 …`                   | Korean wake phrase                                                         |
| Double-clap, first today     | Plays the morning Today Report (calendar + mail summary in butler voice)   |
| Double-clap, again today     | Arms the assistant for the next utterance (same as saying the wake phrase) |

The first click on the page is required once per session to unlock microphone
and audio permissions. After that, voice and clap are the only inputs you need.

---

## What you can say

Phrases below are examples — the LLM matches intent, not exact wording. Mix
Korean and English freely; JARVIS responds in the same mix.

### Calendar

- "What's on my calendar?" / "오늘 일정 알려줘"
- "Anything tomorrow?" / "내일 뭐 있어?"
- "What's happening this week?"

### Mail

- "Read my mail" / "메일 확인해줘"
- "Any new emails?"
- "Search mail for invoice" / "송장 메일 찾아줘"
- "Find emails from Sarah"

### Notes

- "List my notes" / "노트 목록 보여줘"
- "Read the Tokyo trip note"
- "Create a note titled `Groceries` with content `milk, eggs, bread`"

### Tasks

- "Add a task: pick up dry cleaning"
- "What tasks do I have?" / "할 일 뭐 있어?"
- "Mark task 5 done" / "5번 작업 완료"

### Memory

- "Remember that I prefer black coffee" / "나 블랙커피 좋아하는 거 기억해줘"
- "Forget fact 3"
- "What did I say about Tokyo?" — recalls past conversation turns

### Planning

JARVIS's planner runs in two stages.

1. Say something like "Plan a Tokyo trip for October" / "도쿄 여행 계획 짜줘".
   JARVIS asks 3–5 clarifying questions out loud.
2. Answer the questions in your next utterance. JARVIS produces a numbered
   plan.

### Browse & search

- "Browse `https://news.ycombinator.com`"
- "Search the web for the new SwiftUI APIs"
- "What's the latest on `<topic>`?"

> Requires `uv run playwright install` once. If chromium is missing, JARVIS
> reports a soft failure and falls back to a verbal "couldn't browse" message
> instead of crashing the turn.

### Code & work mode

When you ask JARVIS to _build_, _code_, _implement_, or use the Korean
equivalents (`작성`, `만들어`, `구현`), the request is routed to the larger
`work` model tier (`claude-sonnet`, `gpt-4o`, `gemini-pro`) and dispatched to
a background `claude -p` session.

- "Build a Python CLI that downloads RSS feeds"
- "Implement OAuth callback handling for the auth router"
- "Refactor the calendar parser to use EventKit" / "캘린더 파서 EventKit으로 구현해줘"

JARVIS confirms verbally and the session runs detached — you can ask for the
output later.

### System actions

- "Open Terminal"
- "Run `git status` in Terminal"
- (System-level browser actions live under "Browse & search" above.)

---

## Cancelling and steering

| You want to…                      | Do this                                                                       |
| --------------------------------- | ----------------------------------------------------------------------------- |
| Cut JARVIS off mid-sentence       | Click anywhere on the page — sends `abort` over the websocket                 |
| Make JARVIS stop without quitting | Stay silent past the recognition timeout; it auto-resumes wake listening      |
| Switch recognition language       | Open the settings panel and change the language dropdown (`ko-KR` by default) |

---

## When something goes wrong

| Symptom                                 | Likely cause                                           | Fix                                                                   |
| --------------------------------------- | ------------------------------------------------------ | --------------------------------------------------------------------- |
| Calendar action returns "couldn't read" | AppleScript `whose` scan over many calendars           | Set `CALENDAR_NAMES` in `.env` to the calendar display names you want |
| Browse / Search actions fail            | Playwright chromium not installed                      | Run `uv run playwright install` once                                  |
| No audio playback, only text            | ElevenLabs error or quota                              | macOS `say` fallback runs server-side — check the page or your plan   |
| Wake phrase isn't being detected        | Recognition language mismatch                          | Open settings, switch between `ko-KR` / `en-US`                       |
| Today Report fires every double-clap    | localStorage was cleared or browser is in private mode | Use the regular page; the date key persists day-to-day                |
| Server logs `LLM provider failed`       | API key missing, network blip, rate limit              | Add a second provider in `.env` for automatic fallback                |

---

## Tips

- One utterance is faster than two — `"Jarvis, what's on my calendar?"` beats
  saying `"Jarvis"`, waiting for the listening cue, then giving the command.
- The system prompt encourages JARVIS to limit itself to 2–3 sentences, so
  you'll get a brisk butler-style answer rather than a paragraph.
- Conversation memory persists across server restarts — what you told JARVIS
  yesterday is still in context today, including planning sessions in flight.
- Stored facts (`REMEMBER`) get re-injected into the system prompt every turn,
  so they steer responses indefinitely. Use `FORGET` when something stops
  being true.
