#!/bin/sh
# Competition API entrypoint: load prepared stand env, never run import/bootstrap.
set -eu

STAND_DIR="${COMPETITION_STAND_DIR:-/stand}"
STATUS_FILE="${STAND_DIR}/stand_status.json"
ENV_FILE="${STAND_DIR}/stand.env"

if [ ! -f "$STATUS_FILE" ]; then
  echo "competition api: missing ${STATUS_FILE}" >&2
  echo "Run the bootstrap one-shot service before starting api/web." >&2
  exit 1
fi

python - <<'PY' "$STATUS_FILE"
import json, sys
from pathlib import Path
status = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if status.get("status") != "ready" or not status.get("ready_for_launch"):
    raise SystemExit(f"stand not ready: {status}")
print("competition api: stand_status=ready")
PY

if [ ! -f "$ENV_FILE" ]; then
  echo "competition api: missing ${ENV_FILE}" >&2
  exit 1
fi

# Apply stand.env keys except secrets we inject at runtime and host-relative paths.
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    ''|\#*) continue ;;
  esac
  key=${line%%=*}
  val=${line#*=}
  case "$key" in
    DATABASE_URL|BANK_MATERIALS_STORAGE_ROOT|HACKATHON_API_KEY|OPENAI_API_KEY|GIGACHAT_AUTH_KEY|DADATA_API_KEY)
      # Secrets are injected at runtime (compose env), never read from stand.env.
      # NOTE: COMPANY_REGISTRY_* knobs are NOT skipped — they flow from stand.env.
      continue
      ;;
  esac
  export "$key=$val"
done < "$ENV_FILE"

# Fixed container paths shared with bootstrap volume.
export DATABASE_URL="sqlite:////stand/stand.db"
export BANK_MATERIALS_STORAGE_ROOT="/stand/storage"
export COMPETITION_MODE="${COMPETITION_MODE:-true}"
export ASSISTANT_PROVIDER="${ASSISTANT_PROVIDER:-hackathon}"
export ASSISTANT_AGENT_LOOP="${ASSISTANT_AGENT_LOOP:-true}"
# Settings.app_env is Literal[development|test|production] — not "competition".
# Competition profile is COMPETITION_MODE=true (separate).
export APP_ENV="${APP_ENV:-production}"
export SECRET_KEY="${SECRET_KEY:-competition-docker-local-secret}"

# Runtime-only key (compose env_file / shell). Never bake into image.
if [ -n "${HACKATHON_API_KEY:-}" ]; then
  export HACKATHON_API_KEY
else
  unset HACKATHON_API_KEY || true
fi
unset OPENAI_API_KEY || true
unset GIGACHAT_AUTH_KEY || true

# Company registry key is optional and runtime-only. Absent key → the lookup
# endpoint reports not_configured and the UI keeps manual entry (no fake answer).
if [ -n "${DADATA_API_KEY:-}" ]; then
  export DADATA_API_KEY
else
  unset DADATA_API_KEY || true
fi

if [ ! -f /stand/stand.db ]; then
  echo "competition api: /stand/stand.db missing — bootstrap first" >&2
  exit 1
fi

echo "competition api: starting uvicorn (no import on restart)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
