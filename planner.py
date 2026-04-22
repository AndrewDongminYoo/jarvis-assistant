# planner.py — Conversational task planning with clarifying questions
from llm_router import LLMRouter

_router = LLMRouter.from_env()

SYSTEM = (
    "You are JARVIS's planning module. "
    "For any complex task: first ask 3-5 targeted clarifying questions. "
    "Once you have answers, produce a concise numbered plan. "
    "Keep language brief — this output will be spoken aloud."
)


async def get_clarifying_questions(task: str) -> str:
    return await _router.complete(
        task="plan",
        max_tokens=300,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"User wants to: {task}\n\nAsk clarifying questions.",
            }
        ],
    )


async def generate_plan(task: str, answers: str) -> str:
    return await _router.complete(
        task="plan",
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
