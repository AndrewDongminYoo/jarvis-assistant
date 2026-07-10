# LLM Provider Selection (Web UI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user pick one global preferred LLM provider from the web settings panel; the choice moves that provider to the front of every task's fallback order at runtime and persists across restarts.

**Architecture:** `LLMRouter` keeps the env-built order as an immutable base and reorders a working copy via `prefer()`. `server.py` exposes `GET`/`POST /api/providers` and persists the choice to `data/provider_pref.json`, re-applied at startup after `from_env()`. `settings.ts` adds a `<select>` that reads/writes that endpoint. Env order stays the default/floor; the UI is a runtime override on top.

**Tech Stack:** Python 3.13 + FastAPI (backend), pytest (tests), Vite + TypeScript (frontend). No new dependencies.

## Global Constraints

- Python `>=3.13`, run everything with `uv` (`uv run pytest`, `uv run python -m compileall`).
- No new runtime dependencies. Standard library only for the added backend code (`json`, `pathlib`).
- Env provider-order vars (`JARVIS_VOICE_PROVIDERS`, …) remain the default/floor; the UI preference is a runtime override layered on top of `LLMRouter.from_env`.
- "Available" = a provider that has an API key at startup (already present in a base route). Reuse this signal; do not invent a second notion.
- Build the feature around provider **order**, never around pinning model IDs (model IDs are volatile and stay in `llm_router.py`).
- CLI fallback providers (`is_cli_fallback`) are never shown, selected, or reordered.
- `/api/*` has no authentication; it is safe only under the loopback (`127.0.0.1`) bind. `POST /api/providers` mutates routing config — document the `HOST`-override warning in the README. The REST contract moves with the README.
- Logging allowlist: provider name is allowed; never log transcripts, prompt bodies, keys, or full responses.
- `data/provider_pref.json` must be gitignored.
- Frontend: safe DOM only (no `innerHTML`); match the existing `settings-group` / `settings-label` / `settings-input` styling.

---

### Task 1: Router base order, `available_providers`, and `prefer`

**Files:**

- Modify: `llm_router.py` (the `LLMRouter` class `__init__`, plus two new methods and one module helper)
- Test: `tests/test_llm_router.py`

**Interfaces:**

- Consumes: existing `LLMRouter(routes=...)` constructor, provider objects exposing `.name` and optional `.is_cli_fallback`.
- Produces:
  - `LLMRouter._base_routes: dict[str, list[LLMProvider]]` — the env order, never mutated by `prefer`.
  - `LLMRouter.preferred: str | None` — the active preference (None = env default).
  - `LLMRouter.available_providers() -> list[str]` — key-backed API provider names, union across tasks, in stable order `["anthropic", "openai", "gemini"]`, excluding CLI providers.
  - `LLMRouter.prefer(name: str | None) -> None` — reorder `self.routes` from `_base_routes`, moving `name` to the front of each task; unknown/None restores base and sets `preferred = None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_llm_router.py` (the module already has `FakeProvider`, `run`, `pytest`, and imports `LLMRouter`):

