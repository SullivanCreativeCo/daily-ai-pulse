# Daily AI Pulse

A self-hosted daily AI digest. Runs every morning via GitHub Actions, harvests from a curated set of sources, synthesizes through Claude, publishes a polished static page to GitHub Pages.

Bookmark it. Read it with coffee. Steal the content angles.

## How it works

1. GitHub Actions fires at 13:00 UTC (~8am ET).
2. `scripts/harvest.py` lists fresh podcast episodes (yt-dlp), pulls news (Exa), fetches per-URL content (Exa).
3. `scripts/synthesize.py` sends the raw inputs to Claude with the system prompt in `prompts/synthesizer.md`.
4. `scripts/render.py` writes `site/index.html`, `site/archive/YYYY-MM-DD.html`, and rebuilds `site/archive.html`.
5. The workflow commits the changes back to `main`. GitHub Pages auto-deploys.

## Setup

1. Push this repo to GitHub.
2. **Settings** → **Pages**: source = `Deploy from branch`, branch = `main`, folder = `/site`.
3. **Settings** → **Secrets and variables** → **Actions**, add:
   - `ANTHROPIC_API_KEY` (from console.anthropic.com)
   - `EXA_API_KEY` (from exa.ai)
4. **Settings** → **Actions** → **General** → **Workflow permissions**: enable "Read and write permissions".
5. Go to **Actions** tab → **Daily AI Pulse Harvest** → **Run workflow** to publish the first edition.
6. Bookmark `https://<username>.github.io/<repo-name>/`.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in keys
python scripts/harvest.py
open site/index.html
```

## Customize

- **Podcasts**: edit `PODCAST_SOURCES` in `scripts/harvest.py`.
- **News topics**: edit `NEWS_TOPICS` in the same file.
- **Voice/format**: edit `prompts/synthesizer.md`.
- **Look**: edit `site/assets/styles.css` (single accent color is `--accent`).
- **Schedule**: edit the cron in `.github/workflows/daily-harvest.yml`.

## Notes

- YouTube transcript fetching is blocked from datacenter IPs. We work around it by using Exa's `/contents` endpoint with `livecrawl: "always"`. About half the videos come back with usable transcript content; the rest get listed with title + URL only.
- The synthesizer is told to omit empty sections, so quiet days produce shorter pages.
- All raw inputs land in `site/archive.json` so you can mine the historical record later.
