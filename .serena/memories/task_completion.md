# Task Completion

Run the checks matching what you touched. Do not claim "verified" without running.

## Backend changed

1. `uv run pytest` (must pass; macos-marker tests are excluded by default).
2. `uv run python -m compileall server.py planner.py llm_router.py safety.py gui_actions.py computer_use.py`
3. If routing/behavior changed, also confirm relevant module test (e.g. `tests/test_llm_router.py`).

## Frontend changed

1. `cd frontend && pnpm build` (runs `tsc` typecheck + `vite build`).
2. If `wake.ts` or `session.ts` changed, compile+run their `test/*.test.ts` pair (see `mem:suggested_commands`).

## Always

- If runtime behavior changed, update `README.md` in the SAME change (see `mem:core` sources of truth).
- Repo lint: `trunk check` (and `trunk fmt` before committing).
- Confirm no secrets/logs violate `mem:conventions` security rules.
