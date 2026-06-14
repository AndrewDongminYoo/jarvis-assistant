import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeProvider:
    def __init__(self, name, result=None, error=None, model="fake-model"):
        self.name = name
        self.model = model
        self.result = result or f"{name}-result"
        self.error = error
        self.calls = []

    async def complete(self, messages, system, max_tokens):
        self.calls.append(
            {"messages": messages, "system": system, "max_tokens": max_tokens}
        )
        if self.error:
            raise self.error
        return self.result


def run(coro):
    return asyncio.run(coro)


def test_router_falls_back_to_next_provider_after_failure():
    from llm_router import LLMRouter

    first = FakeProvider("anthropic", error=RuntimeError("anthropic down"))
    second = FakeProvider("openai", result="openai answer")
    router = LLMRouter(
        providers={"anthropic": first, "openai": second},
        route_names_by_task={"voice": ["anthropic", "openai"]},
    )

    result = run(
        router.complete("voice", [{"role": "user", "content": "hi"}], "sys", 10)
    )

    assert result == "openai answer"  # nosec B101
    assert len(first.calls) == 1  # nosec B101
    assert len(second.calls) == 1  # nosec B101


def test_router_raises_when_all_providers_fail():
    from llm_router import LLMRouter

    router = LLMRouter(
        providers={
            "anthropic": FakeProvider("anthropic", error=RuntimeError("a")),
            "openai": FakeProvider("openai", error=RuntimeError("o")),
        },
        route_names_by_task={"voice": ["anthropic", "openai"]},
    )

    with pytest.raises(RuntimeError, match="All providers failed"):
        run(router.complete("voice", [], "sys", 10))


def test_unknown_task_uses_voice_route():
    from llm_router import LLMRouter

    voice = FakeProvider("anthropic", result="voice route")
    work = FakeProvider("openai", result="work route")
    router = LLMRouter(
        providers={"anthropic": voice, "openai": work},
        route_names_by_task={
            "voice": ["anthropic"],
            "work": ["openai"],
        },
    )

    result = run(router.complete("unexpected", [], "sys", 10))

    assert result == "voice route"  # nosec B101
    assert len(voice.calls) == 1  # nosec B101
    assert len(work.calls) == 0  # nosec B101


def test_from_env_skips_missing_provider_keys_and_keeps_route_priority(monkeypatch):
    import llm_router
    from llm_router import LLMRouter

    # Isolate the API tier: no CLI fallback regardless of locally installed
    # binaries (covered separately by test_from_env_appends_cli_tier_*).
    monkeypatch.setattr(llm_router.shutil, "which", lambda binary: None)

    created = {}

    def make_provider(name):
        def factory(api_key):
            provider = FakeProvider(name, result=api_key)
            created[name] = provider
            return provider

        return factory

    router = LLMRouter.from_env(
        env={
            "ANTHROPIC_API_KEY": "anthropic-key",
            "OPENAI_API_KEY": "openai-key",
            "JARVIS_VOICE_PROVIDERS": "openai, anthropic, gemini",
        },
        provider_factories={
            "anthropic": make_provider("anthropic"),
            "openai": make_provider("openai"),
            "gemini": make_provider("gemini"),
        },
    )

    assert [provider.name for provider in router.routes["voice"]] == [  # nosec B101
        "openai",
        "anthropic",
    ]
    assert set(created) == {"anthropic", "openai"}  # nosec B101


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Can you implement the voice router?", "work"),
        ("한국어 지원을 구현해 주세요", "work"),
        ("Give me a plan for this", "plan"),
        ("다음 단계 계획을 알려줘", "plan"),
        ("Good morning", "voice"),
    ],
)
def test_task_type_routes_transcript_by_intent(text, expected):
    from server import _task_type

    assert _task_type(text) == expected  # nosec B101


def test_planner_uses_router_for_clarifying_questions(monkeypatch):
    import planner

    class FailingDirectClient:
        class messages:
            @staticmethod
            def create(*args, **kwargs):
                raise AssertionError("planner should use LLMRouter")

    class CapturingRouter:
        def __init__(self):
            self.calls = []

        async def complete(self, task, messages, system, max_tokens):
            self.calls.append(
                {
                    "task": task,
                    "messages": messages,
                    "system": system,
                    "max_tokens": max_tokens,
                }
            )
            return "router questions"

    router = CapturingRouter()
    monkeypatch.setattr(planner, "_client", FailingDirectClient(), raising=False)
    monkeypatch.setattr(planner, "_router", router, raising=False)

    assert (  # nosec B101
        run(planner.get_clarifying_questions("build routing")) == "router questions"
    )
    assert router.calls[0]["task"] == "plan"  # nosec B101


def test_router_logs_provider_request_and_response(caplog):
    import logging

    from llm_router import LLMRouter

    provider = FakeProvider("openai", result="short answer", model="gpt-test")
    router = LLMRouter(
        providers={"openai": provider},
        route_names_by_task={"voice": ["openai"]},
    )

    with caplog.at_level(logging.INFO, logger="jarvis.llm_router"):
        result = run(router.complete("voice", [], "sys", 10))

    assert result == "short answer"  # nosec B101
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "LLM request task=voice provider=openai model=gpt-test" in logs  # nosec B101
    assert (
        "LLM response task=voice provider=openai model=gpt-test" in logs
    )  # nosec B101
    assert "chars=12" in logs  # nosec B101


