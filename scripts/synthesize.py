"""Send raw daily inputs to Claude (via the Claude Code CLI) and get back a markdown digest + Keegan-voice posts.

Uses the local `claude` CLI in headless mode (`claude -p`) so calls bill against
the Claude Code subscription via OAuth, not the pay-as-you-go Anthropic API.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Tuple


PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "synthesizer.md"
MODEL = os.environ.get("PULSE_MODEL", "sonnet")
FALLBACK_MODEL = os.environ.get("PULSE_FALLBACK_MODEL", "haiku")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")
CALL_TIMEOUT_SECS = int(os.environ.get("PULSE_TIMEOUT", "600"))

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _extract_posts(response_text: str) -> tuple[str, dict]:
    m = _JSON_BLOCK.search(response_text)
    if not m:
        return response_text.strip(), {"linkedin": [], "threads": []}
    raw = m.group(1)
    digest_md = response_text[: m.start()].rstrip() + "\n"
    try:
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[synthesize] JSON parse failed: {e}")
        return digest_md, {"linkedin": [], "threads": []}
    posts = {
        "linkedin": list(parsed.get("linkedin") or [])[:3],
        "threads": list(parsed.get("threads") or [])[:3],
    }
    return digest_md, posts


def _call_claude(model: str, system_prompt: str, user_content: str) -> str:
    if not Path(CLAUDE_BIN).exists():
        raise RuntimeError(f"claude CLI not found at {CLAUDE_BIN}. Set CLAUDE_BIN env var.")

    cmd = [
        CLAUDE_BIN,
        "-p",
        "--model", model,
        "--system-prompt", system_prompt,
        "--tools", "",
        "--no-session-persistence",
        "--output-format", "text",
    ]
    proc = subprocess.run(
        cmd,
        input=user_content,
        text=True,
        capture_output=True,
        timeout=CALL_TIMEOUT_SECS,
    )
    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "").strip()[-500:]
        raise RuntimeError(f"claude -p exit {proc.returncode}: {stderr_tail}")
    return (proc.stdout or "").strip()


def run(raw_inputs: dict, today: str) -> Tuple[str, dict]:
    """Call Claude. Return (digest_markdown, posts_dict)."""
    system_prompt = _load_system_prompt()
    user_content = (
        f"Today is {today}.\n\n"
        f"Here are the raw inputs harvested today (JSON):\n\n"
        f"```json\n{json.dumps(raw_inputs, indent=2, default=str)}\n```\n\n"
        f"Produce both outputs per the system prompt. The digest first, then the social posts JSON block at the end."
    )

    try:
        full_response = _call_claude(MODEL, system_prompt, user_content)
    except Exception as e:
        print(f"[synthesize] {MODEL} failed: {e}; falling back to {FALLBACK_MODEL}")
        full_response = _call_claude(FALLBACK_MODEL, system_prompt, user_content)

    return _extract_posts(full_response)
