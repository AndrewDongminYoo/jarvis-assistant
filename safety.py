"""Action safety policy for JARVIS.

Pure-function module: no I/O, no LLM calls. Decisions are derived from the
action tag string and a small set of keyword tables. See
docs/specs/2026-05-11-general-agent-design.md for rationale.
"""

from __future__ import annotations

import re
from enum import Enum


class Decision(Enum):
    SAFE = "safe"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


_AFFIRMATIVE_TOKENS = (
    "yes",
    "yeah",
    "yep",
    "yup",
    "ok",
    "okay",
    "sure",
    "go ahead",
    "go",
    "do it",
    "응",
    "그래",
    "해",
    "해줘",
    "맞아",
    "좋아",
)

_NEGATIVE_TOKENS = (
    "no",
    "nope",
    "cancel",
    "stop",
    "abort",
    "nevermind",
    "never mind",
    "아니",
    "아니야",
    "취소",
    "그만",
    "하지마",
)


def _normalize(text: str) -> str:
    return text.strip().lower()


def is_affirmative(text: str) -> bool:
    norm = _normalize(text)
    if not norm:
        return False
    return any(
        re.search(rf"\b{re.escape(token)}\b", norm) for token in _AFFIRMATIVE_TOKENS
    )


def is_negative(text: str) -> bool:
    norm = _normalize(text)
    if not norm:
        return False
    return any(
        re.search(rf"\b{re.escape(token)}\b", norm) for token in _NEGATIVE_TOKENS
    )
