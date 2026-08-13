# Security Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the local privileged WebSocket, confirmation parser, connection-owned pending state, and Korean safety classification without adding authentication or changing the local-only deployment model.

**Architecture:** Add small pure validation and matching helpers beside the existing FastAPI and safety code, then apply them at the WebSocket and pending-action boundaries.
Keep production state connection-scoped through an explicit generated identifier, preserve existing public action tags, and update runtime documentation with the behavior change.

**Tech Stack:** Python 3.13, FastAPI WebSocket, pytest, standard-library `urllib.parse` and `uuid`.

## Global Constraints

- Preserve the loopback-only, single-user deployment contract.
- Add no dependency and no remote-access support.
- Use failing-test-first proof for every production behavior change.
- Keep `README.md` and `CLAUDE.md` synchronized with runtime behavior.
- Do not modify unrelated review findings in this branch.

---

### Task 1: WebSocket Host and Origin Boundary

**Files:**

- Modify: `server.py`
- Test: `tests/test_server.py`

**Interfaces:**

- Produces: `_is_allowed_websocket_request(host: str, origin: str | None) -> bool`.
- Consumes: `PORT`, the fixed Vite port `5173`, and `WebSocket.headers`.

- [x] **Step 1: Write failing boundary tests**

Add table-driven tests with literal expected values for loopback hosts, allowed local origins, an absent origin, a foreign origin, `Origin: null`, a non-loopback host, malformed values, and a local origin on an unrelated port.
Add `TestClient` WebSocket handshake tests that observe rejection for `Origin: https://evil.example` and a successful `ping`/`pong` exchange for an approved local origin.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run python -m pytest tests/test_server.py -k "websocket_request or untrusted_origin or trusted_local_origin" -v
```

Expected: failures because the validator does not exist and the current endpoint accepts the hostile origin.

- [x] **Step 3: Implement the minimal validator and pre-accept guard**

Parse hosts and origins with `urllib.parse.urlsplit`.
Allow only `localhost`, `127.0.0.1`, and `::1` hosts.
Allow a missing origin after the host passes, or an `http`/`https` loopback origin on port `5173` or `PORT`.
Raise ASGI policy-violation code `1008` before calling `accept()`; under Uvicorn this becomes an HTTP `403` handshake denial rather than a WebSocket close frame.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2 and require every selected test to pass.

### Task 2: Explicit Confirmation Parsing

**Files:**

- Modify: `safety.py`
- Test: `tests/test_safety.py`

**Interfaces:**

- Produces: existing `is_affirmative(text: str) -> bool` and `is_negative(text: str) -> bool` with strict semantics.
- Consumes: no I/O or server state.

- [x] **Step 1: Write failing parser regression tests**

Prove that `I need to go now` is not affirmative, `don't do it` is negative and not affirmative, and `okay, but don't send it` is negative and not affirmative.
Retain positive tests for exact English and Korean phrases plus punctuation and whitespace normalization.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run python -m pytest tests/test_safety.py -k "affirmative or negative" -v
```

Expected: the three regression cases fail against the current token-anywhere parser.

- [x] **Step 3: Implement minimal strict matching**

Normalize case, whitespace, and surrounding punctuation.
Match affirmatives only as complete accepted phrases.
Detect explicit negative words and phrases before the server considers affirmation.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2 and require every selected test to pass.

### Task 3: Ambiguous Confirmation Retention

**Files:**

- Modify: `server.py`
- Test: `tests/test_server_loop.py`

**Interfaces:**

- Consumes: strict `safety.is_negative()` and `safety.is_affirmative()` results.
- Produces: an ambiguous reply restores the same `PendingAction` without dispatching or extending its expiration.

- [x] **Step 1: Write the failing server-loop test**

