"""CLI: apply versioned bank fragment QA revisions to an existing OCR run.

  python -m app.jobs.apply_bank_qa_revisions --dry-run --qa-artifact PATH --database-url URL
  python -m app.jobs.apply_bank_qa_revisions --apply --qa-artifact PATH --database-url URL

Never uses DATABASE_URL from the environment. Does not run migrations.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply bank fragment QA revisions to an existing OCR run"
    )
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate QA artifact against DB without writing",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply all revisions in one transaction (requires --database-url)",
    )
    parser.add_argument(
        "--qa-artifact",
        type=Path,
        required=True,
        help="Path to fragment_revisions QA JSON artifact",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Explicit SQLAlchemy URL (required; env DATABASE_URL is ignored)",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("data/bank_materials/verification/qa_apply_reports"),
        help="Where to write JSON apply reports",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not args.apply:
        print(
            "Refusing to run: pass --dry-run or --apply. No database writes performed.",
            file=sys.stderr,
        )
        return 2

    if not args.database_url or not str(args.database_url).strip():
        print(
            "Refusing: explicit --database-url is required. "
            "DATABASE_URL from the environment is not used.",
            file=sys.stderr,
        )
        return 2

    from app.services.bank_materials.apply_qa_revisions import (
        QaRevisionError,
        run_apply_qa_revisions,
    )

    try:
        result = run_apply_qa_revisions(
            artifact_path=args.qa_artifact,
            database_url=args.database_url,
            dry_run=bool(args.dry_run),
            report_dir=args.report_dir,
        )
    except QaRevisionError as exc:
        print(f"qa_error: [{exc.code}] {exc.detail}", file=sys.stderr)
        return 1

    print(f"status={result.status}")
    print(f"artifact_id={result.artifact_id}")
    print(f"artifact_sha256={result.artifact_sha256}")
    print(f"document_slug={result.document_slug}")
    print(f"ocr_run_id={result.ocr_run_id}")
    print(
        f"inserted_fragments={result.inserted_fragments} "
        f"inserted_regions={result.inserted_regions} "
        f"identical_skip={result.identical_skip}"
    )
    print(f"eligibility_latest={result.eligibility_latest}")
    print(f"counts_after={result.counts_after}")
    if result.detail:
        print(f"detail={result.detail}")
    for rev in result.revisions:
        print(
            f"  {rev['stable_key']}@r{rev['revision']} "
            f"type={rev['content_type']} elig={rev['eligibility']}"
        )

    if result.status in ("applied", "identical_skip", "dry_run_ok"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