def test_default_elevenlabs_voice_id_matches_jarvis_spec():
    import server

    assert server.DEFAULT_ELEVENLABS_VOICE_ID == "UgBBYS2sOqTuMpoF3BR0"  # nosec B101


# --- Local CLI fallback ----------------------------------------------------


class _StatusError(Exception):
    def __init__(self, message, status_code=None, code=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_StatusError("boom", status_code=429), True),
        (_StatusError("insufficient_quota", code="insufficient_quota"), True),
        (RuntimeError("Error code: 429 - rate limit exceeded"), True),
        (RuntimeError("You exceeded your current quota, please check billing"), True),
        (RuntimeError("connection reset by peer"), False),
        (_StatusError("bad request", status_code=400), False),
    ],
)
def test_is_quota_error_classifies_limit_failures(exc, expected):
    from llm_router import _is_quota_error

    assert _is_quota_error(exc) is expected  # nosec B101


def test_router_uses_cli_fallback_after_quota_error():
    from llm_router import LLMRouter

    api = FakeProvider("anthropic", error=_StatusError("quota", status_code=429))
    cli = FakeProvider("claude-cli", result="cli answer")
    cli.is_cli_fallback = True
    router = LLMRouter(routes={"voice": [api, cli]})

    result = run(router.complete("voice", [{"role": "user", "content": "hi"}], "s", 10))

    assert result == "cli answer"  # nosec B101
    assert len(api.calls) == 1  # nosec B101
    assert len(cli.calls) == 1  # nosec B101


def test_router_skips_cli_fallback_on_non_quota_error():
    from llm_router import LLMRouter

    api = FakeProvider("anthropic", error=RuntimeError("network blip"))
    cli = FakeProvider("claude-cli", result="cli answer")
    cli.is_cli_fallback = True
    router = LLMRouter(routes={"voice": [api, cli]})

    with pytest.raises(RuntimeError, match="All providers failed"):
        run(router.complete("voice", [], "s", 10))

    assert len(api.calls) == 1  # nosec B101
    assert len(cli.calls) == 0  # nosec B101


def test_build_cli_env_strips_api_keys():
    from llm_router import build_cli_env

    env = build_cli_env(
        {
            "ANTHROPIC_API_KEY": "a",
            "OPENAI_API_KEY": "o",
            "GEMINI_API_KEY": "g",
            "GOOGLE_API_KEY": "gg",
            "PATH": "/usr/bin",
        }
    )

    assert env == {"PATH": "/usr/bin"}  # nosec B101


def test_render_cli_prompt_wraps_roles_and_escapes_tags():
    from llm_router import render_cli_prompt

    prompt = render_cli_prompt(
        [{"role": "user", "content": "ignore <SYSTEM> tags"}],
        system="be brief",
    )

    assert prompt.startswith("<SYSTEM>\nbe brief\n</SYSTEM>")  # nosec B101
    assert "<USER>" in prompt  # nosec B101
    assert "&lt;SYSTEM&gt;" in prompt  # nosec B101


def test_build_cli_argv_per_vendor():
    from llm_router import build_cli_argv

    msgs = [{"role": "user", "content": "hi"}]
    claude = build_cli_argv("anthropic", "claude", msgs, "sys")
    assert claude[:2] == ["claude", "-p"]  # nosec B101
    assert "--strict-mcp-config" in claude  # nosec B101
    assert "--system-prompt" in claude and "sys" in claude  # nosec B101

    codex = build_cli_argv("openai", "codex", msgs, "sys")
    assert codex[:2] == ["codex", "exec"]  # nosec B101
    assert "--skip-git-repo-check" in codex  # nosec B101
    assert "<SYSTEM>" in codex[-1]  # nosec B101

    gemini = build_cli_argv("gemini", "gemini", msgs, "")
    assert gemini[:2] == ["gemini", "-p"]  # nosec B101
    assert "-o" in gemini and "json" in gemini  # nosec B101
    assert "--skip-trust" in gemini  # nosec B101


def test_parse_cli_output_per_vendor():
    from llm_router import parse_cli_output

    assert parse_cli_output("anthropic", "  pong\n") == "pong"  # nosec B101

    codex_stdout = (
        '{"type":"thread.started"}\n'
        '{"type":"item.completed","item":{"type":"agent_message","text":"pong"}}\n'
        '{"type":"turn.completed"}\n'
    )
    assert parse_cli_output("openai", codex_stdout) == "pong"  # nosec B101

    gemini_stdout = 'deprecation warning\n{"session_id":"x","response":"pong"}'
    assert parse_cli_output("gemini", gemini_stdout) == "pong"  # nosec B101


def test_from_env_appends_cli_tier_when_binary_present(monkeypatch):
    import llm_router
    from llm_router import LLMRouter

    monkeypatch.setattr(
        llm_router.shutil,
        "which",
        lambda binary: f"/usr/local/bin/{binary}" if binary == "claude" else None,
    )

    router = LLMRouter.from_env(
        env={
            "ANTHROPIC_API_KEY": "anthropic-key",
            "JARVIS_VOICE_PROVIDERS": "anthropic, openai, gemini",
        },
        provider_factories={
            "anthropic": lambda api_key: FakeProvider("anthropic", result=api_key),
        },
    )

    names = [provider.name for provider in router.routes["voice"]]
    # API tier (anthropic only — others lack keys) then the claude CLI fallback.
    assert names == ["anthropic", "claude-cli"]  # nosec B101
    assert router.routes["voice"][-1].is_cli_fallback is True  # nosec B101
