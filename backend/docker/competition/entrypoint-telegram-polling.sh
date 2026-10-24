#!/bin/sh
# Optional Telegram getUpdates polling — mutually exclusive with active webhook ingress.
# Uses existing `python -m app.workers.telegram_polling` (refuses getWebhookInfo.url ≠ empty).
set -eu

STAND_DIR="${COMPETITION_STAND_DIR:-/stand}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////stand/stand.db}"
export BANK_MATERIALS_STORAGE_ROOT="${BANK_MATERIALS_STORAGE_ROOT:-/stand/storage}"
export APP_ENV="${APP_ENV:-production}"
export COMPETITION_MODE="${COMPETITION_MODE:-true}"
export TELEGRAM_POLLING_STATE_DIR="${TELEGRAM_POLLING_STATE_DIR:-/stand/telegram_runtime}"

mkdir -p "$TELEGRAM_POLLING_STATE_DIR"

if [ ! -f "${STAND_DIR}/stand.db" ]; then
  echo "telegram_polling: ${STAND_DIR}/stand.db missing — bootstrap/migrate first" >&2
  exit 1
fi

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "telegram_polling: TELEGRAM_BOT_TOKEN unset — refusing (optional service)" >&2
  exit 2
fi

# Explicit compose/env gate: do not run polling when operator chose webhook mode.
MODE="$(printf '%s' "${TELEGRAM_INGRESS_MODE:-polling}" | tr '[:upper:]' '[:lower:]')"
case "$MODE" in
  webhook)
    echo "telegram_polling: TELEGRAM_INGRESS_MODE=webhook — refuse (polling XOR webhook)" >&2
    exit 3
    ;;
  polling|"")
    ;;
  *)
    echo "telegram_polling: unknown TELEGRAM_INGRESS_MODE=${TELEGRAM_INGRESS_MODE} (use polling|webhook)" >&2
    exit 3
    ;;
esac

if [ "${TELEGRAM_WEBHOOK_ACTIVE:-}" = "true" ] || [ "${TELEGRAM_WEBHOOK_ACTIVE:-}" = "1" ]; then
  echo "telegram_polling: TELEGRAM_WEBHOOK_ACTIVE set — refuse (polling XOR webhook)" >&2
  exit 3
fi

echo "telegram_polling: DATABASE_URL=${DATABASE_URL} state=${TELEGRAM_POLLING_STATE_DIR}"
exec python -m app.workers.telegram_polling
