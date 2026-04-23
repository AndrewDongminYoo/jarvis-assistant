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


def test_from_env_skips_missing_provider_keys_and_keeps_route_priority():
    from llm_router import LLMRouter

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
