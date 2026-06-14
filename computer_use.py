"""Anthropic Computer Use bridge for JARVIS.

Vision-grounded GUI automation fallback for apps that don't cleanly
expose macOS Accessibility (Figma, Electron canvases, games, web
embeds). Handles a single `[ACTION:COMPUTER:goal]` invocation by
running Anthropic's Computer Use tool-call loop until the model
produces a final text answer (or MAX_TURNS triggers).

pyobjc / anthropic / subprocess calls all happen inside the public
entrypoint and helpers below so the module imports cleanly under unit
tests that monkeypatch the seams.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("jarvis.computer")

# Anthropic Computer Use API surface
COMPUTER_TOOL_TYPE = "computer_20250124"
COMPUTER_USE_BETA = "computer-use-2025-01-24"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Loop and image bounds
MAX_TURNS = 25
MAX_SCALED_DIM = 1280  # cap longest edge; preserves aspect ratio
MAX_OUTPUT_TOKENS = 4096


def _model() -> str:
    """Return the Claude model id to drive the Computer Use loop."""
    return os.getenv("JARVIS_COMPUTER_MODEL", DEFAULT_MODEL)


def run_computer_goal(goal: str) -> str:
    """Run a Computer Use session for `goal` and return the final
    narrated result. Filled in by later tasks."""
    raise NotImplementedError
