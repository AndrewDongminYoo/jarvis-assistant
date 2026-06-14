"""Task-aware LLM provider routing for JARVIS."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

log = logging.getLogger("jarvis.llm_router")

Message = dict[str, Any]


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        messages: list[Message],
        system: str,
        max_tokens: int,
    ) -> str: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        messages: list[Message],
        system: str,
        max_tokens: int,
    ) -> str:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return response.content[0].text  # type: ignore[union-attr]


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key)

    async def complete(
        self,
        messages: list[Message],
        system: str,
        max_tokens: int,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *messages],
        )
        return response.choices[0].message.content or ""


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    async def complete(
        self,
        messages: list[Message],
        system: str,
        max_tokens: int,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *messages],
        )
        return response.choices[0].message.content or ""


# --- Local CLI fallback ----------------------------------------------------
#
# When an API provider runs out of quota/credits, JARVIS can fall back to a
# locally installed coding-assistant CLI (claude / codex / gemini). These CLIs
# authenticate through the user's own subscription/OAuth login, which is
# separate from the (now exhausted) API billing — making them a viable last
# resort. The fallback only engages after a quota-class error is seen on the
# API tier; ordinary failures do not spawn subprocesses.

# Maps an API vendor to its local CLI binary and the provider name used in logs.
CLI_BINARIES = {
    "anthropic": "claude",
    "openai": "codex",
    "gemini": "gemini",
}
CLI_PROVIDER_NAMES = {
    "anthropic": "claude-cli",
    "openai": "codex-cli",
    "gemini": "gemini-cli",
}
# Stripped from the CLI subprocess environment so the CLI uses its own login
# instead of an exhausted API credential. Each var below was verified to route
# its CLI to API billing when present: claude honors ANTHROPIC_API_KEY /
# ANTHROPIC_AUTH_TOKEN, codex honors CODEX_API_KEY (it ignores OPENAI_API_KEY,
# but scrubbing it is harmless), gemini honors GEMINI_API_KEY / GOOGLE_API_KEY.
CLI_SCRUBBED_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)
DEFAULT_CLI_TIMEOUT_S = 90.0
CLI_TIMEOUT_ENV_VAR = "JARVIS_CLI_TIMEOUT"

_QUOTA_STATUS_CODES = frozenset({429})
_QUOTA_ERROR_CODES = frozenset({"insufficient_quota", "rate_limit_exceeded"})
_QUOTA_MESSAGE_MARKERS = (
    "insufficient_quota",
    "insufficient quota",
    "credit balance",
    "exceeded your current quota",
    "quota",
    "rate limit",
    "rate_limit",
    "too many requests",
    "billing",
)
# Matches tag-like tokens (<USER>, </SYSTEM>, ...) in user content so they
# cannot be confused with the role-block delimiters we wrap messages in.
_PROMPT_TAG_RE = re.compile(r"</?[A-Za-z_][A-Za-z0-9_]*>")


def _is_quota_error(exc: BaseException) -> bool:
    """Return True when an exception looks like a quota/rate-limit/billing error.

    Recognizes HTTP 429, SDK error codes (insufficient_quota,
    rate_limit_exceeded), and common message markers across Anthropic, OpenAI,
    and the Gemini OpenAI-compatible client.
    """
    if getattr(exc, "status_code", None) in _QUOTA_STATUS_CODES:
        return True
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.lower() in _QUOTA_ERROR_CODES:
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _QUOTA_MESSAGE_MARKERS)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


def render_cli_prompt(
    messages: list[Message],
    system: str | None = None,
) -> str:
    """Flatten a conversation into a single tagged prompt string.

    Each turn becomes a `<ROLE>...</ROLE>` block. When `system` is provided it
    is prepended as a `<SYSTEM>` block — used for CLIs without a system-prompt
    flag (codex, gemini). For claude the system prompt is passed via a flag, so
    `system` is omitted here.
    """
    blocks: list[str] = []
    if system:
        blocks.append(f"<SYSTEM>\n{_PROMPT_TAG_RE.sub(_escape_tag, system)}\n</SYSTEM>")
    for message in messages:
        role = str(message.get("role", "user")).upper()
        text = _PROMPT_TAG_RE.sub(_escape_tag, _content_to_text(message.get("content")))
        blocks.append(f"<{role}>\n{text}\n</{role}>")
    return "\n\n".join(blocks)


def _escape_tag(match: re.Match[str]) -> str:
    return match.group(0).replace("<", "&lt;").replace(">", "&gt;")


def build_cli_argv(
    vendor: str,
    binary: str,
    messages: list[Message],
    system: str,
) -> list[str]:
    """Build the non-interactive argv for a vendor's CLI."""
    if vendor == "anthropic":
        argv = [binary, "-p", render_cli_prompt(messages), "--strict-mcp-config"]
        if system:
            argv += ["--system-prompt", system]
        return argv
    prompt = render_cli_prompt(messages, system=system or None)
    # codex/gemini refuse to run outside a trusted/git directory; the fallback
    # runs in a neutral temp cwd (no project context), so bypass those checks.
    if vendor == "openai":
        return [binary, "exec", "--skip-git-repo-check", "--json", prompt]
    if vendor == "gemini":
        return [binary, "-p", prompt, "-o", "json", "--skip-trust"]
    raise ValueError(f"no CLI argv builder for vendor '{vendor}'")


