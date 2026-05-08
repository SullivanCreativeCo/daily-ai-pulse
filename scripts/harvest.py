"""Daily AI Pulse harvester.

Defensive by design: if any source fails, log and continue. Never crash.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

# Allow `python scripts/harvest.py` from repo root
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

import youtube_lister
import exa_client
import synthesize
import render


load_dotenv()

ROOT = Path(__file__).parent.parent
SITE = ROOT / "site"
ARCHIVE_JSON = SITE / "archive.json"


PODCAST_SOURCES = [
    {"name": "The Koerner Office",
     "url": "https://www.youtube.com/@thekoerneroffice"},
    {"name": "Startup Ideas Podcast",
     "url": "https://www.youtube.com/playlist?list=PLQHTakJAwGLMQxKVlKUVpC7aiYTZ2j2J9"},
    {"name": "Corey Ganim",
     "url": "https://www.youtube.com/@coreyganim"},
    {"name": "AI Daily Brief",
     "url": "https://www.youtube.com/@AIDailyBrief"},
    {"name": "The Boring Marketer",
     "url": "https://www.youtube.com/@theboringmarketer"},
    {"name": "The Entrepreneur's Studio",
     "url": "https://www.youtube.com/@theentrepreneursstudio2010"},
]

NEWS_TOPICS = [
    {"key": "model_releases",
     "label": "AI model releases",
     "query": "new AI model release OR new LLM announcement OR foundation model launch"},
    {"key": "product_releases",
     "label": "AI product releases",
     "query": "new AI product launch OR AI app release OR AI tool shipping today"},
    {"key": "x_posts",
     "label": "Popular X posts about AI",
     "query": "popular trending tweets about AI agents and AI products",
     "include_domains": ["x.com", "twitter.com"]},
]


# ---------- archive helpers ----------

def _load_archive() -> list[dict]:
    if not ARCHIVE_JSON.exists():
        return []
    try:
        return json.loads(ARCHIVE_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[harvest] archive.json unreadable, starting fresh: {e}")
        return []


def _save_archive(entries: list[dict]) -> None:
    ARCHIVE_JSON.write_text(json.dumps(entries, indent=2, default=str), encoding="utf-8")


def _seen(entries: list[dict]) -> tuple[set[str], set[str]]:
    urls, vids = set(), set()
    for e in entries:
        u = e.get("url")
        v = e.get("video_id")
        if u: urls.add(u)
        if v: vids.add(v)
    return urls, vids


# ---------- harvesters ----------

def harvest_youtube(seen_video_ids: set[str]) -> list[dict]:
    """Return per-podcast video records with Exa-fetched content where possible."""
    results: list[dict] = []
    for src in PODCAST_SOURCES:
        try:
            videos = youtube_lister.list_recent(src["url"], max=3, exclude_ids=seen_video_ids)
        except Exception as e:
            print(f"[harvest] {src['name']} listing failed: {e}")
            continue
        for v in videos:
            content = {}
            try:
                content = exa_client.fetch_url(v["url"])
            except Exception as e:
                print(f"[harvest] exa fetch failed for {v['url']}: {e}")
            results.append({
                "source": src["name"],
                "video_id": v["video_id"],
                "title": v["title"],
                "url": v["url"],
                "exa_text": (content.get("text") or "")[:6000],
                "exa_highlights": content.get("highlights") or [],
                "low_content": content.get("low_content", True),
            })
    return results


def harvest_news(seen_urls: set[str]) -> dict[str, list[dict]]:
    """Return {topic_key: [items]} deduped by URL across topics."""
    yesterday = (dt.datetime.utcnow() - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    out: dict[str, list[dict]] = {}
    cross_topic_seen = set(seen_urls)
    for topic in NEWS_TOPICS:
        try:
            items = exa_client.search(
                query=topic["query"],
                category="news",
                start_published_date=yesterday,
                num_results=5,
                include_domains=topic.get("include_domains"),
            )
        except Exception as e:
            print(f"[harvest] news search failed for {topic['key']}: {e}")
            items = []

        keep = []
        for it in items:
            url = it.get("url")
            if not url or url in cross_topic_seen:
                continue
            cross_topic_seen.add(url)
            keep.append(it)
        out[topic["key"]] = keep
    return out


# ---------- main ----------

def _extract_headline(digest_md: str) -> str:
    """Pull the first paragraph under '## Today's headline'. Used for archive index."""
    m = re.search(r"##\s+Today's headline\s*\n+([^\n]+)", digest_md)
    if m:
        return m.group(1).strip()
    # fall back to first non-empty line after the H1
    for line in digest_md.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return "(no headline)"


def main() -> int:
    today = dt.datetime.utcnow().strftime("%Y-%m-%d")
    last_updated = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    archive = _load_archive()
    seen_urls, seen_vids = _seen(archive)
    print(f"[harvest] {today}: {len(archive)} archive entries, "
          f"{len(seen_urls)} seen urls, {len(seen_vids)} seen videos")

    # 1. YouTube
    yt_items = harvest_youtube(seen_vids)
    print(f"[harvest] youtube: {len(yt_items)} new videos")

    # 2. News
    news_by_topic = harvest_news(seen_urls)
    total_news = sum(len(v) for v in news_by_topic.values())
    print(f"[harvest] news: {total_news} items across {len(news_by_topic)} topics")

    posts = {"linkedin": [], "threads": []}

    # If we got literally nothing, still publish a tombstone so the page reflects today
    if not yt_items and not total_news:
        print("[harvest] no fresh inputs today; writing minimal placeholder")
        digest_md = (
            f"# Daily AI Pulse - {today}\n\n"
            f"## Today's headline\n"
            f"Quiet day in the harvest. No new podcast episodes or fresh news cleared the dedupe filter.\n\n"
            f"_Check back tomorrow._\n"
        )
    else:
        # 3. Synthesize (returns digest markdown + posts dict)
        raw_inputs = {
            "podcasts": yt_items,
            "news": news_by_topic,
            "topic_labels": {t["key"]: t["label"] for t in NEWS_TOPICS},
        }
        try:
            digest_md, posts = synthesize.run(raw_inputs, today)
        except Exception as e:
            print(f"[harvest] synthesis failed: {e}")
            digest_md = (
                f"# Daily AI Pulse - {today}\n\n"
                f"## Today's headline\n"
                f"Synthesis hit an error today. Raw inputs saved to archive.json. Error: {e}\n"
            )
            posts = {"linkedin": [], "threads": []}

    # 4. Render with posts injected
    render.write_today_and_archive(digest_md, today, last_updated, posts=posts)

    # 5. Update archive
    headline = _extract_headline(digest_md)
    archive.append({
        "kind": "digest",
        "date": today,
        "headline": headline,
        "url": f"archive/{today}.html",
        "posts": posts,
    })
    for v in yt_items:
        archive.append({
            "kind": "youtube",
            "date": today,
            "source": v["source"],
            "title": v["title"],
            "url": v["url"],
            "video_id": v["video_id"],
        })
    for topic_key, items in news_by_topic.items():
        for it in items:
            archive.append({
                "kind": "news",
                "date": today,
                "topic": topic_key,
                "title": it.get("title"),
                "url": it.get("url"),
                "snippet": (it.get("snippet") or "")[:400],
            })
    _save_archive(archive)

    # 6. Rebuild archive index
    render.render_archive_index(archive)

    print(f"[harvest] done: {today}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
