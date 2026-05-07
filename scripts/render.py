"""Convert the daily digest markdown into a polished HTML page.

Two outputs per day:
  - site/index.html             (overwritten, today's view)
  - site/archive/YYYY-MM-DD.html (permanent archive copy)

Also rebuilds:
  - site/archive.html           (chronological index with client-side keyword filter)

Includes two preprocessors that fix limitations of markdown2 for our prompt format:
  - _lift_nested_quotes: pulls `  > "quote"` lines out of list items into
    standalone blockquotes so they render as `<blockquote>` instead of `&gt;`.
  - _autolink_bare_urls: wraps bare https URLs in `<...>` so they become links.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import markdown2


SITE = Path(__file__).parent.parent / "site"


_LIST_MARKER = re.compile(r"^(\s*[-*]|\s*\d+\.)\s+")
_QUOTE_INSIDE = re.compile(r"^( {2,})>\s?(.*)$")
_BARE_URL = re.compile(r"(\s|^)(https?://[^\s<>)\]]+)")


def _lift_nested_quotes(md: str) -> str:
    """Lift `  > ...` lines from list items into top-level blockquotes."""
    out_lines: list[str] = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if _LIST_MARKER.match(line):
            block = [line]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    block.append(nxt)
                    i += 1
                    break
                if nxt.startswith("  ") and not _LIST_MARKER.match(nxt):
                    block.append(nxt)
                    i += 1
                else:
                    break
            quote_lines = [_QUOTE_INSIDE.match(b).group(2) for b in block if _QUOTE_INSIDE.match(b)]
            non_quote = [b for b in block if not _QUOTE_INSIDE.match(b)]
            out_lines.extend(non_quote)
            for q in quote_lines:
                out_lines.append("")
                out_lines.append("> " + q)
                out_lines.append("")
        else:
            out_lines.append(line)
            i += 1
    return "\n".join(out_lines)


def _autolink_bare_urls(md: str) -> str:
    """Wrap bare https URLs in <...> so markdown2 autolinks them.

    Skips lines that already look like markdown link syntax `[txt](url)` or `<url>`.
    """
    out: list[str] = []
    for line in md.split("\n"):
        if "](" in line or "<http" in line:
            out.append(line)
            continue
        def _wrap(m: re.Match) -> str:
            return m.group(1) + "<" + m.group(2) + ">"
        out.append(_BARE_URL.sub(_wrap, line))
    return "\n".join(out)


PAGE_SHELL = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="icon" type="image/svg+xml" href="{root}assets/favicon.svg" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,700&family=Inter:wght@400;500;600&display=swap" />
  <link rel="stylesheet" href="{root}assets/styles.css" />
</head>
<body>
  <header class="site-header">
    <a class="logo" href="{root}index.html">Daily AI Pulse</a>
    <nav>
      <a href="{root}index.html">Today</a>
      <a href="{root}archive.html">Archive</a>
    </nav>
  </header>
  <main class="reading-column">
    {meta}
    <article class="digest">
{body}
    </article>
  </main>
  <footer class="site-footer">
    <p>Harvested daily. Synthesized by Claude. Built for builders.</p>
  </footer>
</body>
</html>
"""


def _render_meta(date: str, last_updated: Optional[str]) -> str:
    bits = ['<p class="dateline">' + date + "</p>"]
    if last_updated:
        bits.append('<p class="last-updated">Last updated ' + last_updated + " UTC</p>")
    return "\n    ".join(bits)


def markdown_to_html(digest_md: str, date: str, last_updated: Optional[str] = None,
                    is_archive_page: bool = False) -> str:
    """Render the digest markdown into a fully-styled HTML page."""
    pre = _autolink_bare_urls(_lift_nested_quotes(digest_md))
    body = markdown2.markdown(
        pre,
        extras=["fenced-code-blocks", "tables", "header-ids", "cuddled-lists", "target-blank-links"],
    )
    title = "Daily AI Pulse — " + date
    root = "../" if is_archive_page else ""
    return PAGE_SHELL.format(
        title=title,
        root=root,
        meta=_render_meta(date, last_updated),
        body=body,
    )


def write_today_and_archive(digest_md: str, date: str, last_updated: str) -> None:
    """Write index.html (today) and archive/<date>.html (permanent)."""
    today_html = markdown_to_html(digest_md, date, last_updated, is_archive_page=False)
    archive_html = markdown_to_html(digest_md, date, last_updated, is_archive_page=True)

    (SITE / "index.html").write_text(today_html, encoding="utf-8")
    (SITE / "archive").mkdir(parents=True, exist_ok=True)
    (SITE / "archive" / (date + ".html")).write_text(archive_html, encoding="utf-8")


ARCHIVE_INDEX_SHELL = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Archive — Daily AI Pulse</title>
  <link rel="icon" type="image/svg+xml" href="assets/favicon.svg" />
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,700&family=Inter:wght@400;500;600&display=swap" />
  <link rel="stylesheet" href="assets/styles.css" />
</head>
<body>
  <header class="site-header">
    <a class="logo" href="index.html">Daily AI Pulse</a>
    <nav>
      <a href="index.html">Today</a>
      <a href="archive.html">Archive</a>
    </nav>
  </header>
  <main class="reading-column">
    <h1 class="archive-title">Archive</h1>
    <input id="filter" type="search" placeholder="Filter by keyword..." class="filter-input" />
    <ul class="archive-list" id="archive-list">
__ITEMS__
    </ul>
  </main>
  <footer class="site-footer">
    <p>Harvested daily. Synthesized by Claude.</p>
  </footer>
  <script>
    const input = document.getElementById('filter');
    const list = document.getElementById('archive-list');
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      for (const li of list.children) {
        const hay = li.textContent.toLowerCase();
        li.style.display = !q || hay.includes(q) ? '' : 'none';
      }
    });
  </script>
</body>
</html>
"""


def render_archive_index(archive_entries: list[dict]) -> None:
    """Build archive.html from archive.json entries."""
    by_date: dict[str, dict] = {}
    for e in archive_entries:
        d = e.get("date")
        if not d:
            continue
        if d not in by_date and e.get("kind") == "digest":
            by_date[d] = e
    for e in archive_entries:
        d = e.get("date")
        if d and d not in by_date:
            by_date[d] = {"date": d, "headline": e.get("headline") or e.get("title") or ""}

    rows = []
    for d in sorted(by_date.keys(), reverse=True):
        entry = by_date[d]
        headline = entry.get("headline") or "(no headline)"
        rows.append(
            '      <li class="archive-item">'
            '<a href="archive/' + d + '.html"><span class="archive-date">' + d + '</span>'
            '<span class="archive-headline">' + headline + '</span></a></li>'
        )

    html = ARCHIVE_INDEX_SHELL.replace("__ITEMS__", "\n".join(rows) or "      <li>(no archive yet)</li>")
    (SITE / "archive.html").write_text(html, encoding="utf-8")
