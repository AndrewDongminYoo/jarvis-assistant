# Security Boundaries Design

## Status

Approved on August 13, 2026.

## Context

JARVIS intentionally runs without authentication on a single user's Mac and binds to loopback by default.
That local-only deployment model does not protect the privileged WebSocket from a hostile browser origin, because browsers can attempt connections to loopback services and FastAPI's HTTP CORS middleware does not validate WebSocket handshakes.
The current confirmation parser also accepts affirmative words embedded in unrelated or explicitly negated sentences, and the safety classifier does not consistently recognize Korean risky-action labels or Korean suffixes.

This change hardens the existing local-only boundary without adding accounts, remote access, a general authorization framework, or action sandboxing.

## Goals

- Reject privileged WebSocket handshakes when the request host is not loopback.
- Reject browser WebSocket handshakes whose `Origin` is not an approved local JARVIS origin.
- Preserve origin-less clients only when they connect through a loopback host.
- Execute a pending action only after a short, explicit affirmative response.
- Treat explicit negative language as cancellation and retain a pending action when the reply is ambiguous.
- Bind pending confirmations to a generated connection identifier and remove them when the connection closes.
- Recognize Korean risky-click labels and Korean payment or credential terms with attached particles or polite suffixes.
- Keep the existing `SAFE`, `CONFIRM`, and `BLOCKED` public policy model.

## Non-Goals

- Authentication, user accounts, or bearer tokens.
- LAN, tunnel, reverse-proxy, container-published, or remote-client support.
- General action sandboxing.
- Computer Use nested-action approval, AppleScript escaping, SQLite concurrency, audio framing, or the remaining review backlog.
- A new dependency or framework abstraction.

## WebSocket Handshake Policy

The server validates the request before calling `WebSocket.accept()`.

A request host is trusted only when its parsed hostname is `localhost`, `127.0.0.1`, or `::1`.
The host may omit a port or include either the fixed Vite development port `5173` or the configured backend `PORT`.
Malformed hosts and all non-loopback names or addresses are rejected.

An absent `Origin` is accepted for local non-browser clients after the host check passes.
A present `Origin` must use `http` or `https`, must use a loopback hostname, and must use either the Vite development port `5173` or the configured backend `PORT`.
Opaque origins such as `null`, credential-bearing origins, malformed values, and all other ports are rejected.

The endpoint raises ASGI policy-violation code `1008` before acceptance.
Uvicorn maps that pre-accept denial to an HTTP `403` handshake rejection, so browser clients are not promised a WebSocket close-frame code.
The existing HTTP CORS configuration remains unchanged because it serves a separate boundary.

## Confirmation Semantics

Affirmative detection becomes exact after common apostrophe canonicalization, case-folding, whitespace collapse, and removal of surrounding sentence punctuation.
Accepted phrases remain deliberately small and include established English and Korean responses such as `yes`, `okay`, `go ahead`, `do it`, `예`, `응`, `그래`, and `해줘`.
Affirmative words embedded in longer speech do not authorize execution.

Negative detection remains fail-safe and runs before affirmative detection.
Explicit negative words or phrases such as `no`, `cancel`, `stop`, `abort`, `don't`, `don’t`, `do not`, `아니요`, `취소`, `그만`, and `하지 마` cancel the pending action even when the utterance also contains an affirmative token.
Common Korean endings in phrases such as `취소해줘`, `하지 마세요`, and `아니에요` remain cancellations, while the completed-pattern boundary prevents unrelated words such as `취소선` and `아니메이션` from cancelling.

If a reply is neither negative nor an exact affirmative, the server restores the same unexpired pending action and asks for an explicit yes or no.
The original expiration timestamp is retained, so ambiguous replies cannot extend the confirmation window indefinitely.
The reply does not enter normal turn handling while the confirmation remains pending.

## Connection Ownership

Each accepted WebSocket receives a random UUID-based connection identifier.
Production calls pass that identifier into message handling and use it as the pending-action registry key.
The WebSocket endpoint removes the connection's pending action in `finally`, regardless of normal close, disconnect, protocol error, or cancellation.

Direct unit calls may omit the identifier and retain the existing object-derived fallback for test compatibility, but the production WebSocket path never uses that fallback.

## Korean Safety Classification

Risky UI click labels add Korean equivalents for send, delete, purchase, confirmation, payment, submission, removal, trash, sign-out, and discard actions.
Matching remains case-insensitive substring matching because labels commonly contain surrounding product copy.

Computer Use blocking keeps word-boundary matching for English keywords to avoid false positives such as `airpay` and `repay`.
Korean payment and credential keywords use substring matching so particles and polite suffixes do not bypass the block.
The same matching helper is used by `classify()` and `reason()` so the decision and explanation cannot drift.

## Error Handling

- A rejected WebSocket does not start a handler or create pending state.
- An ambiguous confirmation does not invoke the dispatcher.
- A disconnected connection cannot leave an executable pending action behind.
- Existing negative confirmations continue to return the bilingual cancellation response.
- Existing safe reads and confirmed write actions retain their public action tags and result formats.

## Test Strategy

- Pure tests cover valid and invalid hosts and origins, including IPv4, IPv6, missing origin, opaque origin, foreign origin, and disallowed ports.
- FastAPI WebSocket integration tests prove that an untrusted origin is rejected and a trusted local origin completes a `ping`/`pong` exchange.
- Safety tests reproduce the unrelated-sentence, negated-sentence, and Korean cancellation-suffix defects before implementation while protecting unrelated Korean words from substring matches.
- Safety tests cover Korean risky UI labels and Korean suffixed Computer Use keywords.
- Server-loop tests prove that ambiguous replies do not dispatch and retain the original pending action.
- WebSocket lifecycle tests prove generated connection IDs are passed to handlers and pending state is removed on disconnect.
- The final gate runs the focused tests, the complete backend suite, Python compilation, Trunk checks for the modified files, and `git diff --check`.

## Documentation Contract

`README.md` remains the runtime source of truth and documents the local WebSocket origin restriction and explicit confirmation behavior.
`CLAUDE.md` receives the matching agent-facing cross-file contract in the same change.
