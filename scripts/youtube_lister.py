"""Thin wrapper around yt-dlp flat-playlist extraction.

Listing a channel/playlist works fine from datacenter IPs (GitHub Actions).
Downloading captions does NOT — that path is blocked.
For transcripts we go through Exa /contents instead (see exa_client.fetch_url).
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

import yt_dlp


def published_within_days(video_id: str, days: int) -> bool:
    """Best-effort recency check for a single video.

    Flat-playlist extraction returns no upload date, so to filter stale uploads we
    probe one video's metadata. This is only called for un-seen candidates (a small
    number per run), and runs locally (residential IP), so the cost is bounded.

    Returns True on any failure or missing date: never drop a video on uncertainty.
    """
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
    except Exception as e:
        print(f"[youtube_lister] age probe failed for {video_id}: {e}")
        return True

    info = info or {}
    ts = info.get("timestamp") or info.get("release_timestamp")
    if ts:
        age_days = (dt.datetime.now(dt.timezone.utc).timestamp() - ts) / 86400
        return age_days <= days

    upd = info.get("upload_date")  # YYYYMMDD string
    if upd:
        try:
            d = dt.datetime.strptime(upd, "%Y%m%d").replace(tzinfo=dt.timezone.utc)
            return (dt.datetime.now(dt.timezone.utc) - d).days <= days
        except Exception:
            return True
    return True


def _normalize_channel_url(url: str) -> str:
    """Make sure @handle URLs end with /videos so flat-playlist gets the upload feed."""
    if "/playlist?" in url or "/videos" in url:
        return url
    if "youtube.com/@" in url:
        return url.rstrip("/") + "/videos"
    return url


def list_recent(url: str, max: int = 5, exclude_ids: Iterable[str] | None = None) -> list[dict]:
    """Return up to `max` recent videos from a channel or playlist URL.

    Each item: {"video_id": str, "title": str, "url": str}.
    Anything in exclude_ids is filtered out (used to skip already-seen videos).
    """
    exclude = set(exclude_ids or [])
    target = _normalize_channel_url(url)

    opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "playlistend": max * 3,  # over-fetch in case some are filtered
    }

    out: list[dict] = []
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)
    except Exception as e:
        print(f"[youtube_lister] failed to list {target}: {e}")
        return out

    entries = (info or {}).get("entries") or []
    for entry in entries:
        if not entry:
            continue
        vid = entry.get("id")
        title = entry.get("title")
        if not vid or not title:
            continue
        if vid in exclude:
            continue
        out.append({
            "video_id": vid,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
        if len(out) >= max:
            break
    return out


if __name__ == "__main__":
    import json, sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/@thekoerneroffice"
    print(json.dumps(list_recent(url, max=3), indent=2))
