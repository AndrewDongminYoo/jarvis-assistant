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


_SAFE_KINDS = {
    "CALENDAR",
    "BROWSE",
    "SEARCH",
    "RECALL",
    "REMEMBER",
    "PLAN",
    "PLAN_ANSWER",
}
_CONFIRM_KINDS = {"FORGET", "WORK"}
_SAFE_NOTES_SUBS = {"LIST", "READ"}
_SAFE_TASK_SUBS = {"LIST"}
_SAFE_UI_SUBS = {"OBSERVE", "FOCUS", "SCROLL"}

_RISKY_CLICK_LABELS = (
    "send",
    "delete",
    "buy",
    "confirm",
    "pay",
    "submit",
    "remove",
    "trash",
    "sign out",
    "discard",
)

_BLOCKED_TERMINAL_PATTERNS = (
    re.compile(r"\bsudo\b"),
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"^\s*:\(\)\s*\{"),  # fork bomb
    re.compile(r"curl[^|]*\|\s*(sh|bash|zsh)\b"),
    re.compile(r"wget[^|]*\|\s*(sh|bash|zsh)\b"),
    re.compile(r">\s*/(etc|System|usr|bin|sbin)/"),
)

_BLOCKED_COMPUTER_KEYWORDS = (
    "pay",
    "payment",
    "transfer",
    "bank",
    "password",
    "송금",
    "결제",
    "이체",
    "비밀번호",
)


def _split(action: str) -> tuple[str, str]:
    """Return (kind_upper, payload). payload is everything after the first colon."""
    if ":" not in action:
        return action.upper(), ""
    kind, _, payload = action.partition(":")
    return kind.upper(), payload


def classify(action: str) -> Decision:
    if not action:
        return Decision.BLOCKED
    kind, payload = _split(action)

    if kind == "MAIL":
        head = payload.upper()
        if head == "SEND" or head.startswith("SEND:"):
            return Decision.CONFIRM
        return Decision.SAFE

    if kind in _SAFE_KINDS:
        return Decision.SAFE

    if kind == "NOTES":
        sub = payload.partition(":")[0].upper() or "LIST"
        return Decision.SAFE if sub in _SAFE_NOTES_SUBS else Decision.CONFIRM

    if kind == "TASK":
        sub = payload.partition(":")[0].upper() or "LIST"
        return Decision.SAFE if sub in _SAFE_TASK_SUBS else Decision.CONFIRM

    if kind == "UI":
        sub, _, rest = payload.partition(":")
        sub_u = sub.upper()
        if sub_u in _SAFE_UI_SUBS:
            return Decision.SAFE
        if sub_u == "CLICK":
            _role, _sep, label = rest.partition("::")
            ll = label.lower()
            return (
                Decision.CONFIRM
                if any(r in ll for r in _RISKY_CLICK_LABELS)
                else Decision.SAFE
            )
        if sub_u in {"TYPE", "KEY"}:
            return Decision.CONFIRM
        return Decision.CONFIRM

    if kind == "TERMINAL":
        if any(p.search(payload) for p in _BLOCKED_TERMINAL_PATTERNS):
            return Decision.BLOCKED
        return Decision.CONFIRM

    if kind == "COMPUTER":
        goal = payload.lower()
        if any(k in goal for k in _BLOCKED_COMPUTER_KEYWORDS):
            return Decision.BLOCKED
        return Decision.CONFIRM

    if kind in _CONFIRM_KINDS:
        return Decision.CONFIRM

    return Decision.BLOCKED


def reason(action: str) -> str:
    kind, payload = _split(action)
    if kind == "TERMINAL":
        for p in _BLOCKED_TERMINAL_PATTERNS:
            if p.search(payload):
                return f"dangerous shell pattern: {p.pattern}"
    if kind == "COMPUTER":
        low = payload.lower()
        for k in _BLOCKED_COMPUTER_KEYWORDS:
            if k in low:
                return f"payment or credentials keyword: {k}"
    return f"unrecognized or unsafe action: {action}"
