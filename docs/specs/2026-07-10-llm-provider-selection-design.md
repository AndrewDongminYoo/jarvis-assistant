# LLM Provider Selection (Web UI) — Design

Status: Approved, not yet implemented
Date: 2026-07-10
Owner: Dongmin
Parent spec: `docs/specs/2026-05-11-general-agent-design.md`
Related: `llm_router.py`, `docs/specs/2026-04-22-multilingual-llm-router-design.md`

## Goal

Let the user, from the web settings panel, see which LLM providers are currently available and choose one to prefer.
The preferred provider is moved to the front of every task's fallback order at runtime and persisted so the choice survives a server restart.

## Non-Goals (YAGNI)

- Per-task provider preference (voice/work/plan/narrate each). One global preference only.
- Forcing a single provider with no fallback. The preference reorders; it never removes the fallback chain or the quota CLI tier.
- Drag-to-reorder or full ordering control. A single "move to front" choice.
- A live "last provider used" indicator in the UI.
- Pinning specific model IDs. The UI is built around provider order; per-task model IDs stay in `llm_router.py` (they are volatile).
- Exposing or selecting the CLI fallback providers (`claude-cli`, etc.). They remain quota-only fallbacks.

## Decisions

| Axis         | Decision                                                                                                                    |
| ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Scope        | One global preferred provider applied to all four tasks                                                                     |
| Relationship | Env order is the default/floor; the UI preference is a runtime override layered on top of `from_env`                        |
| Availability | "Available" = provider has an API key at startup (already in a task route). Reuse the existing signal                       |
| Application  | Move the preferred provider instance to the front of each task route; keep the rest of the order and the CLI tier unchanged |
| Persistence  | Server-side JSON file (`data/provider_pref.json`), gitignored. Loaded at startup after `from_env`                           |
| Transport    | New REST pair `GET`/`POST /api/providers`. The WebSocket turn protocol is unchanged                                         |
| Unavailable  | Shown in the UI as a disabled option (not hidden) so the user sees why it can't be picked                                   |

## Architecture

### Router (`llm_router.py`)

`LLMRouter` gains the notion of a base order plus an active preference.

- Store the env-built order as a base at construction: `self._base_routes = {task: list(providers)}` (a shallow copy of `self.routes`). This is the floor the UI override layers onto.
- `available_providers() -> list[str]`: the API provider names present in at least one base route (union across the four tasks), returned in a stable order (`anthropic`, `openai`, `gemini`), excluding CLI providers (those with `is_cli_fallback`). This is the availability signal the GET endpoint returns. Preferring a provider present in only some tasks is fine: `prefer` moves it to the front where it appears and is a no-op where it does not.
- `prefer(name: str | None) -> None`: recompute `self.routes` from `self._base_routes`. For each task, produce a new list where the provider whose `.name == name` is moved to the front, preserving the relative order of everything else (including the CLI tier). `name is None` (or a name not present) restores the exact base order. Pure reordering of existing instances — no rebuild, no new API clients.
- `self.preferred: str | None` records the active choice for the GET endpoint.

Why reordering instances is safe: each task route already holds provider instances bound to that task's model (the `openai` instance in `work` uses `gpt-4o`; in `voice` it uses `gpt-4o-mini`). Moving an instance to the front preserves the per-task model and the "work is the only large tier" cost expectation.

### Persistence (`server.py`)

- Path constant `PROVIDER_PREF_PATH = Path("data/provider_pref.json")`. File shape: `{"preferred": "openai"}` or `{"preferred": null}`.
- `_load_provider_pref()` at startup, right after `_router = LLMRouter.from_env()`: if the file exists and names an available provider, call `_router.prefer(name)`. A missing file, unreadable file, or a name not in `available_providers()` is ignored (env default stands) — never a startup error.
- `_save_provider_pref(name | None)` writes the file (creating `data/` if needed).

### REST API (`server.py`)

- `GET /api/providers` → `{"available": [...], "preferred": <name|null>}`. `available` from `available_providers()`, `preferred` from `_router.preferred`.
- `POST /api/providers` body `{"preferred": <name|null>}`:
  - `null` clears the override → `_router.prefer(None)`, persist `null`, return the new state.
  - a name in `available` → `_router.prefer(name)`, persist, return the new state.
  - anything else → `400` with a short message; router and file are untouched.
- Both inherit the existing `/api/*` posture: no authentication, safe only under the loopback (`127.0.0.1`) bind. `POST` mutates routing config, so it is only safe locally.

### Frontend (`frontend/src/settings.ts`)

- Add a "Preferred LLM" group below the language dropdown, matching the existing `<select>` styling and the no-`innerHTML` DOM convention.
- On panel open, `GET /api/providers`; build options: `Auto (default order)` (value empty → `preferred: null`) plus one option per known provider. Providers not in `available` render as `disabled`.
- Set the current value from `preferred`. On `change`, `POST /api/providers` with the chosen value. This is the frontend's first use of `fetch` against `/api`.
- Failures (offline, non-200) are swallowed with a console warning; the selector is a convenience, not a critical path.

## Data Flow

```text
Panel open → GET /api/providers → {available, preferred} → render <select>
User picks "GPT" → POST /api/providers {preferred:"openai"}
   → validate against available
   → _router.prefer("openai")  (openai instance to front of every task route)
   → write data/provider_pref.json
   → 200 {available, preferred:"openai"}
Next turn → _router.complete(task) walks the reordered route → openai first
Server restart → from_env() (env floor) → _load_provider_pref() re-applies "openai"
```

## Error Handling

- Invalid POST value → `400`, no state change.
- Preferring an available provider that later fails at request time → the existing router fallback handles it (next provider, then CLI on quota error). Preference only changes order, not the fallback guarantees.
- Corrupt/missing pref file at startup → ignored, env default order stands.
- Frontend fetch error → console warning, panel still usable for other settings.

## Testing

Backend (pytest, `tests/test_llm_router.py`, `tests/test_server.py`):

- `prefer("openai")` moves openai to the front of every task route and preserves the relative order of the rest and the CLI tier.
- `prefer(None)` and `prefer("absent-name")` restore/keep the exact base order.
- `available_providers()` returns only key-backed API providers, excluding CLI, in stable order.
- `GET /api/providers` returns available + preferred; `POST` with a valid name reorders and persists; `POST` with an invalid name returns 400 and leaves state unchanged; `POST {preferred:null}` clears.
- Startup load applies a persisted preference; a missing/corrupt file is ignored.

Frontend: logic is thin (fetch + build `<select>` + fetch on change) and has no pure unit like `wake.ts`; verify by driving the panel manually (`pnpm build` for typecheck).

## Security & Observability Notes

- New endpoints are unauthenticated like the rest of `/api/*`; document in README that `POST /api/providers` mutates routing and is only safe under the default loopback bind (`HOST` override warning).
- `data/provider_pref.json` must be gitignored (add a `.gitignore` entry). It contains only a provider name — no secrets — but config files are not committed.
- Logging keeps to the allowlist: provider name is already allowed, so logging the applied preference is fine; no transcript/prompt/body data is logged.

## Docs

- Update the README "LLM Routing" section: the env vars remain the default order, the UI preference is a runtime override, and document the `GET`/`POST /api/providers` contract (the REST contract moves with the README).
- `docs/voice-commands.md` is not touched — this is a UI setting, not a voice command.
