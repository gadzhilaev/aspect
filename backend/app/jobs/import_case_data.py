"""CLI: python -m app.jobs.import_case_data --dry-run|--load ...

--dry-run validates competition CSV without writing to any application DB.
--load writes into an explicitly provided --database-url (never implicit).
Activation is a separate command: python -m app.jobs.activate_case_snapshot.
Resume is not implemented.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or import competition case CSV data"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory with competition CSV files (required for --dry-run and --load)",
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
        help="Write into an explicit --database-url after preflight (not compatible with --dry-run)",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("data/case/reports"),
        help="Where to write JSON/Markdown reports",
    )
    parser.add_argument(
        "--slot-key",
        type=str,
        default=None,
        help="Case slot key (required for --load)",
    )
    parser.add_argument(
        "--version-label",
        type=str,
        default=None,
        help="Human version label within the slot (required for --load)",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Target DB URL for --load only; never taken implicitly from working DATABASE_URL",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Loader batch size for --load (must be positive)",
    )
    args = parser.parse_args(argv)

    if args.dry_run and args.load:
        print("--dry-run and --load are mutually exclusive", file=sys.stderr)
        return 2
    if not args.dry_run and not args.load:
        print("Refusing to run: specify --dry-run or --load.", file=sys.stderr)
        return 2
    if args.input_dir is None:
        print("--input-dir is required", file=sys.stderr)
        return 2

    if args.dry_run:
        if not args.input_dir.is_dir():
            print(f"Input directory not found: {args.input_dir}", file=sys.stderr)
            return 2
        # Import after CLI gate so missing mode never touches DB modules.
        from app.services.case_data.dry_run import run_dry_run

        result = run_dry_run(input_dir=args.input_dir, report_dir=args.report_dir)
        print(
            f"dry-run ok={result.ok} can_proceed_to_load={result.can_proceed_to_load} "
            f"duration={result.duration_seconds:.2f}s "
            f"errors={sum(b.count for b in result.errors.values())} "
            f"warnings={sum(b.count for b in result.warnings.values())}"
        )
        print(f"reports: {args.report_dir / 'case_dry_run_latest.json'}")
        print(f"reports: {args.report_dir / 'case_dry_run_latest.md'}")
        return 0 if result.ok else 1

    # --load
    missing = []
    if not args.slot_key:
        missing.append("--slot-key")
    if not args.version_label:
        missing.append("--version-label")
    if not args.database_url:
        missing.append("--database-url")
    if missing:
        print(
            "Refusing --load without explicit "
            + ", ".join(missing)
            + ". Working DATABASE_URL is never used implicitly.",
            file=sys.stderr,
        )
        return 2

    if not args.input_dir.is_dir():
        print(f"Input directory not found: {args.input_dir}", file=sys.stderr)
        return 2

    from app.services.case_data.import_pipeline import (
        ImportPipelineError,
        PreflightFailedError,
        SchemaNotReadyError,
        VersionLabelConflictError,
        redact_database_url,
        run_case_import,
    )

    print(
        f"load target db={redact_database_url(args.database_url)} "
        f"slot={args.slot_key!r} version={args.version_label!r}",
        file=sys.stderr,
    )

    try:
        result = run_case_import(
            input_dir=args.input_dir,
            database_url=args.database_url,
            slot_key=args.slot_key,
            version_label=args.version_label,
            report_dir=args.report_dir,
            batch_size=args.batch_size,
        )
    except (PreflightFailedError, SchemaNotReadyError, VersionLabelConflictError) as exc:
        print(f"load refused: {exc}", file=sys.stderr)
        return 2
    except ImportPipelineError as exc:
        print(f"load error: {exc}", file=sys.stderr)
        return 1

    print(
        f"load status={result.status} snapshot_id={result.snapshot_id} "
        f"reason={result.reason}"
    )
    if result.status == "ready":
        return 0
    if result.status == "identical_skip":
        return 0
    if result.status == "preflight_failed":
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
