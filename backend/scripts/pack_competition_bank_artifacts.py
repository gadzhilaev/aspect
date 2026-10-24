"""Pack OCR + matching PDFs + QA revisions into a portable local directory.

Does not include DBs, keys, accounts, or logs.
Does not publish or redistribute competition materials.
Does not change verification statuses, quotes, or dates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pack bank OCR/PDF/QA artifacts")
    parser.add_argument("--ocr-dir", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--qa-dir", type=Path, required=True)
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument(
        "--slug",
        action="append",
        dest="slugs",
        default=None,
        help="Optional OCR slug filter (repeatable). Default: all OCR docs.",
    )
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from app.services.competition_stand.pack import pack_bank_artifacts

    result = pack_bank_artifacts(
        ocr_dir=args.ocr_dir,
        pdf_dir=args.pdf_dir,
        qa_dir=args.qa_dir,
        pack_dir=args.pack_dir,
        slugs=args.slugs,
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