```python
def _four_task_router(order):
    # order: list of FakeProvider; same instances across all four tasks
    return LLMRouter(routes={t: list(order) for t in ("voice", "work", "plan", "narrate")})


def test_prefer_moves_provider_to_front_of_every_task():
    a, o, g = FakeProvider("anthropic"), FakeProvider("openai"), FakeProvider("gemini")
    router = LLMRouter(
        routes={
            "voice": [a, o, g],
            "work": [o, a, g],
            "plan": [a, o, g],
            "narrate": [a, o, g],
        }
    )
    router.prefer("openai")
    for task in ("voice", "work", "plan", "narrate"):
        assert router.routes[task][0].name == "openai"  # nosec B101
    # relative order of the rest is preserved
    assert [p.name for p in router.routes["voice"]] == [
        "openai",
        "anthropic",
        "gemini",
    ]  # nosec B101
    assert router.preferred == "openai"  # nosec B101


def test_prefer_none_restores_base_order():
    a, o = FakeProvider("anthropic"), FakeProvider("openai")
    router = _four_task_router([a, o])
    router.prefer("openai")
    router.prefer(None)
    assert [p.name for p in router.routes["voice"]] == ["anthropic", "openai"]  # nosec B101
    assert router.preferred is None  # nosec B101


def test_prefer_absent_name_keeps_base_order_and_clears_preferred():
    a, o = FakeProvider("anthropic"), FakeProvider("openai")
    router = _four_task_router([a, o])
    router.prefer("gemini")  # not present in any route
    assert [p.name for p in router.routes["voice"]] == ["anthropic", "openai"]  # nosec B101
    assert router.preferred is None  # nosec B101


def test_prefer_does_not_mutate_base_routes():
    a, o = FakeProvider("anthropic"), FakeProvider("openai")
    router = _four_task_router([a, o])
    router.prefer("openai")
    # a second prefer starts from the pristine base, not the reordered routes
    router.prefer("anthropic")
    assert [p.name for p in router.routes["voice"]] == ["anthropic", "openai"]  # nosec B101


def test_available_providers_unions_tasks_excludes_cli_stable_order():
    a, o = FakeProvider("anthropic"), FakeProvider("openai")
    cli = FakeProvider("codex-cli")
    cli.is_cli_fallback = True
    router = LLMRouter(
        routes={
            "voice": [o, a, cli],
            "work": [o, a, cli],
            "plan": [a],       # anthropic only here
            "narrate": [o],    # openai only here
        }
    )
    assert router.available_providers() == ["anthropic", "openai"]  # nosec B101
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_llm_router.py -k "prefer or available_providers" -q`
Expected: FAIL — `AttributeError: 'LLMRouter' object has no attribute 'prefer'` (and `available_providers`).

- [ ] **Step 3: Implement base order + methods + helper**

In `llm_router.py`, replace the `LLMRouter.__init__` body so both construction paths record a base copy and initialize `preferred`:

```python
    def __init__(
        self,
        providers: Mapping[str, LLMProvider] | None = None,
        route_names_by_task: Mapping[str, Sequence[str]] | None = None,
        routes: Mapping[str, Sequence[LLMProvider]] | None = None,
    ) -> None:
        if routes is not None:
            self.routes = {
                task: list(providers_for_task)
                for task, providers_for_task in routes.items()
            }
        else:
            providers = providers or {}
            route_names_by_task = route_names_by_task or DEFAULT_ROUTE_NAMES
            self.routes = {
                task: [
                    providers[name]
                    for name in route_names_by_task.get(task, [])
                    if name in providers
                ]
                for task in TASKS
            }
        # The env-built order is the floor; prefer() reorders a copy of it.
        self._base_routes = {task: list(ps) for task, ps in self.routes.items()}
        self.preferred: str | None = None
```

Add these two methods to `LLMRouter` (e.g. right after `from_env`):

```python
    def available_providers(self) -> list[str]:
        """API provider names present in at least one base route, excluding
        CLI fallbacks, in stable order."""
        present = {
            provider.name
            for providers_for_task in self._base_routes.values()
            for provider in providers_for_task
            if not getattr(provider, "is_cli_fallback", False)
        }
        return [name for name in ("anthropic", "openai", "gemini") if name in present]

    def prefer(self, name: str | None) -> None:
        """Move provider `name` to the front of every task route, recomputed
        from the pristine base order. Unknown or None restores the base order."""
        valid = bool(name) and any(
            provider.name == name
            for providers_for_task in self._base_routes.values()
            for provider in providers_for_task
        )
        self.preferred = name if valid else None
        self.routes = {
            task: _move_to_front(list(providers_for_task), self.preferred)
            for task, providers_for_task in self._base_routes.items()
        }
```

Add this module-level helper near the bottom of `llm_router.py` (next to `_route_names_for_task`):

```python
def _move_to_front(
    providers: list[LLMProvider], name: str | None
) -> list[LLMProvider]:
    """Return a new list with the provider named `name` first (if present),
    preserving the relative order of everything else."""
    if not name:
        return providers
    front = [p for p in providers if p.name == name]
    rest = [p for p in providers if p.name != name]
    return front + rest
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_llm_router.py -q`
Expected: PASS (all existing router tests plus the five new ones).

- [ ] **Step 5: Compile check**

