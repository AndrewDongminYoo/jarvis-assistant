# JARVIS General Agent — Design

Status: Draft
Date: 2026-05-11
Owner: Dongmin

## Goal

Evolve JARVIS from a voice-first, single-shot assistant into a voice-first
**general agent** that can drive the browser, terminal, and arbitrary macOS apps
through short multi-step plans, while keeping the existing voice UX and the
current action-tag dispatch architecture intact.

Inspiration: UI-TARS-desktop. JARVIS keeps its current AppleScript and
high-level integrations as the fast path, and adds a GUI-grounded path for
arbitrary apps.

## Non-Goals

- Replacing the existing `[ACTION:KIND:args]` system. New capabilities are
  additive tags, not a rewrite.
- Long-horizon autonomous agents (10+ steps). Loops are bounded by
  `MAX_STEPS = 5`.
- Self-hosted GUI grounding models (UI-TARS-7B, etc.). All vision-based GUI
  control uses Anthropic Computer Use.
- Background/headless operation. The assistant runs interactively against the
  currently focused user session.

## Decisions

| Axis          | Decision                                                                                                 |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| Primary scope | Balanced general agent — browser, macOS apps, terminal                                                   |
| GUI engine    | Hybrid: AppleScript / Accessibility for known apps, Claude Computer Use for arbitrary apps               |
| Autonomy      | Short multi-step, `MAX_STEPS = 5`, natural termination when LLM emits no action                          |
| Safety        | Voice confirmation for risky actions only; read/explore is free                                          |
| Approach      | Approach A — extend action system with GUI tags and generalize 2-pass dispatch into a bounded micro-loop |

## Architecture

### Module Responsibilities

| Module                  | Responsibility                                                                                                                                     | External deps                              |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `actions.py` (existing) | AppleScript high-level actions: calendar, mail, notes, Terminal, Chrome activate                                                                   | `osascript`                                |
| `gui_actions.py` (new)  | macOS Accessibility API: dump active app UI tree, click by role+label, type, scroll, send keystrokes. Known-app fast path.                         | `pyobjc` (`ApplicationServices`, `Quartz`) |
| `computer_use.py` (new) | Wrapper around Anthropic `computer_20250124` tool. Captures screenshots, runs click/type/key actions, exchanges one step at a time with the model. | `anthropic`, `Quartz` for screenshots      |
| `safety.py` (new)       | Pure-function classifier: `SAFE` / `CONFIRM` / `BLOCKED`. Includes `is_affirmative` / `is_negative` helpers for confirmation replies.              | none                                       |
| `server.py` (modified)  | Routing, WebSocket protocol, micro-loop. Knows action _kinds_ but not their internals.                                                             | the above                                  |

`gui_actions.py` and `computer_use.py` are not unified behind a single abstract
interface. They are reached through distinct action tags (`UI:*` and
`COMPUTER:*`), which makes the LLM's choice explicit and keeps routing logic
out of code.

### New Action Tags

Existing tags are unchanged. New tags:

```plaintext
# Known-app fast path (Accessibility-based)
[ACTION:UI:OBSERVE]              # dump pruned UI tree of the frontmost app
[ACTION:UI:FOCUS:app_name]       # activate an app
[ACTION:UI:CLICK:role::label]    # e.g. button::Send, link::Pull requests
[ACTION:UI:TYPE:text]            # type into the currently focused field
[ACTION:UI:KEY:cmd+t]            # send a keystroke
[ACTION:UI:SCROLL:dir::amount]   # dir ∈ up|down|left|right, amount in lines

# Arbitrary-app path (vision-grounded)
[ACTION:COMPUTER:goal]           # delegate a short goal to Computer Use
                                 # computer_use.py runs its own internal
                                 # screenshot↔action loop, bounded by its own
                                 # step budget, and returns a final result
                                 # string to the outer loop
```

The system prompt is updated to teach the model:

- Prefer `UI:*` for apps where Accessibility is reliable (Chrome, Slack,
  Notes, Mail, Terminal, Finder).
- Use `COMPUTER:*` only when `UI:*` is insufficient (Figma, design tools,
  games, web canvases) or when `UI:OBSERVE` returns an unrecognized structure.
- Always start a multi-step task with `UI:OBSERVE` or `UI:FOCUS` if the active
  app is uncertain.

### Micro ReAct Loop

`handle_message` generalizes the current single dispatch + narrate into a
bounded loop. The narrate pass is unchanged in spirit — it remains the final
spoken summary on cheap models.