def parse_cli_output(vendor: str, stdout: str) -> str:
    """Extract the assistant text from a vendor CLI's stdout."""
    if vendor == "anthropic":
        return stdout.strip()
    if vendor == "openai":
        return _parse_codex_output(stdout)
    if vendor == "gemini":
        return _parse_gemini_output(stdout)
    raise ValueError(f"no CLI output parser for vendor '{vendor}'")


def _parse_codex_output(stdout: str) -> str:
    """Pull the last `agent_message` text out of codex's JSONL stream."""
    text = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            value = item.get("text")
            if isinstance(value, str) and value:
                text = value
    return text.strip()


def _parse_gemini_output(stdout: str) -> str:
    """Read the `response` field from `gemini -o json` output."""
    stripped = stdout.strip()
    start = stripped.find("{")
    if start == -1:
        return ""
    try:
        data = json.loads(stripped[start:])
    except ValueError:
        return ""
    if isinstance(data, dict) and isinstance(data.get("response"), str):
        return data["response"].strip()
    return ""


def build_cli_env(base_env: Mapping[str, str]) -> dict[str, str]:
    """Copy the environment with API keys removed so the CLI uses its login."""
    env = dict(base_env)
    for key in CLI_SCRUBBED_ENV_KEYS:
        env.pop(key, None)
    return env


def _cli_exit_error(binary: str, code: int | None, stderr: str) -> str:
    detail = stderr.strip()
    low = detail.lower()
    if any(
        marker in low
        for marker in (
            "unauthenticated",
            "not authenticated",
            "invalid api key",
            "please log in",
            "log in",
        )
    ):
        return f"{binary} CLI is not authenticated (exit {code}); run `{binary}` in a terminal to log in"
    snippet = detail[:200]
    return f"{binary} CLI exited with code {code}" + (f": {snippet}" if snippet else "")


class CliProvider:
    """LLM provider backed by a local CLI subprocess (claude / codex / gemini).

    `max_tokens` has no CLI equivalent and is ignored; the CLI's default model
    is used. Reached only as a quota fallback (see `LLMRouter.complete`).
    """

    is_cli_fallback = True

    def __init__(
        self,
        vendor: str,
        binary: str,
        name: str,
        timeout_s: float = DEFAULT_CLI_TIMEOUT_S,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        self.vendor = vendor
        self.binary = binary
        self.name = name
        self.model = f"{binary}-cli-default"
        self._timeout_s = timeout_s
        self._env = dict(env) if env is not None else None
        self._cwd = cwd

    async def complete(
        self,
        messages: list[Message],
        system: str,
        max_tokens: int,
    ) -> str:
        argv = build_cli_argv(self.vendor, self.binary, messages, system)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
            env=self._env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), self._timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"{self.binary} CLI timed out after {self._timeout_s:.0f}s"
            ) from None

        stderr = stderr_b.decode("utf-8", "replace")
        if proc.returncode != 0:
            raise RuntimeError(_cli_exit_error(self.binary, proc.returncode, stderr))

        text = parse_cli_output(self.vendor, stdout_b.decode("utf-8", "replace"))
        if not text:
            raise RuntimeError(f"{self.binary} CLI returned no content")
        return text


def _cli_timeout_s(env: Mapping[str, str]) -> float:
    raw = env.get(CLI_TIMEOUT_ENV_VAR, "")
    if not raw:
        return DEFAULT_CLI_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CLI_TIMEOUT_S
    return value if value > 0 else DEFAULT_CLI_TIMEOUT_S


TASKS = ("voice", "work", "plan", "narrate")
DEFAULT_ROUTE_NAMES = {
    "voice": ["anthropic", "openai", "gemini"],
    "work": ["openai", "anthropic", "gemini"],
    "plan": ["anthropic", "openai", "gemini"],
    "narrate": ["anthropic", "openai", "gemini"],
}
ROUTE_ENV_VARS = {
    "voice": "JARVIS_VOICE_PROVIDERS",
    "work": "JARVIS_WORK_PROVIDERS",
    "plan": "JARVIS_PLAN_PROVIDERS",
    "narrate": "JARVIS_NARRATE_PROVIDERS",
}
API_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
ANTHROPIC_MODELS = {
    "voice": "claude-haiku-4-5-20251001",
    "work": "claude-sonnet-4-5-20250929",
    "plan": "claude-haiku-4-5-20251001",
    "narrate": "claude-haiku-4-5-20251001",
}
OPENAI_MODELS = {
    "voice": "gpt-4o-mini",
    "work": "gpt-4o",
    "plan": "gpt-4o-mini",
    "narrate": "gpt-4o-mini",
}
GEMINI_MODELS = {
    "voice": "gemini-2.0-flash",
    "work": "gemini-2.0-pro",
    "plan": "gemini-2.0-flash",
    "narrate": "gemini-2.0-flash",
}

