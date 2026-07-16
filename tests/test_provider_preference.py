import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from anyio import run

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import planner  # noqa: E402
import server  # noqa: E402
from llm_router import LLMRouter, Message  # noqa: E402


@dataclass(frozen=True, slots=True)
class _Provider:
    name: str
    result: str

    async def complete(
        self,
        messages: list[Message],
        system: str,
        max_tokens: int,
    ) -> str:
        return self.result


def _router(provider: _Provider) -> LLMRouter:
    return LLMRouter(
        routes={task: [provider] for task in ("voice", "work", "plan", "narrate")}
    )


def test_plan_dispatch_uses_runtime_router(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.setattr(server, "_router", _router(_Provider("openai", "selected")))
    monkeypatch.setattr(planner, "_router", _router(_Provider("anthropic", "default")))

    # When
    result = run(server.dispatch_action, "PLAN:Ship the release")

    # Then
    assert result == "selected"  # nosec B101


def test_plan_answer_dispatch_uses_runtime_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setattr(server, "_router", _router(_Provider("openai", "selected")))
    monkeypatch.setattr(planner, "_router", _router(_Provider("anthropic", "default")))

    # When
    result = run(
        server.dispatch_action,
        "PLAN_ANSWER:Ship the release::Use the existing pipeline",
    )

    # Then
    assert result == "selected"  # nosec B101
