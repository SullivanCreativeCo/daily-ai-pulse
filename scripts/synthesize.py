"""Send raw daily inputs to Claude and get back a markdown digest + Keegan-voice posts."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Tuple

from anthropic import Anthropic


PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "synthesizer.md"
MODEL = os.environ.get("PULSE_MODEL", "claude-sonnet-4-5")
FALLBACK_MODEL = "claude-haiku-4-5-20251001"

# Match a fenced ```json block, capture the JSON inside
_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _extract_posts(response_text: str) -> tuple[str, dict]:
    """Pull the trailing ```json block off the response.

    Returns (digest_md_without_json_block, posts_dict).
    posts_dict is {} if no parsable block found.
    """
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


def run(raw_inputs: dict, today: str) -> Tuple[str, dict]:
    """Call Claude. Return (digest_markdown, posts_dict)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    user_content = (
        f"Today is {today}.\n\n"
        f"Here are the raw inputs harvested today (JSON):\n\n"
        f"```json\n{json.dumps(raw_inputs, indent=2, default=str)}\n```\n\n"
        f"Produce both outputs per the system prompt. The digest first, then the social posts JSON block at the end."
    )

    def _call(model: str) -> str:
        msg = client.messages.create(
            model=model,
            max_tokens=6000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        chunks = []
        for block in msg.content:
            text = getattr(block, "text", None)
            if text:
                chunks.append(text)
        return "\n".join(chunks).strip()

    try:
        full_response = _call(MODEL)
    except Exception as e:
        print(f"[synthesize] {MODEL} failed: {e}; falling back to {FALLBACK_MODEL}")
        full_response = _call(FALLBACK_MODEL)

    return _extract_posts(full_response)
