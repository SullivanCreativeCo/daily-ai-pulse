"""Send raw daily inputs to Claude and get back a polished markdown digest."""

from __future__ import annotations

import json
import os
from pathlib import Path

from anthropic import Anthropic


PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "synthesizer.md"
MODEL = os.environ.get("PULSE_MODEL", "claude-sonnet-4-5")
FALLBACK_MODEL = "claude-haiku-4-5-20251001"


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def run(raw_inputs: dict, today: str) -> str:
    """Call Claude with the synthesizer system prompt. Return markdown digest text."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    user_content = (
        f"Today is {today}.\n\n"
        f"Here are the raw inputs harvested today (JSON):\n\n"
        f"```json\n{json.dumps(raw_inputs, indent=2, default=str)}\n```\n\n"
        f"Produce the digest exactly per the system prompt format. "
        f"Skip any section that has no notable content."
    )

    def _call(model: str) -> str:
        msg = client.messages.create(
            model=model,
            max_tokens=4000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        # Claude returns a list of content blocks; we just want the text
        chunks = []
        for block in msg.content:
            text = getattr(block, "text", None)
            if text:
                chunks.append(text)
        return "\n".join(chunks).strip()

    try:
        return _call(MODEL)
    except Exception as e:
        print(f"[synthesize] {MODEL} failed: {e}; falling back to {FALLBACK_MODEL}")
        return _call(FALLBACK_MODEL)
