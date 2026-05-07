"""Exa.ai wrapper for news search and per-URL content fetching."""

from __future__ import annotations

import os
from typing import Optional

from exa_py import Exa


_client: Optional[Exa] = None


def _get_client() -> Exa:
    global _client
    if _client is None:
        key = os.environ.get("EXA_API_KEY")
        if not key:
            raise RuntimeError("EXA_API_KEY not set")
        _client = Exa(api_key=key)
    return _client


def search(
    query: str,
    category: str = "news",
    start_published_date: Optional[str] = None,
    num_results: int = 5,
    include_domains: Optional[list] = None,
) -> list[dict]:
    """Run an Exa /search call. Returns clean dicts.

    Each dict: {title, url, published_date, author, score, snippet}.
    """
    client = _get_client()
    kwargs = {
        "num_results": num_results,
        "type": "auto",
    }
    if category:
        kwargs["category"] = category
    if start_published_date:
        kwargs["start_published_date"] = start_published_date
    if include_domains:
        kwargs["include_domains"] = include_domains

    try:
        resp = client.search_and_contents(
            query,
            text={"max_characters": 1500},
            highlights={"num_sentences": 3, "highlights_per_url": 1},
            **kwargs,
        )
    except Exception as e:
        print(f"[exa_client] search failed for '{query}': {e}")
        return []

    out: list[dict] = []
    for r in getattr(resp, "results", []) or []:
        text = getattr(r, "text", "") or ""
        highlights = getattr(r, "highlights", None) or []
        snippet = (highlights[0] if highlights else text[:600]).strip()
        out.append({
            "title": getattr(r, "title", "") or "",
            "url": getattr(r, "url", "") or "",
            "published_date": getattr(r, "published_date", None),
            "author": getattr(r, "author", None),
            "score": getattr(r, "score", None),
            "snippet": snippet,
            "low_content": len(text) < 200,
        })
    return out


def fetch_url(
    url: str,
    text: bool = True,
    highlights: bool = True,
    livecrawl: str = "always",
) -> dict:
    """Fetch a single URL via Exa /contents. Returns {title, url, text, highlights, low_content}.

    For YouTube URLs, Exa returns transcript-quality content for ~50% of videos
    (the cached/popular ones). The rest come back light — flagged as low_content.
    """
    client = _get_client()
    try:
        resp = client.get_contents(
            urls=[url],
            text={"max_characters": 8000} if text else False,
            highlights={"num_sentences": 4, "highlights_per_url": 3} if highlights else False,
            livecrawl=livecrawl,
        )
    except Exception as e:
        print(f"[exa_client] fetch_url failed for {url}: {e}")
        return {"url": url, "title": "", "text": "", "highlights": [], "low_content": True, "error": str(e)}

    results = getattr(resp, "results", []) or []
    if not results:
        return {"url": url, "title": "", "text": "", "highlights": [], "low_content": True}
    r = results[0]
    body = getattr(r, "text", "") or ""
    return {
        "url": getattr(r, "url", "") or url,
        "title": getattr(r, "title", "") or "",
        "text": body,
        "highlights": getattr(r, "highlights", None) or [],
        "low_content": len(body) < 400,
    }
