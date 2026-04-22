# planner.py — Conversational task planning with clarifying questions
import os

from anthropic import Anthropic

_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

SYSTEM = (
    "You are JARVIS's planning module. "
    "For any complex task: first ask 3-5 targeted clarifying questions. "
    "Once you have answers, produce a concise numbered plan. "
    "Keep language brief — this output will be spoken aloud."
)


def get_clarifying_questions(task: str) -> str:
    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"User wants to: {task}\n\nAsk clarifying questions.",
            }
        ],
    )
    return resp.content[0].text  # type: ignore[union-attr]


def generate_plan(task: str, answers: str) -> str:
    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=SYSTEM,
        messages=[
            {"role": "user", "content": f"Task: {task}"},
            {"role": "assistant", "content": "Here are my clarifying questions."},
            {
                "role": "user",
                "content": f"Answers: {answers}\n\nNow produce the numbered plan.",
            },
        ],
    )
    return resp.content[0].text  # type: ignore[union-attr]