Run: `uv run python -m compileall -q llm_router.py`
Expected: no output (success).

- [ ] **Step 6: Commit**

```bash
git add llm_router.py tests/test_llm_router.py
git commit -m "feat(router): add global provider preference reordering"
```

---

### Task 2: Persistence + REST endpoints + gitignore + README

**Files:**

- Modify: `server.py` (imports; `PROVIDER_PREF_PATH`, `_load_provider_pref`, `_save_provider_pref` right after `_router`; two endpoints in the REST section)
- Modify: `.gitignore` (add `data/provider_pref.json`)
- Modify: `README.md` (LLM Routing section)
- Test: `tests/test_server.py`

**Interfaces:**

- Consumes: `LLMRouter.available_providers()`, `LLMRouter.prefer()`, `LLMRouter.preferred` from Task 1.
- Produces:
  - `server.PROVIDER_PREF_PATH: Path`
  - `server._load_provider_pref() -> None`, `server._save_provider_pref(name: str | None) -> None`
  - `GET /api/providers` → `{"available": list[str], "preferred": str | None}`
  - `POST /api/providers` body `{"preferred": str | None}` → same shape on success; `HTTPException(400)` on an unknown/unavailable name.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_server.py` (it already has `run`, imports `server`, and imports `pytest` is NOT present — add `import pytest` and `from fastapi import HTTPException` at the top of the file if missing):

```python
import pytest
from fastapi import HTTPException
from llm_router import LLMRouter


class _Prov:
    def __init__(self, name):
        self.name = name


def _install_fake_router(monkeypatch, order=("anthropic", "openai")):
    provs = [_Prov(n) for n in order]
    router = LLMRouter(routes={t: list(provs) for t in ("voice", "work", "plan", "narrate")})
    monkeypatch.setattr(server, "_router", router)
    return router


def test_api_providers_get_returns_available_and_preferred(monkeypatch):
    _install_fake_router(monkeypatch)
    data = run(server.api_providers())
    assert data["available"] == ["anthropic", "openai"]  # nosec B101
    assert data["preferred"] is None  # nosec B101


def test_api_set_provider_reorders_and_persists(monkeypatch, tmp_path):
    router = _install_fake_router(monkeypatch)
    pref_file = tmp_path / "provider_pref.json"
    monkeypatch.setattr(server, "PROVIDER_PREF_PATH", pref_file)

    data = run(server.api_set_provider({"preferred": "openai"}))
    assert data["preferred"] == "openai"  # nosec B101
    assert router.routes["voice"][0].name == "openai"  # nosec B101
    assert pref_file.read_text().strip() == '{"preferred": "openai"}'  # nosec B101


def test_api_set_provider_null_clears(monkeypatch, tmp_path):
    router = _install_fake_router(monkeypatch)
    monkeypatch.setattr(server, "PROVIDER_PREF_PATH", tmp_path / "p.json")
    run(server.api_set_provider({"preferred": "openai"}))
    data = run(server.api_set_provider({"preferred": None}))
    assert data["preferred"] is None  # nosec B101
    assert router.routes["voice"][0].name == "anthropic"  # nosec B101


def test_api_set_provider_rejects_unknown(monkeypatch, tmp_path):
    router = _install_fake_router(monkeypatch)
    monkeypatch.setattr(server, "PROVIDER_PREF_PATH", tmp_path / "p.json")
    with pytest.raises(HTTPException) as excinfo:
        run(server.api_set_provider({"preferred": "bogus"}))
    assert excinfo.value.status_code == 400  # nosec B101
    # router untouched
    assert router.preferred is None  # nosec B101


def test_load_provider_pref_applies_saved_choice(monkeypatch, tmp_path):
    router = _install_fake_router(monkeypatch)
    pref_file = tmp_path / "p.json"
    pref_file.write_text('{"preferred": "openai"}')
    monkeypatch.setattr(server, "PROVIDER_PREF_PATH", pref_file)
    server._load_provider_pref()
    assert router.preferred == "openai"  # nosec B101


