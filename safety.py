"""Action safety policy for JARVIS.

Pure-function module: no I/O, no LLM calls. Decisions are derived from the
action tag string and a small set of keyword tables. See
docs/specs/2026-05-11-general-agent-design.md for rationale.
"""

from __future__ import annotations

import re
import unicodedata
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
    "예",
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
    "don't",
    "dont",
    "do not",
    "아니",
    "아니요",
    "아니야",
    "취소",
    "그만",
    "하지마",
    "하지 마",
)


def _normalize(text: str) -> str:
    norm = " ".join(text.replace("’", "'").casefold().split())
    previous = None
    while norm != previous:
        previous = norm
        norm = norm.strip()
        while norm and unicodedata.category(norm[0]).startswith("P"):
            norm = norm[1:]
        while norm and unicodedata.category(norm[-1]).startswith("P"):
            norm = norm[:-1]
    return norm.strip()


def is_affirmative(text: str) -> bool:
    norm = _normalize(text)
    return bool(norm) and norm in _AFFIRMATIVE_TOKENS


def is_negative(text: str) -> bool:
    norm = _normalize(text)
    if not norm:
        return False
    return any(
        re.search(rf"(?<!\w){re.escape(token)}(?!\w)", norm)
        for token in _NEGATIVE_TOKENS
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
    "보내기",
    "전송",
    "삭제",
    "구매",
    "확인",
    "결제",
    "제출",
    "제거",
    "휴지통",
    "로그아웃",
    "폐기",
)

_BLOCKED_TERMINAL_PATTERNS = (
    re.compile(r"\bsudo\b"),
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\s*:\(\)\s*\{"),  # fork bomb
    re.compile(r"curl[^|]*\|\s*(sh|bash|zsh)\b"),
    re.compile(r"wget[^|]*\|\s*(sh|bash|zsh)\b"),
    re.compile(r">\s*/(etc|System|usr|bin|sbin)/"),
)

_BLOCKED_COMPUTER_ASCII_KEYWORDS = (
    "pay",
    "payment",
    "transfer",
    "bank",
    "password",
)

_BLOCKED_COMPUTER_KOREAN_KEYWORDS = (
    "송금",
    "결제",
    "이체",
    "비밀번호",
)


def _matching_blocked_computer_keyword(goal: str) -> str | None:
    low = goal.casefold()
    for keyword in _BLOCKED_COMPUTER_ASCII_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", low):
            return keyword
    for keyword in _BLOCKED_COMPUTER_KOREAN_KEYWORDS:
        if keyword in low:
            return keyword
    return None


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
            label_lower = label.lower()
            return (
                Decision.CONFIRM
                if any(r in label_lower for r in _RISKY_CLICK_LABELS)
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
        if _matching_blocked_computer_keyword(payload) is not None:
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
        keyword = _matching_blocked_computer_keyword(payload)
        if keyword is not None:
            return f"payment or credentials keyword: {keyword}"
    return f"unrecognized or unsafe action: {action}"
