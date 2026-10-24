"""CLI: python -m app.jobs.activate_case_snapshot --database-url ... --activate

Activates a ready case snapshot. Does not import CSV data.
Never uses the working DATABASE_URL implicitly.
"""

from __future__ import annotations

import argparse
import sys

from app.services.case_data.import_pipeline import redact_database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Atomically activate a ready case snapshot for a slot"
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="Target DB URL (required; working DATABASE_URL is never used)",
    )
    parser.add_argument("--slot-key", required=True, help="Case slot key")
    parser.add_argument(
        "--snapshot-id",
        required=True,
        help="Ready snapshot UUID to activate",
    )
    expect = parser.add_mutually_exclusive_group(required=True)
    expect.add_argument(
        "--expected-active-id",
        dest="expected_active_id",
        default=None,
        help="Current active snapshot id that must still hold (optimistic concurrency)",
    )
    expect.add_argument(
        "--expect-no-active",
        action="store_true",
        help="Require that the slot currently has no active snapshot",
    )
    args = parser.parse_args(argv)

    print(
        f"activate target db={redact_database_url(args.database_url)} "
        f"slot={args.slot_key!r} snapshot={args.snapshot_id}",
        file=sys.stderr,
    )

    from app.services.case_data.activate_snapshot import (
        ActivationConflictError,
        ActivationError,
        ActivationIntegrityError,
        ActivationPreconditionError,
        run_activation,
    )

    try:
        result = run_activation(
            database_url=args.database_url,
            slot_key=args.slot_key,
            snapshot_id=args.snapshot_id,
            expected_active_snapshot_id=args.expected_active_id,
            expect_no_active=args.expect_no_active,
        )
    except (ActivationPreconditionError, ActivationConflictError, ActivationIntegrityError) as exc:
        print(f"activate refused: {exc}", file=sys.stderr)
        return 2
    except ActivationError as exc:
        print(f"activate error: {exc}", file=sys.stderr)
        return 1

    print(
        f"outcome={result.outcome} slot={result.slot_key} "
        f"previous={result.previous_snapshot_id} current={result.current_snapshot_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
