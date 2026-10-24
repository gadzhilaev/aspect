"""CLI: python -m app.jobs.link_case_org_company --database-url ...

Operator binding of competition U_* to an existing Company.
Does not create Company/membership and does not activate snapshots.
Never uses the working DATABASE_URL implicitly.
"""

from __future__ import annotations

import argparse
import sys

from app.services.case_data.import_pipeline import redact_database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Link a competition org (U_*) to an existing Company in a slot"
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="Target DB URL (required; working DATABASE_URL is never used)",
    )
    parser.add_argument("--slot-key", required=True, help="Case slot key")
    parser.add_argument("--external-uid", required=True, help="Competition U_* id")
    parser.add_argument("--company-id", required=True, help="Existing Company UUID")
    parser.add_argument(
        "--linked-by",
        default=None,
        help="Operator identifier stored on the link (optional)",
    )
    args = parser.parse_args(argv)

    print(
        f"link target db={redact_database_url(args.database_url)} "
        f"slot={args.slot_key!r} uid={args.external_uid!r} company={args.company_id}",
        file=sys.stderr,
    )

    from app.services.case_data.link_org_company import (
        LinkConflictError,
        LinkError,
        LinkPreconditionError,
        run_link,
    )

    try:
        result = run_link(
            database_url=args.database_url,
            slot_key=args.slot_key,
            external_uid=args.external_uid,
            company_id=args.company_id,
            linked_by=args.linked_by,
        )
    except (LinkPreconditionError, LinkConflictError) as exc:
        print(f"link refused: {exc}", file=sys.stderr)
        return 2
    except LinkError as exc:
        print(f"link error: {exc}", file=sys.stderr)
        return 1

    print(
        f"outcome={result.outcome} slot={result.slot_key} "
        f"uid={result.external_uid} company={result.company_id} "
        f"link_id={result.link_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
