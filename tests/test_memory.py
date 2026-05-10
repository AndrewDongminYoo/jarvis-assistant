import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory import MAX_RECENT, Memory  # noqa: E402


def _new_memory() -> tuple[Memory, Path]:
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test.db"
    return Memory(db_path=db_path), db_path


def test_recent_starts_empty_for_fresh_db() -> None:
    mem, _ = _new_memory()
    assert mem.get_recent() == []


def test_add_exchange_appends_to_recent() -> None:
    mem, _ = _new_memory()
    mem.add_exchange("user", "hello")
    mem.add_exchange("assistant", "hi")
    assert mem.get_recent() == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_recent_hydrates_from_persisted_messages() -> None:
    mem1, path = _new_memory()
    mem1.add_exchange("user", "first")
    mem1.add_exchange("assistant", "second")
    mem1.conn.close()

    mem2 = Memory(db_path=path)
    assert mem2.get_recent() == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]


def test_hydration_caps_at_max_recent() -> None:
    mem1, path = _new_memory()
    total = MAX_RECENT + 5
    for i in range(total):
        mem1.add_exchange("user", f"msg {i}")
    mem1.conn.close()

    mem2 = Memory(db_path=path)
    recent = mem2.get_recent()
    assert len(recent) == MAX_RECENT
    assert recent[0]["content"] == f"msg {total - MAX_RECENT}"
    assert recent[-1]["content"] == f"msg {total - 1}"


def test_facts_round_trip() -> None:
    mem, _ = _new_memory()
    fact_id = mem.add_fact("user prefers metric units")
    assert fact_id > 0
    facts = mem.list_facts()
    assert len(facts) == 1
    assert facts[0]["fact"] == "user prefers metric units"
    assert mem.delete_fact(fact_id) is True
    assert mem.list_facts() == []


def test_facts_as_context_when_empty_returns_blank() -> None:
    mem, _ = _new_memory()
    assert mem.facts_as_context() == ""


def test_facts_as_context_lists_facts() -> None:
    mem, _ = _new_memory()
    mem.add_fact("uses VS Code")
    mem.add_fact("speaks Korean")
    ctx = mem.facts_as_context()
    assert "uses VS Code" in ctx
    assert "speaks Korean" in ctx


def test_search_returns_matching_messages() -> None:
    mem, _ = _new_memory()
    mem.add_exchange("user", "remind me about the dentist appointment")
    mem.add_exchange("assistant", "noted")
    hits = mem.search("dentist")
    assert len(hits) == 1
    assert "dentist" in hits[0]["content"]