ProviderFactory = Callable[..., LLMProvider]


class LLMRouter:
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
            return

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

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        provider_factories: Mapping[str, ProviderFactory] | None = None,
    ) -> "LLMRouter":
        env = env or os.environ
        factories = provider_factories or _default_provider_factories()
        routes: dict[str, list[LLMProvider]] = {}
        cli_env = build_cli_env(env)
        cli_timeout = _cli_timeout_s(env)
        cli_cwd = tempfile.gettempdir()

        for task in TASKS:
            route_names = _route_names_for_task(env, task)
            routes[task] = []
            for provider_name in route_names:
                api_key = env.get(API_KEY_ENV_VARS.get(provider_name, ""), "")
                if not api_key:
                    continue
                factory = factories.get(provider_name)
                if factory is None:
                    continue
                routes[task].append(_build_provider(factory, api_key, task))
            # Append the local CLI fallback tier, mirroring the configured
            # vendor order. A CLI is included only when its binary is on PATH;
            # it is reached at request time only after a quota-class error.
            for vendor in dict.fromkeys(route_names):
                binary = CLI_BINARIES.get(vendor)
                if not binary:
                    continue
                resolved = shutil.which(binary)
                if not resolved:
                    continue
                routes[task].append(
                    CliProvider(
                        vendor=vendor,
                        binary=resolved,
                        name=CLI_PROVIDER_NAMES[vendor],
                        timeout_s=cli_timeout,
                        env=cli_env,
                        cwd=cli_cwd,
                    )
                )

        configured = {
            provider.name
            for providers_for_task in routes.values()
            for provider in providers_for_task
        }
        if configured:
            log.info("Configured LLM providers: %s", ", ".join(sorted(configured)))
        else:
            log.warning("No LLM providers configured")
        return cls(routes=routes)

    async def complete(
        self,
        task: str,
        messages: list[Message],
        system: str,
        max_tokens: int,
    ) -> str:
        route = self.routes.get(task) or self.routes.get("voice", [])
        errors: list[str] = []
        quota_seen = False

        for provider in route:
            is_cli = getattr(provider, "is_cli_fallback", False)
            # The CLI tier is a quota fallback only: skip it unless an API
            # provider already failed with a quota/credit error.
            if is_cli and not quota_seen:
                continue
            model = getattr(provider, "model", "unknown")
            started = time.perf_counter()
            try:
                log.info(
                    "LLM request task=%s provider=%s model=%s",
                    task,
                    provider.name,
                    model,
                )
                response = await provider.complete(messages, system, max_tokens)
                duration_ms = int((time.perf_counter() - started) * 1000)
                log.info(
                    "LLM response task=%s provider=%s model=%s duration_ms=%d chars=%d",
                    task,
                    provider.name,
                    model,
                    duration_ms,
                    len(response),
                )
                return response
            except Exception as exc:
                log.warning(
                    "LLM provider failed task=%s provider=%s model=%s error=%s",
                    task,
                    provider.name,
                    model,
                    exc,
                )
                errors.append(f"{provider.name}: {exc}")
                if not is_cli and not quota_seen and _is_quota_error(exc):
                    quota_seen = True
                    log.warning(
                        "LLM quota exhausted task=%s provider=%s; enabling local CLI fallback",
                        task,
                        provider.name,
                    )

        details = "; ".join(errors) if errors else "no configured providers"
        raise RuntimeError(f"All providers failed for task '{task}': {details}")


def _default_provider_factories() -> dict[str, ProviderFactory]:
    return {
        "anthropic": lambda api_key, task: AnthropicProvider(
            api_key, ANTHROPIC_MODELS[task]
        ),
        "openai": lambda api_key, task: OpenAIProvider(api_key, OPENAI_MODELS[task]),
        "gemini": lambda api_key, task: GeminiProvider(api_key, GEMINI_MODELS[task]),
    }


def _route_names_for_task(env: Mapping[str, str], task: str) -> list[str]:
    configured = env.get(ROUTE_ENV_VARS[task], "")
    raw_names = configured.split(",") if configured else DEFAULT_ROUTE_NAMES[task]
    return [name.strip().lower() for name in raw_names if name.strip()]


def _build_provider(factory: ProviderFactory, api_key: str, task: str) -> LLMProvider:
    parameters = inspect.signature(factory).parameters
    required = [
        param
        for param in parameters.values()
        if param.default is inspect.Parameter.empty
        and param.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(required) >= 2:
        return factory(api_key, task)
    return factory(api_key)
