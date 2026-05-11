import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calendar_access  # noqa: E402


def test_default_script_targets_every_calendar(monkeypatch):
    monkeypatch.setattr(calendar_access, "CALENDAR_NAMES", [])
    script = calendar_access._build_calendar_script()
    assert "set targets to every calendar" in script  # nosec B101
    assert "repeat with aCal in calendars" not in script  # nosec B101


def test_filtered_script_loops_calendars_and_emits_token_list(monkeypatch):
    monkeypatch.setattr(
        calendar_access,
        "CALENDAR_NAMES",
        ["ydm2790@gmail.com", "앤드류 (동민)"],
    )
    script = calendar_access._build_calendar_script()
    # New script iterates Calendar.app's `calendars` collection directly —
    # the `accounts` collection was removed from the scriptable surface.
    assert "repeat with aCal in calendars" in script  # nosec B101
    assert "name of aCal" in script  # nosec B101
    assert '"ydm2790@gmail.com"' in script  # nosec B101
    assert '"앤드류 (동민)"' in script  # nosec B101
    assert "repeat with acct in accounts" not in script  # nosec B101
    assert "set targets to every calendar" not in script  # nosec B101


def test_run_logs_warning_on_applescript_failure(monkeypatch, caplog):
    """A non-zero returncode from osascript must surface, not silently turn
    into empty stdout — that is exactly how the previous `accounts` regression
    hid for months."""
    import subprocess as _sp

    class FakeCompleted:
        returncode = 1
        stdout = ""
        stderr = "execution error: The variable accounts is not defined. (-2753)"

    def fake_run(*args, **kwargs):
        return FakeCompleted()

    monkeypatch.setattr(_sp, "run", fake_run)
    with caplog.at_level("WARNING", logger="jarvis.calendar"):
        result = calendar_access._run("ignored")
    assert result == ""  # nosec B101
    assert any(
        "AppleScript failed" in rec.message for rec in caplog.records
    )  # nosec B101


def test_script_wraps_in_with_timeout_block():
    script = calendar_access._build_calendar_script()
    assert (
        f"with timeout of {calendar_access.APPLESCRIPT_TIMEOUT} seconds" in script
    )  # nosec B101
    assert "end timeout" in script  # nosec B101


def test_script_uses_seven_day_window():
    script = calendar_access._build_calendar_script()
    assert "todayStart + (7 * days)" in script  # nosec B101
    assert "start date >= todayStart" in script  # nosec B101
    assert "start date <= weekEnd" in script  # nosec B101


def test_fetch_events_parses_newline_delimited_rows(monkeypatch):
    raw = (
        "Standup | Monday, May 13, 2026 at 09:00:00\n"
        "Lunch | Monday, May 13, 2026 at 12:00:00"
    )
    monkeypatch.setattr(calendar_access, "_run", lambda script: raw)
    events = calendar_access._fetch_events()
    assert len(events) == 2  # nosec B101
    assert events[0] == {  # nosec B101
        "title": "Standup",
        "start": "Monday, May 13, 2026 at 09:00:00",
    }
    assert events[1]["title"] == "Lunch"  # nosec B101


def test_script_joins_results_with_linefeed_delimiter():
    script = calendar_access._build_calendar_script()
    assert "AppleScript's text item delimiters to linefeed" in script  # nosec B101
    assert "return resultList as string" in script  # nosec B101


def test_fetch_events_returns_empty_when_run_blank(monkeypatch):
    monkeypatch.setattr(calendar_access, "_run", lambda script: "")
    assert calendar_access._fetch_events() == []  # nosec B101


def test_get_events_summary_handles_empty(monkeypatch):
    monkeypatch.setattr(calendar_access, "get_upcoming_events", lambda: [])
    summary = calendar_access.get_events_summary()
    assert "clear" in summary.lower()  # nosec B101


def test_get_events_summary_lists_first_ten(monkeypatch):
    fake_events = [{"title": f"Event {i}", "start": f"t{i}"} for i in range(15)]
    monkeypatch.setattr(calendar_access, "get_upcoming_events", lambda: fake_events)
    summary = calendar_access.get_events_summary()
    assert "Upcoming events" in summary  # nosec B101
    assert "Event 0" in summary  # nosec B101
    assert "Event 9" in summary  # nosec B101
    assert "Event 10" not in summary  # nosec B101
