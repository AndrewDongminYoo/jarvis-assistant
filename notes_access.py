# notes_access.py — Apple Notes: read and create via AppleScript (no edit/delete)
import subprocess
from typing import Optional


def _run(script: str) -> str:
    r = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=15
    )
    return r.stdout.strip()


def list_note_titles(limit: int = 20) -> list[str]:
    script = f"""
tell application "Notes"
    set results to {{}}
    set counter to 0
    repeat with n in notes
        if counter >= {limit} then exit repeat
        set results to results & {{name of n}}
        set counter to counter + 1
    end repeat
    return results
end tell
"""
    raw = _run(script)
    return [t.strip() for t in raw.split(",") if t.strip()] if raw else []


def read_note(title: str) -> Optional[str]:
    escaped = title.replace('"', '\\"')
    script = f"""
tell application "Notes"
    set matched to (notes whose name is "{escaped}")
    if length of matched > 0 then return body of item 1 of matched
    return ""
end tell
"""
    raw = _run(script)
    return raw if raw else None


def create_note(title: str, content: str) -> bool:
    et = title.replace('"', '\\"')
    ec = content.replace('"', '\\"').replace("\n", "\\n")
    script = f'tell application "Notes" to make new note with properties {{name:"{et}", body:"{ec}"}}'
    r = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=15
    )
    return r.returncode == 0
