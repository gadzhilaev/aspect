#!/bin/sh
# Optional Telegram outbox worker — same DB volume as API/scheduler.
# Does not start unless Compose profile `telegram` is enabled AND TELEGRAM_BOT_TOKEN is set.
# No tokens in the image; runtime env only. Loops existing `python -m app.workers.notification_worker`.
set -eu

STAND_DIR="${COMPETITION_STAND_DIR:-/stand}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////stand/stand.db}"
export BANK_MATERIALS_STORAGE_ROOT="${BANK_MATERIALS_STORAGE_ROOT:-/stand/storage}"
export APP_ENV="${APP_ENV:-production}"
export COMPETITION_MODE="${COMPETITION_MODE:-true}"
export NEWS_SCHEDULER_STATE_DIR="${NEWS_SCHEDULER_STATE_DIR:-/stand/news_scheduler_runtime}"

if [ ! -f "${STAND_DIR}/stand.db" ]; then
  echo "telegram_worker: ${STAND_DIR}/stand.db missing — bootstrap/migrate first" >&2
  exit 1
fi

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "telegram_worker: TELEGRAM_BOT_TOKEN unset — refusing (optional service; do not enable without secrets)" >&2
  exit 2
fi

# Worker may run under polling or webhook ingress; it only drains outbox.
INTERVAL="${TELEGRAM_WORKER_INTERVAL_SECONDS:-5}"
echo "telegram_worker: DATABASE_URL=${DATABASE_URL} interval=${INTERVAL}s kinds=${TELEGRAM_OUTBOX_KINDS:-<all>}"

while true; do
  python -m app.workers.notification_worker || true
  sleep "$INTERVAL"
done
