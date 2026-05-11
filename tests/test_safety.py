import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safety import Decision, is_affirmative, is_negative  # noqa: E402


def test_decision_enum_has_three_members():
    assert {d.name for d in Decision} == {"SAFE", "CONFIRM", "BLOCKED"}  # nosec B101


def test_is_affirmative_english_tokens():
    for text in ("yes", "Yeah", "ok", "okay", "sure", "go ahead", "do it"):
        assert is_affirmative(text) is True, text  # nosec B101


def test_is_affirmative_korean_tokens():
    for text in ("응", "그래", "해줘", "맞아", "좋아"):
        assert is_affirmative(text) is True, text  # nosec B101


def test_is_affirmative_rejects_others():
    for text in ("", "no", "cancel", "maybe later", "thinking about it"):
        assert is_affirmative(text) is False, text  # nosec B101


def test_is_negative_english_tokens():
    for text in ("no", "Nope", "cancel that", "stop", "abort", "nevermind"):
        assert is_negative(text) is True, text  # nosec B101


def test_is_negative_korean_tokens():
    for text in ("아니", "아니야", "취소", "그만", "하지마"):
        assert is_negative(text) is True, text  # nosec B101


def test_is_negative_rejects_others():
    for text in ("", "yes", "sure", "응", "go"):
        assert is_negative(text) is False, text  # nosec B101
