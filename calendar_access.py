# calendar_access.py — Read Apple Calendar via AppleScript with background cache
import logging
import os
import subprocess
import threading
import time

log = logging.getLogger("jarvis.calendar")

_cache: dict = {"events": [], "updated_at": 0.0}
_lock = threading.Lock()
CACHE_TTL = 300
APPLESCRIPT_TIMEOUT = 45

# Comma-separated list of calendar display names (substring match) to limit the
# scan. Recent macOS Calendar.app no longer exposes the "accounts" collection to
# AppleScript, so filtering is done against the visible calendar names instead
# (e.g. "ydm2790@gmail.com", "앤드류 (동민)"). Leave empty to scan every calendar.
CALENDAR_NAMES = [
    name.strip() for name in os.getenv("CALENDAR_NAMES", "").split(",") if name.strip()
]


def _build_calendar_script() -> str:
    if CALENDAR_NAMES:
        token_list = "{" + ", ".join(f'"{n}"' for n in CALENDAR_NAMES) + "}"
        cal_block = f"""set targets to {{}}
        repeat with aCal in calendars
            set calName to name of aCal
            repeat with tk in {token_list}
                if calName contains tk then
                    set end of targets to aCal
                    exit repeat
                end if
            end repeat
        end repeat"""
    else:
        cal_block = "set targets to every calendar"

    return f"""
with timeout of {APPLESCRIPT_TIMEOUT} seconds
    set resultList to {{}}
    set todayStart to (current date)
    set hours of todayStart to 0
    set minutes of todayStart to 0
    set seconds of todayStart to 0
    set weekEnd to todayStart + (7 * days)
    tell application "Calendar"
        {cal_block}
        repeat with aCal in targets
            repeat with ev in (every event of aCal whose start date >= todayStart and start date <= weekEnd)
                set evStart to start date of ev
                set evTitle to summary of ev
                set resultList to resultList & {{evTitle & " | " & (evStart as string)}}
            end repeat
        end repeat
    end tell
    set AppleScript's text item delimiters to linefeed
    return resultList as string
end timeout
"""


def _run(script: str) -> str:
    r = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=APPLESCRIPT_TIMEOUT,
    )
    if r.returncode != 0:
        # Surface AppleScript failures so they don't silently degrade to an
        # empty calendar. A previous version of this module iterated the now-
        # removed `accounts` collection and looked perfectly healthy in logs
        # because stderr was discarded.
        log.warning(
            "Calendar AppleScript failed (rc=%s): %s",
            r.returncode,
            r.stderr.strip(),
        )
    return r.stdout.strip()


def _fetch_events() -> list[dict]:
    raw = _run(_build_calendar_script())
    events: list[dict] = []
    if raw:
        for item in raw.split("\n"):
            parts = item.strip().split(" | ")
            if len(parts) == 2:
                events.append({"title": parts[0], "start": parts[1]})
    return events


def _refresh_cache() -> None:
    events = _fetch_events()
    with _lock:
        _cache["events"] = events
        _cache["updated_at"] = time.time()


def get_upcoming_events(force: bool = False) -> list[dict]:
    with _lock:
        age = time.time() - _cache["updated_at"]
    if force or age > CACHE_TTL:
        _refresh_cache()
    with _lock:
        return list(_cache["events"])


def get_events_summary() -> str:
    events = get_upcoming_events()
    if not events:
        return "Your calendar is clear for the next 7 days, sir."
    lines = [f"- {e['title']} at {e['start']}" for e in events[:10]]
    return "Upcoming events:\n" + "\n".join(lines)


def start_background_refresh() -> None:
    def _loop() -> None:
        while True:
            try:
                _refresh_cache()
            except Exception:
                pass
            time.sleep(CACHE_TTL)

    threading.Thread(target=_loop, daemon=True).start()