```python
MAX_STEPS = 5
turn_history = [user_msg]
steps: list[tuple[str, str]] = []

for step in range(MAX_STEPS):
    raw = await router.complete(task=task, history=turn_history)
    m = ACTION_RE.search(raw)
    if not m:
        break  # natural termination — model produced a final answer

    action = m.group(1)
    if steps and steps[-1][0] == action:
        # repeat-detection: model is stuck. Break out and narrate.
        break

    decision = safety.classify(action)
    if decision is Decision.BLOCKED:
        result = f"blocked: {safety.reason(action)}"
    elif decision is Decision.CONFIRM:
        _pending[ws_id] = PendingAction(action, turn_history, time.time())
        return await emit_confirm_prompt(action, ws)
    else:
        result = await dispatch_action(action)

    steps.append((action, result))
    turn_history.append(assistant(raw))
    turn_history.append(system_result(result))

await narrate(turn_history, ws)
```

Termination conditions, in order: (1) model emits no action tag, (2) repeated
action detected, (3) `MAX_STEPS` reached, (4) pending confirmation returned.

## Safety Model

### Classification

`safety.classify(action: str) -> Decision` is pure and table-driven.

| Action family                                                                                                                  | Default | Argument-based promotion                                                                                                        |
| ------------------------------------------------------------------------------------------------------------------------------ | ------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `CALENDAR`, `MAIL` (read), `NOTES:LIST/READ`, `BROWSE`, `SEARCH`, `RECALL`, `TASK:LIST`, `UI:OBSERVE/FOCUS/SCROLL`, `REMEMBER` | SAFE    | —                                                                                                                               |
| `NOTES:CREATE`, `TASK:CREATE/DONE`, `FORGET`, `UI:TYPE`                                                                        | CONFIRM | —                                                                                                                               |
| `UI:CLICK:role::label`                                                                                                         | SAFE    | label matches one of `{Send, Delete, Buy, Confirm, Pay, Submit, Remove, Trash, Sign out, Discard}` (case-insensitive) → CONFIRM |
| `TERMINAL:cmd`                                                                                                                 | CONFIRM | cmd matches one of `sudo`, `rm -rf`, `:(){`, redirect into a system path, `curl ... \| sh` → BLOCKED                            |
| `MAIL:SEND:*`                                                                                                                  | CONFIRM | —                                                                                                                               |
| `COMPUTER:goal`                                                                                                                | CONFIRM | goal contains payment, transfer, bank, or password keywords (en+ko) → BLOCKED                                                   |
| `WORK:task`                                                                                                                    | CONFIRM | —                                                                                                                               |

Rules live in `safety.py` as module-level constants. Externalizing to a
`safety_rules.toml` file is a later option if the rules grow; not in scope
now.

### Pending Action Pattern

```python
@dataclass
class PendingAction:
    action: str          # raw tag content, e.g. "MAIL:SEND:anna@x.com::Hi"
    history: list[Msg]
    asked_at: float
    expires_in: float = 30.0

    def expired(self) -> bool:
        return time.time() - self.asked_at > self.expires_in
```

State lives in `server.py` as `_pending: dict[str, PendingAction]`, keyed by
the WebSocket session id. A session has at most one pending action at a time.
If a new pending is set while one already exists, the older one is overwritten
(the user has moved on).

At the top of `handle_message`:

```python
pending = _pending.pop(ws_id, None)
if pending and not pending.expired():
    if safety.is_affirmative(user_text):
        return await execute_confirmed(pending, ws)
    if safety.is_negative(user_text):
        return await narrate_cancelled(pending, ws)
    # neither — drop the pending and fall through to normal handling
```

`is_affirmative` / `is_negative` are pure functions matching a small set of
English + Korean tokens (e.g. `{"yes", "yeah", "go", "ok", "응", "그래", "해"}`
and `{"no", "cancel", "stop", "아니", "취소", "하지마"}`). Behavior is unit-
tested.

## Data Flow

A representative multi-step turn:

```log
voice "내 PR 보여줘"
  → STT → transcript
  → handle_message
    → no pending action
    → _task_type → "voice"
    → router.complete (1) → "[ACTION:UI:FOCUS:Google Chrome]"
    → safety: SAFE → gui_actions.focus → ok
    → router.complete (2) → "[ACTION:BROWSE:https://github.com/pulls]"
    → safety: SAFE → browser.browse_url → page text
    → router.complete (3) → "오픈 PR 3건이에요: A, B, C." (no action tag)
    → loop exits naturally
    → narrate pass (cheap model) → spoken summary
  → WebSocket: thinking → text → audio → done
```

A risky single action:

