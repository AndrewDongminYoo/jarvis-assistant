"""Task-aware LLM provider routing for JARVIS."""

from __future__ import annotations

import inspect
import logging
import os
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

        for provider in route:
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
