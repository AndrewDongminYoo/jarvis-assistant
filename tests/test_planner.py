import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import planner  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class FakeRouter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def complete(self, task, messages, system, max_tokens):
        self.calls.append(
            {
                "task": task,
                "messages": messages,
                "system": system,
                "max_tokens": max_tokens,
            }
        )
        return f"router-replied-for-{task}"


def test_get_clarifying_questions_routes_to_plan_task(monkeypatch):
    fake = FakeRouter()
    monkeypatch.setattr(planner, "_router", fake)

    result = run(planner.get_clarifying_questions("Plan a Tokyo trip"))

    assert result == "router-replied-for-plan"  # nosec B101
    assert len(fake.calls) == 1  # nosec B101
    call = fake.calls[0]
    assert call["task"] == "plan"  # nosec B101
    assert call["max_tokens"] == 300  # nosec B101
    assert call["system"].startswith("You are JARVIS's planning module")  # nosec B101
    assert "Tokyo trip" in call["messages"][0]["content"]  # nosec B101


def test_generate_plan_assembles_three_message_turns(monkeypatch):
    fake = FakeRouter()
    monkeypatch.setattr(planner, "_router", fake)

    result = run(
        planner.generate_plan("Tokyo trip", "October, two weeks, culture-focused")
    )

    assert result == "router-replied-for-plan"  # nosec B101
    call = fake.calls[0]
    assert call["task"] == "plan"  # nosec B101
    assert call["max_tokens"] == 500  # nosec B101
    messages = call["messages"]
    assert len(messages) == 3  # nosec B101
    assert messages[0]["role"] == "user"  # nosec B101
    assert "Tokyo trip" in messages[0]["content"]  # nosec B101
    assert messages[1]["role"] == "assistant"  # nosec B101
    assert messages[2]["role"] == "user"  # nosec B101
    assert "October" in messages[2]["content"]  # nosec B101
    assert "numbered plan" in messages[2]["content"]  # nosec B101


def test_router_failure_propagates(monkeypatch):
    class FailingRouter:
        async def complete(self, *args, **kwargs):
            raise RuntimeError("all providers failed")

    monkeypatch.setattr(planner, "_router", FailingRouter())

    try:
        run(planner.get_clarifying_questions("anything"))
    except RuntimeError as exc:
        assert "all providers failed" in str(exc)  # nosec B101
        return
    raise AssertionError("expected RuntimeError to propagate")
