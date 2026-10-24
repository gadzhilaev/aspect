"""CLI: python -m app.jobs.import_bank_materials (--dry-run | --load) ...

Dry-run validates OCR corpus + PDFs without connecting to an application DB.
Load writes to an explicitly provided --database-url only (never DATABASE_URL).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or import bank materials OCR corpus"
    )
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only; do not connect to or write an application database",
    )
    mode.add_argument(
        "--load",
        action="store_true",
        help="Load into a database after preflight (requires --database-url)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/bank_materials/ocr"),
        help="Directory with per-document OCR outputs (manifest.json, pages, fragments)",
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path("data/bank_materials/raw"),
        help="Directory with original PDFs",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("data/bank_materials/reports"),
        help="Where to write JSON/Markdown reports (gitignored)",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Explicit SQLAlchemy URL for --load (required; env DATABASE_URL is ignored)",
    )
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=None,
        help="Root for opaque storage keys (defaults to staging root for --load)",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not args.load:
        print(
            "Refusing to run: pass --dry-run or --load. "
            "No database writes performed.",
            file=sys.stderr,
        )
        return 2

    if args.dry_run:
        from app.services.bank_materials.dry_run import (
            run_bank_materials_dry_run,
            write_reports,
        )

        result = run_bank_materials_dry_run(input_dir=args.input_dir, pdf_dir=args.pdf_dir)
        json_path, md_path = write_reports(result, args.report_dir)

        print(f"ok={result.ok}")
        print(
            f"documents={result.totals.get('documents')} pages={result.totals.get('pages')} "
            f"fragments={result.totals.get('fragments')}"
        )
        print(
            f"eligible_search={result.totals.get('eligible_search')} "
            f"ai_evidence={result.totals.get('eligible_ai_evidence')} "
            f"exact_quote={result.totals.get('eligible_exact_quote')}"
        )
        print(
            f"blocking_errors={result.blocking_error_count} warnings={result.warning_count}"
        )
        print(f"report_json={json_path}")
        print(f"report_md={md_path}")

        if result.errors:
            print("\nBlocking errors:", file=sys.stderr)
            for e in result.errors[:50]:
                print(
                    f"  [{e.code}] doc={e.document} page={e.page} key={e.stable_key} "
                    f"field={e.field}: {e.detail}",
                    file=sys.stderr,
                )
            if len(result.errors) > 50:
                print(f"  … and {len(result.errors) - 50} more", file=sys.stderr)

        return 0 if result.ok else 1

    # --load
    if not args.database_url or not str(args.database_url).strip():
        print(
            "Refusing --load: explicit --database-url is required. "
            "DATABASE_URL from the environment is not used.",
            file=sys.stderr,
        )
        return 2

    from app.services.bank_materials.load import BankLoadError, run_bank_materials_load

    try:
        result = run_bank_materials_load(
            input_dir=args.input_dir,
            pdf_dir=args.pdf_dir,
            database_url=args.database_url,
            storage_root=args.storage_root,
            report_dir=args.report_dir,
        )
    except BankLoadError as exc:
        print(f"load_error: [{exc.code}] {exc.detail}", file=sys.stderr)
        return 2

    print(f"status={result.status} ok={result.ok} partial_success={result.partial_success}")
    print(f"database={result.database}")
    print(
        f"inserted={result.inserted} identical_skip={result.identical_skip} "
        f"failed={result.failed}"
    )
    print(
        f"eligibility_search={result.eligibility_totals.get('search')} "
        f"ai_evidence={result.eligibility_totals.get('ai_evidence')} "
        f"exact_quote={result.eligibility_totals.get('exact_quote')}"
    )
    if result.detail:
        print(f"detail={result.detail}")
    for key, path in (result.report_paths or {}).items():
        print(f"{key}={path}")
    for doc in result.documents:
        print(
            f"  doc={doc.slug} status={doc.status} code={doc.code} "
            f"elig={doc.eligibility_after_read}"
        )

    if result.status == "schema_not_ready":
        return 2
    if result.status == "preflight_failed":
        return 1
    if result.partial_success:
        return 0  # partial success is an explicit outcome; still exit 0 with flag
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
