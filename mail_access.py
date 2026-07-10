import subprocess

APPLESCRIPT_TIMEOUT = 30


def _escape_applescript_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


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


def send_mail(recipient: str, body: str) -> bool:
    recipient_clean = recipient.strip()
    body_clean = body.strip()
    if not recipient_clean or not body_clean:
        return False

    escaped_recipient = _escape_applescript_string(recipient_clean)
    escaped_body = _escape_applescript_string(body_clean)
    script = f"""
tell application "Mail"
    set newMessage to make new outgoing message with properties {{visible:false, subject:"Message from JARVIS", content:"{escaped_body}"}}
    tell newMessage
        make new to recipient at end of to recipients with properties {{address:"{escaped_recipient}"}}
        send
    end tell
end tell
"""
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=APPLESCRIPT_TIMEOUT,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
