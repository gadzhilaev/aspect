#!/bin/sh
# One-shot competition bootstrap inside the API image.
# Inputs: /inputs/{csv,pdf,ocr,qa} (read-only). Output: /stand (persistent volume).
set -eu

CSV_DIR="${COMPETITION_CSV_DIR:-/inputs/csv}"
PDF_DIR="${COMPETITION_PDF_DIR:-/inputs/pdf}"
OCR_DIR="${COMPETITION_OCR_DIR:-/inputs/ocr}"
QA_DIR="${COMPETITION_QA_DIR:-/inputs/qa}"
OUT_DIR="${COMPETITION_STAND_DIR:-/stand}"
UIDS="${COMPETITION_EXTERNAL_UIDS:-}"

if [ -z "$UIDS" ]; then
  echo "COMPETITION_EXTERNAL_UIDS is required (space-separated U_* list)" >&2
  exit 2
fi

uid_args=""
for u in $UIDS; do
  uid_args="$uid_args --external-uid $u"
done

mode="${COMPETITION_BOOTSTRAP_MODE:-bootstrap}"

if [ "$mode" = "preflight" ]; then
  # shellcheck disable=SC2086
  exec python scripts/bootstrap_competition_stand.py --preflight-only \
    --csv-dir "$CSV_DIR" \
    --pdf-dir "$PDF_DIR" \
    --ocr-dir "$OCR_DIR" \
    --qa-dir "$QA_DIR" \
    $uid_args
fi

# shellcheck disable=SC2086
python scripts/bootstrap_competition_stand.py \
  --csv-dir "$CSV_DIR" \
  --pdf-dir "$PDF_DIR" \
  --ocr-dir "$OCR_DIR" \
  --qa-dir "$QA_DIR" \
  --output-dir "$OUT_DIR" \
  --api-port 8000 \
  --web-port 80 \
  $uid_args

# Rewrite stand.env paths for the container volume layout (absolute).
python - <<'PY'
from pathlib import Path

stand = Path("/stand")
env_path = stand / "stand.env"
if not env_path.is_file():
    raise SystemExit("bootstrap finished but /stand/stand.env missing")

lines = []
for line in env_path.read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        lines.append("DATABASE_URL=sqlite:////stand/stand.db")
    elif line.startswith("BANK_MATERIALS_STORAGE_ROOT="):
        lines.append("BANK_MATERIALS_STORAGE_ROOT=/stand/storage")
    elif line.startswith("HACKATHON_API_KEY="):
        continue  # never persist key in stand.env inside the volume writeback
    else:
        lines.append(line)
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("rewrote stand.env for container paths")
PY
