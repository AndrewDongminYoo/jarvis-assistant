# work_mode.py — Persistent Claude Code sessions via claude CLI
import os
import subprocess
import uuid
from pathlib import Path

SESSIONS_DIR = Path("data/work_sessions")


def start_task(task_description: str) -> str:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_id = str(uuid.uuid4())[:8]
    output_file = SESSIONS_DIR / f"{session_id}.txt"
    prompt = f"Task: {task_description}\n\nPlease complete this task step by step."
    subprocess.Popen(
        ["claude", "-p", prompt],
        stdout=open(output_file, "w"),
        stderr=subprocess.STDOUT,
        cwd=os.getcwd(),
    )
    return (
        f"I've dispatched Claude Code to handle that, sir. "
        f"Session {session_id} is running in the background."
    )


def get_session_output(session_id: str) -> str:
    output_file = SESSIONS_DIR / f"{session_id}.txt"
    if not output_file.exists():
        return f"Session {session_id} not found."
    return output_file.read_text()[-2000:]
