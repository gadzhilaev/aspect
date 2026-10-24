"""Start isolated uvicorn for case-context integration (env only; no .env edits)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "data" / "case" / "verification" / "case_context_integration_latest.json"


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8014
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    copy_db = Path(art["copy_db"])
    if not copy_db.is_file():
        print(f"missing copy db: {copy_db}", file=sys.stderr)
        return 1
    # Relative URL from project root — avoids Windows/Cyrillic absolute-path issues.
    rel = copy_db.resolve().relative_to(ROOT.resolve()).as_posix()
    db_url = f"sqlite:///./{rel}"

    os.environ["DATABASE_URL"] = db_url
    os.environ["CASE_CONTEXT_SLOT_KEY"] = art.get("slot_key") or "competition_default"
    os.environ.setdefault("SECRET_KEY", "case-ctx-integration-isolated")
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("CORS_ORIGINS", "*")
    os.environ.setdefault("ASSISTANT_PROVIDER", "mock")
    # Do not inherit production assistant keys for this smoke process.
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["GIGACHAT_AUTH_KEY"] = ""

    os.chdir(ROOT)
    print(f"case-ctx-api port={port} db=./{rel}", flush=True)

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