def test_load_provider_pref_ignores_missing_or_corrupt(monkeypatch, tmp_path):
    router = _install_fake_router(monkeypatch)
    # missing file
    monkeypatch.setattr(server, "PROVIDER_PREF_PATH", tmp_path / "absent.json")
    server._load_provider_pref()
    assert router.preferred is None  # nosec B101
    # corrupt file
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    monkeypatch.setattr(server, "PROVIDER_PREF_PATH", bad)
    server._load_provider_pref()
    assert router.preferred is None  # nosec B101
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_server.py -k "provider" -q`
Expected: FAIL — `AttributeError: module 'server' has no attribute 'api_providers'`.

- [ ] **Step 3: Add imports**

In `server.py`, add `import json` to the stdlib import block (after `import httpx` region — put `import json` with the stdlib imports near the top, e.g. after `import base64`), and add `HTTPException` to the FastAPI import:

```python
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
```

- [ ] **Step 4: Add persistence helpers right after the router is built**

In `server.py`, immediately after the line `_router = LLMRouter.from_env()`, insert:

```python
PROVIDER_PREF_PATH = Path("data/provider_pref.json")


def _load_provider_pref() -> None:
    """Apply a persisted provider preference on top of the env default order.
    A missing, unreadable, or unknown-provider file is ignored."""
    try:
        name = json.loads(PROVIDER_PREF_PATH.read_text()).get("preferred")
    except (OSError, ValueError):
        return
    if isinstance(name, str) and name in _router.available_providers():
        _router.prefer(name)


def _save_provider_pref(name: str | None) -> None:
    PROVIDER_PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROVIDER_PREF_PATH.write_text(json.dumps({"preferred": name}))


_load_provider_pref()
```

- [ ] **Step 5: Add the two endpoints**

In `server.py`, in the REST API section (after `api_status` / `api_health`), add:

```python
@app.get("/api/providers")
async def api_providers():
    return {
        "available": _router.available_providers(),
        "preferred": _router.preferred,
    }


@app.post("/api/providers")
async def api_set_provider(body: dict):
    name = body.get("preferred")
    if name is not None and name not in _router.available_providers():
        raise HTTPException(status_code=400, detail="unknown or unavailable provider")
    _router.prefer(name)
    _save_provider_pref(_router.preferred)
    return {
        "available": _router.available_providers(),
        "preferred": _router.preferred,
    }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_server.py -k "provider" -q`
Expected: PASS (six new tests).

- [ ] **Step 7: Gitignore the persistence file**

Add to `.gitignore`, next to the existing `data/` entries (e.g. after `data/active_session.json`):

```gitignore
data/provider_pref.json
```

Verify: `git check-ignore data/provider_pref.json` prints the path.

- [ ] **Step 8: Update the README**

In `README.md`, in the "LLM Routing" section, after the provider-order table (the "Default provider order per task" block), add:

```markdown
#### Preferred provider (runtime override)

The per-task order above is the default. From the web settings panel
("Preferred LLM") the user can move one provider to the front of every
task's order at runtime. The choice is stored in `data/provider_pref.json`
and re-applied at startup on top of the env defaults; "Auto" clears it.

- `GET /api/providers` → `{ "available": [<provider>, …], "preferred": <provider|null> }`
  (`available` = providers whose API key is present at startup).
- `POST /api/providers` with `{ "preferred": <provider|null> }` reorders the
  live router and persists the choice; an unknown or unavailable name returns
  `400`.

Like the rest of `/api/*`, these endpoints are unauthenticated and are only
safe under the default loopback bind. `POST /api/providers` mutates routing
config, so do not expose the server (see the `HOST` warning above) with these
endpoints reachable.
```

- [ ] **Step 9: Full regression + compile**

Run: `uv run pytest tests/test_server.py tests/test_llm_router.py -q`
Expected: PASS.
Run: `uv run python -m compileall -q server.py`
Expected: no output.

- [ ] **Step 10: Commit**

```bash
git add server.py tests/test_server.py .gitignore README.md
git commit -m "feat(server): expose GET/POST /api/providers with persistence"
```

---

### Task 3: Frontend "Preferred LLM" selector

**Files:**

- Modify: `frontend/src/settings.ts`

**Interfaces:**

- Consumes: `GET /api/providers` → `{ available: string[]; preferred: string | null }`, `POST /api/providers` body `{ preferred: string | null }` from Task 2.
- Produces: a `<select id="s-llm-provider">` in the settings panel; no exported API change.

- [ ] **Step 1: Add the provider group + load/save logic**

In `frontend/src/settings.ts`, after the block that appends `languageGroup` to `formWrap` (the line `formWrap.appendChild(languageGroup);`) and before `panel.appendChild(formWrap);`, insert:

```typescript
// Preferred LLM provider
const providerGroup = document.createElement("div");
providerGroup.className = "settings-group";

