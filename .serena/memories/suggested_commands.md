# Suggested Commands

## Backend (run from project root)

- Tests: `uv run pytest` (macos-marker tests excluded by default). Single: `uv run pytest tests/test_llm_router.py::test_name` or `uv run pytest -k "fallback" -x`.
- Compile check: `uv run python -m compileall server.py planner.py llm_router.py safety.py gui_actions.py computer_use.py`
- Live macOS integration tests (needs Accessibility permission): `uv run pytest -m macos`.

## Frontend (from `frontend/`)

- Build (also typechecks): `pnpm build` (= `tsc && vite build`). Dev server: `pnpm dev` (port 5173).
- Frontend unit tests = compile+run one pair manually (no runner):
  `pnpm exec tsc --ignoreConfig --module NodeNext --moduleResolution NodeNext --target ES2020 --outDir /tmp/out src/wake.ts test/wake.test.ts && node /tmp/out/test/wake.test.js`
  (same pattern for `session`).

## Run whole app

- `scripts/start.sh` — activates `.venv`, runs `python server.py` + `pnpm dev`, opens on http://localhost:5173 (Chrome). Backend `PORT` default `8340`, serves built frontend at `/app` when `frontend/dist/` exists; dev proxies `/ws/voice` + `/api` to `https://localhost:8340`.

## Lint (repo-wide)

- `trunk check` / `trunk fmt` (trunk.io configured in `.trunk/`).

## Darwin notes

- Standard BSD userland (`sed -i ''`, `find`, `grep` differ from GNU). App needs one initial click to unlock mic/audio.