```log
voice "Anna에게 메일 보내줘, '점심 같이 먹을래?'"
  → handle_message
    → _task_type → "voice"
    → router.complete (1) → "[ACTION:MAIL:SEND:anna@x.com::점심 같이 먹을래?]"
    → safety: CONFIRM → store pending, narrate "Anna에게 보낼게요, 진행할까요?"
    → WebSocket: thinking → text → audio → done
voice "응"
  → handle_message
    → pending found, is_affirmative → execute_confirmed
    → mail send → "sent"
    → narrate → "보냈어요."
```

### WebSocket Protocol Changes

Existing outbound types (`thinking`, `text`, `audio`, `done`, `error`) are
unchanged. One optional addition:

```json
{ "type": "step", "kind": "BROWSE", "summary": "github.com/pulls 열고 있어요" }
```

`step` messages are emitted between loop iterations to let the frontend show
progress. They are not spoken. Frontends that ignore the new type continue to
work — the protocol stays backward compatible.

## Error Handling

| Case                                | Behavior                                                                                                                      |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `dispatch_action` raises            | Result is `f"error: {msg}"`, fed back to the LLM. The LLM may retry or apologize via narrate.                                 |
| Accessibility permission missing    | `gui_actions` raises a typed error. Server narrates: "JARVIS가 시스템 환경설정 > 개인정보 보호 > 접근성에서 권한이 필요해요." |
| Same action repeated twice in a row | Loop breaks; narrate "여기서 막혔어요."                                                                                       |
| `MAX_STEPS` reached                 | Loop breaks; narrate "여러 단계가 필요해서 멈췄어요. 다시 시도해 주세요."                                                     |
| Computer Use API failure            | Result is an error string; the LLM may fall back to `BROWSE`/`SEARCH` or apologize.                                           |
| Pending action expired              | Silently dropped on the next turn; normal flow proceeds.                                                                      |

## Testing Strategy

| Target                                  | File                         | Approach                                                                                                                                                                                            |
| --------------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `safety.classify`                       | `tests/test_safety.py`       | Table-based parameterized cases (≥30 pairs) covering each row of the rule table                                                                                                                     |
| `safety.is_affirmative` / `is_negative` | `tests/test_safety.py`       | Korean + English token tables                                                                                                                                                                       |
| Micro-loop (`handle_message`)           | `tests/test_server_loop.py`  | Fake router injected via existing `LLMRouter(routes=...)` pattern. Scenarios: 0-step, 2-step, CONFIRM, MAX_STEPS, repeat-detected, pending-then-affirmative, pending-then-negative, pending-expired |
| `gui_actions` AX tree parser            | `tests/test_gui_actions.py`  | Pre-captured AX dump fixtures parsed offline. Live AX calls are split into an integration test that is skipped by default                                                                           |
| `computer_use` wrapper                  | `tests/test_computer_use.py` | Fake `anthropic` client; dummy 1×1 PIL image for screenshots                                                                                                                                        |
| Frontend                                | unchanged                    | Existing `wake.ts` / `session.ts` tests still pass — `done` is still the cue to re-arm                                                                                                              |

Manual verification checklist (not automated):

- Wake → "Chrome 열어줘" → focus works
- Wake → "Anna에게 메일 보내줘, ..." → confirm prompt → "응" → sent
- Wake → "rm -rf /" → BLOCKED narrate, no execution
- Wake → "내 PR 보여줘" → 2-step loop, single spoken summary
- AX permission revoked → narrate prompts for permission

## Rollout

1. Land `safety.py` and tests first — pure code, no system side effects.
2. Refactor `handle_message` into the micro-loop with `MAX_STEPS = 1`. All
   existing tests must still pass. This is the riskiest single change.
3. Bump `MAX_STEPS = 5` once the loop is stable.
4. Add `gui_actions.py` with `UI:OBSERVE` and `UI:FOCUS` only. Iterate on AX
   tree pruning until output fits comfortably in the model context.
5. Add `UI:CLICK` / `UI:TYPE` / `UI:KEY` / `UI:SCROLL`.
6. Add `computer_use.py` and the `[ACTION:COMPUTER:goal]` tag.
7. Add the optional `step` WebSocket message and a small frontend indicator.

Each step is a separate PR with green tests before moving on.

## Open Questions

- Should `UI:OBSERVE` cache the last observation for one turn to save a round
  trip when the model wants to act on what it just saw? (Defer until step 4
  reveals whether it's needed.)
- What is the right `MAX_STEPS` value? Start at 5; revisit after dogfooding.
- Should the `step` message also carry latency for observability? (Defer; the
  existing LLM router logging already captures per-call latency.)