const providerLabel = document.createElement("label");
providerLabel.className = "settings-label";
providerLabel.htmlFor = "s-llm-provider";
providerLabel.textContent = "Preferred LLM";

const providerSelect = document.createElement("select");
providerSelect.id = "s-llm-provider";
providerSelect.className = "settings-input";
providerSelect.disabled = true; // enabled after availability loads

const providerLabels: Record<string, string> = {
  anthropic: "Claude (Anthropic)",
  openai: "GPT (OpenAI)",
  gemini: "Gemini (Google)",
};

const autoOption = document.createElement("option");
autoOption.value = "";
autoOption.textContent = "Auto (default order)";
providerSelect.appendChild(autoOption);

Object.entries(providerLabels).forEach(([value, label]) => {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  option.disabled = true; // enabled per availability in loadProviders()
  providerSelect.appendChild(option);
});

providerGroup.appendChild(providerLabel);
providerGroup.appendChild(providerSelect);
formWrap.appendChild(providerGroup);

async function loadProviders(): Promise<void> {
  try {
    const res = await fetch("/api/providers");
    if (!res.ok) return;
    const data = (await res.json()) as {
      available: string[];
      preferred: string | null;
    };
    Array.from(providerSelect.options).forEach((opt) => {
      opt.disabled = opt.value !== "" && !data.available.includes(opt.value);
    });
    providerSelect.value = data.preferred ?? "";
    providerSelect.disabled = false;
  } catch {
    // settings are a convenience; ignore fetch failures
  }
}

providerSelect.addEventListener("change", () => {
  void fetch("/api/providers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preferred: providerSelect.value || null }),
  }).catch(() => {
    /* ignore — non-critical */
  });
});
```

- [ ] **Step 2: Load availability when the panel opens**

In `frontend/src/settings.ts`, change the settings button handler from:

```typescript
btn.addEventListener("click", () => panel.classList.remove("hidden"));
```

to:

```typescript
btn.addEventListener("click", () => {
  panel.classList.remove("hidden");
  void loadProviders();
});
```

- [ ] **Step 3: Typecheck + build the frontend**

Run: `cd frontend && pnpm build`
Expected: `tsc` passes with no type errors and `vite build` completes.

- [ ] **Step 4: Manual verification**

Start the app (`scripts/start.sh`), open `http://localhost:5173` in Chrome, open the settings panel:

- The "Preferred LLM" dropdown shows "Auto (default order)" plus the three providers; providers without an API key are greyed out (disabled).
- Selecting an available provider issues `POST /api/providers`; reopening the panel shows it still selected (persisted).
- Confirm `data/provider_pref.json` was written with the chosen name.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/settings.ts
git commit -m "feat(frontend): add preferred LLM provider selector to settings"
```

---

## Self-Review

- **Spec coverage:** Router `prefer`/`available_providers`/base order (Task 1); persistence + `GET`/`POST /api/providers` + validation + startup load (Task 2); gitignore + README contract (Task 2 steps 7–8); frontend selector with disabled-unavailable + Auto + fetch-on-open + persistence-visible (Task 3). All spec sections map to a task.
- **Placeholder scan:** none — every code step contains full code and exact commands.
- **Type consistency:** `available_providers() -> list[str]`, `prefer(name: str | None)`, `preferred: str | None`, endpoint shape `{available, preferred}`, frontend `{ available: string[]; preferred: string | null }` — consistent across Tasks 1–3.
- **Constraint check:** no new deps (stdlib `json`/`pathlib` only); CLI providers excluded via `is_cli_fallback`; env stays the floor (`_load_provider_pref` layered after `from_env`); README + `/api` moved together; provider name only in logs; `data/provider_pref.json` gitignored; frontend uses safe DOM.
