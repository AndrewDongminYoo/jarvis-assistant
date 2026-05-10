# mail_access.py — Read-only Apple Mail access via AppleScript
import subprocess

APPLESCRIPT_TIMEOUT = 30


def _run(script: str) -> str:
    r = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=APPLESCRIPT_TIMEOUT,
    )
    return r.stdout.strip()


def get_unread_count() -> int:
    raw = _run('tell application "Mail" to return unread count of inbox')
    try:
        return int(raw)
    except ValueError:
        return 0


def get_recent_subjects(limit: int = 5) -> list[str]:
    script = f"""
tell application "Mail"
    set results to {{}}
    set counter to 0
    repeat with m in messages of inbox
        if counter >= {limit} then exit repeat
        set results to results & {{subject of m}}
        set counter to counter + 1
    end repeat
    return results
end tell
"""
    raw = _run(script)
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else []


def search_mail(query: str, limit: int = 5) -> list[dict]:
    escaped = query.replace('"', '\\"')
    script = f"""
tell application "Mail"
    set results to {{}}
    set counter to 0
    set msgs to (messages of inbox whose subject contains "{escaped}" or sender contains "{escaped}")
    repeat with m in msgs
        if counter >= {limit} then exit repeat
        set results to results & {{subject of m & " | " & sender of m}}
        set counter to counter + 1
    end repeat
    return results
end tell
"""
    raw = _run(script)
    items: list[dict] = []
    if raw:
        for line in raw.split(","):
            parts = line.strip().split(" | ")
            if len(parts) == 2:
                items.append({"subject": parts[0], "sender": parts[1]})
    return items


def get_mail_summary() -> str:
    count = get_unread_count()
    if count == 0:
        return "Your inbox is clear, sir."
    subjects = get_recent_subjects()
    lines = "\n".join(f"- {s}" for s in subjects)
    return f"You have {count} unread messages. Recent subjects:\n{lines}"
