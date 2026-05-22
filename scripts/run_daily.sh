#!/bin/bash
# Daily AI Pulse runner. Invoked by launchd each morning.
# Activates venv, harvests + synthesizes (subscription via claude CLI), commits, pushes.

set -uo pipefail

REPO="/Users/sullivancreativeco./Projects/daily-ai-pulse"
LOG="$HOME/Library/Logs/daily-ai-pulse.log"

mkdir -p "$(dirname "$LOG")"

{
  echo
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') run_daily start ==="

  cd "$REPO" || { echo "FATAL: cannot cd $REPO"; exit 1; }

  # Pull latest in case GH Actions or another machine pushed
  git pull --ff-only origin main || echo "warn: git pull failed (continuing)"

  # Activate venv, then run harvest
  source .venv/bin/activate

  if ! python scripts/harvest.py; then
    echo "FATAL: harvest.py exited non-zero"
    exit 2
  fi

  # Stage and push if anything changed
  if ! git diff --quiet site/; then
    git add site/
    git -c user.name="daily-ai-pulse-bot" -c user.email="actions@github.com" \
        commit -m "Daily harvest $(date -u +%Y-%m-%d)"
    if ! git push origin main; then
      echo "warn: git push failed"
      exit 3
    fi
    echo "pushed: $(git rev-parse --short HEAD)"
  else
    echo "no site changes to commit"
  fi

  echo "=== done ==="
} >> "$LOG" 2>&1