Seed `_pending` with a dangerous action, send `I need to go now`, and assert that the dispatcher is not called, the same object remains under the same key with the original `asked_at`, and the response requests an explicit yes or no.

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv run python -m pytest tests/test_server_loop.py -k "ambiguous_confirmation" -v
```

Expected: failure because the current handler drops pending state and routes the utterance as a new request.

- [x] **Step 3: Implement minimal pending restoration**

Restore the popped, unexpired pending object when neither detector matches.
Send a short bilingual clarification, synthesize it, emit `done`, and return without calling the router or dispatcher.

- [x] **Step 4: Run the focused test and adjacent confirmation tests**

Run:

```bash
uv run python -m pytest tests/test_server_loop.py -k "pending or confirmation" -v
```

Expected: all selected pending and confirmation tests pass.

### Task 4: Connection-Owned Pending Lifecycle

**Files:**

- Modify: `server.py`
- Test: `tests/test_server_pending.py`
- Test: `tests/test_server.py`

**Interfaces:**

- Produces: `_new_connection_id() -> str` and `handle_message(ws, text, connection_id=None)`.
- Consumes: the generated identifier in `ws_voice()` and `_pending` registry.

- [x] **Step 1: Write failing connection lifecycle tests**

Assert two generated IDs differ.
Drive `ws_voice()` with a fake connection that disconnects and assert its seeded pending entry is removed.
Assert the endpoint passes the generated ID into `handle_message()` for transcript turns.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run python -m pytest tests/test_server.py tests/test_server_pending.py -k "connection_id or pending_cleanup" -v
```

Expected: failures because production currently keys pending actions with `id(ws)` and has no disconnect cleanup.

- [x] **Step 3: Implement generated ownership and cleanup**

Generate one UUID hex identifier after request validation.
Pass it to every `handle_message()` task.
Use it for pending lookup and storage.
Remove its pending entry and cancel the current handler in `ws_voice()` cleanup.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2 and require every selected test to pass.

### Task 5: Korean Fail-Closed Safety Rules

**Files:**

- Modify: `safety.py`
- Test: `tests/test_safety.py`

**Interfaces:**

- Produces: one internal keyword matcher shared by `classify()` and `reason()`.
- Consumes: existing `Decision` values and action-tag format.

- [x] **Step 1: Write failing Korean safety tests**

Assert that click labels containing `삭제` and `결제` require confirmation.
Assert that Computer Use goals containing `결제해주세요` and `비밀번호를 입력` are blocked.
Retain the English false-positive cases for `airpay` and `repay`.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run python -m pytest tests/test_safety.py -k "korean or payment or risky_label" -v
```

Expected: Korean label and suffixed-keyword cases fail against the current English-only or word-boundary-only policy.

- [x] **Step 3: Implement minimal bilingual matching**

Add Korean risky click fragments.
Use word-boundary matching for ASCII Computer Use keywords and substring matching for Korean keywords.
Reuse that matcher in `reason()`.

- [x] **Step 4: Run the complete safety suite**

Run:

```bash
uv run python -m pytest tests/test_safety.py -v
```

Expected: all safety tests pass.

### Task 6: Runtime Documentation and Final Gate

**Files:**

- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:**

- Consumes: the implemented handshake, confirmation, connection, and Korean safety contracts.
- Produces: synchronized operator and agent guidance.

- [x] **Step 1: Update the runtime contract**

Document the approved loopback origins, origin-less local client behavior, strict explicit confirmations, ambiguous-reply retention, and disconnect cleanup.
State that LAN, tunnel, reverse-proxy, and remote use still require a separate authentication design.

- [x] **Step 2: Run focused and complete verification**

Run:

```bash
uv run python -m pytest tests/test_safety.py tests/test_server.py tests/test_server_loop.py tests/test_server_pending.py -v
uv run python -m pytest
uv run python -m compileall server.py safety.py
trunk check server.py safety.py tests/test_safety.py tests/test_server.py tests/test_server_loop.py tests/test_server_pending.py README.md CLAUDE.md docs/specs/2026-08-13-security-boundaries-design.md docs/plans/2026-08-13-security-boundaries.md
git diff --check
```

Expected: all pytest and compilation commands pass, Trunk reports no issues in the explicit changed-file set, and `git diff --check` exits zero.

- [x] **Step 3: Review the complete diff**

Confirm that no dependency, unrelated review finding, generated file, or remote state changed.
