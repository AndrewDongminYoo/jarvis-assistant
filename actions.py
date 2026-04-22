# actions.py — System-level AppleScript actions for JARVIS
import subprocess


def _osascript(script: str) -> tuple[bool, str]:
    r = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=15
    )
    return r.returncode == 0, r.stdout.strip()


def open_terminal(command: str = "") -> bool:
    if command:
        escaped = command.replace('"', '\\"')
        script = f'tell app "Terminal" to do script "{escaped}"'
    else:
        script = 'tell app "Terminal" to activate'
    ok, _ = _osascript(script)
    return ok


def open_chrome(url: str = "") -> bool:
    script = (
        f'open location "{url}"'
        if url
        else 'tell application "Google Chrome" to activate'
    )
    ok, _ = _osascript(script)
    return ok


def show_notification(title: str, message: str) -> bool:
    et = title.replace('"', '\\"')
    em = message.replace('"', '\\"')
    ok, _ = _osascript(f'display notification "{em}" with title "{et}"')
    return ok


def speak_macos(text: str, voice: str = "Daniel") -> None:
    subprocess.run(["say", "-v", voice, text], timeout=60)
