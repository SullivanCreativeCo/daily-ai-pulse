#!/bin/bash
# Daily AI Pulse runner. Invoked by launchd each morning.
# Activates venv, harvests + synthesizes (subscription via claude CLI), commits, pushes.

set -uo pipefail

REPO="/Users/sullivancreativeco./Projects/daily-ai-pulse"
LOG="$HOME/Library/Logs/daily-ai-pulse.log"
HEALTH="$HOME/Desktop/KeegsOS/workspace/command-center/pulse-health.json"
PULSE="$HOME/Desktop/KeegsOS/workspace/command-center/pulse-today.json"

mkdir -p "$(dirname "$LOG")"

# Best-effort macOS notification. Never fails the job.
notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"Daily AI Pulse\"" >/dev/null 2>&1 || true
}

# Record run health for the Command Center to surface. Always best-effort.
# args: <ok true|false> <status> <note>
write_health() {
  mkdir -p "$(dirname "$HEALTH")" 2>/dev/null || true
  local iso; iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cat > "$HEALTH" <<EOF 2>/dev/null || true
{
  "last_run_iso": "$iso",
  "ok": $1,
  "status": "$2",
  "note": "$3"
}
EOF
}

{
  echo
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') run_daily start ==="

  cd "$REPO" || { echo "FATAL: cannot cd $REPO"; write_health "false" "error" "cannot cd repo"; notify "Failed: cannot open repo"; exit 1; }

  # Pull latest in case GH Actions or another machine pushed
  git pull --ff-only origin main || echo "warn: git pull failed (continuing)"

  # Activate venv, then run harvest
  source .venv/bin/activate

  if ! python scripts/harvest.py; then
    echo "FATAL: harvest.py exited non-zero"
    write_health "false" "error" "harvest.py exited non-zero"
    notify "Harvest failed this morning. Pulse not refreshed."
    exit 2
  fi

  # Harvest succeeded at the process level. Read the status it recorded in the
  # sidecar: "tombstone" (no fresh inputs) or "error" (synthesis failed) both mean
  # the pulse is degraded even though the script didn't crash, so flag them.
  PULSE_STATUS="$(python -c "import json,sys; print(json.load(open('$PULSE')).get('status','ok'))" 2>/dev/null || echo "unknown")"
  case "$PULSE_STATUS" in
    ok)
      write_health "true" "ok" "pulse refreshed" ;;
    tombstone)
      write_health "false" "tombstone" "no fresh inputs cleared the dedupe filter"
      notify "Quiet harvest: no fresh AI news or episodes today." ;;
    error)
      write_health "false" "error" "synthesis step failed; raw inputs saved"
      notify "Pulse synthesis failed. Check the log." ;;
    *)
      write_health "false" "unknown" "could not read pulse status ($PULSE_STATUS)" ;;
  esac
  echo "pulse status: $PULSE_STATUS"

  # Stage and push if anything changed. The push is BEST-EFFORT: the KeegsOS
  # dashboard reads the local pulse-today.json sidecar and does not depend on the
  # push. So a no-network window (8am wake-up) or a blocked SSH port must not fail
  # the whole job. We try a normal push, then GitHub's port-443 SSH fallback (for
  # networks that block port 22), then leave the commit local for the next run.
  if ! git diff --quiet site/; then
    git add site/
    git -c user.name="daily-ai-pulse-bot" -c user.email="actions@github.com" \
        commit -m "Daily harvest $(date -u +%Y-%m-%d)"
    if git push origin main; then
      echo "pushed: $(git rev-parse --short HEAD)"
    elif GIT_SSH_COMMAND="ssh -o Hostname=ssh.github.com -o Port=443" git push origin main; then
      echo "pushed via ssh:443: $(git rev-parse --short HEAD)"
    else
      echo "warn: git push failed (commit kept local; dashboard unaffected, will push next run)"
    fi
  else
    echo "no site changes to commit"
  fi

  echo "=== done ==="
} >> "$LOG" 2>&1
