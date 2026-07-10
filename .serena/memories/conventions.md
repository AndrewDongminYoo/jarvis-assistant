# Conventions

## Layout

- Backend = flat top-level `.py` modules at project root (no `src/` package). Tests mirror as `tests/test_<module>.py`.
- Frontend under `frontend/src/`; tests under `frontend/test/` as self-executing `*.test.ts`.

## Language / comms

- Conversation with user: Korean. Code, identifiers, comments, commit messages, docs: English.
- Korean user-facing strings/comments elsewhere are intentional — do not translate.

## Security (hard rules)

- Never commit `.env`, `JARVIS.md`, DB files, cert/key files, API keys. Use placeholders in docs (e.g. `your-anthropic-key-here`).
- Never log user transcripts, prompt bodies, API keys, or full model responses. LLM logs = task/provider/model, success|failure, latency, response length ONLY.

## Design patterns to preserve

- `wake.ts` MUST stay a pure, side-effect-free function so its unit test stays meaningful.
- Action tags: system prompt (`server.py`), `ACTION_RE` parser, `_dispatch_action_result`, and README action list move together.
- Router tests inject via `routes=` kwarg — keep `LLMRouter` constructor injectable.
- Preserve existing attribution comments (original JARVIS build prompt credits Taoufik, instagram.com/taoufik.ai).

## Style

- `set -euo pipefail` idiom for shell scripts. Minimal diffs, existing conventions, no broad refactors unless asked.
- Markdown: language id on every fenced block; no hard wraps; sentence-per-line.

## Serena-specific

- Prefer symbolic tools over full-file reads; refactor via `rename_symbol`/`safe_delete_symbol`. Serena line numbers are 0-based.
