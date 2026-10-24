"""CLI: python -m app.jobs.ingest_news

Intended for cron / Task Scheduler every ~15 minutes.
Does not start background tasks inside FastAPI.

Reprocess previously rejected raw after policy change:
  python -m app.jobs.ingest_news --heuristic-enrich --reprocess-rejected \\
    --reprocess-hosts wto.org,customs.gov.ru,ec.europa.eu [--reprocess-apply]
"""

from __future__ import annotations

import argparse
import json
import sys

from app.db.session import SessionLocal
from app.services.ingestion import run_ingestion
from app.services.ingestion.reprocess import reprocess_rejected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest news signals into Kontur")
    parser.add_argument("--no-fetch", action="store_true", help="Only process pending raw items")
    parser.add_argument("--no-process", action="store_true", help="Only fetch and store raw items")
    parser.add_argument(
        "--heuristic-enrich",
        action="store_true",
        help="Skip live LLM enrichment (deterministic heuristic; safe with COMPETITION_MODE)",
    )
    parser.add_argument(
        "--reprocess-rejected",
        action="store_true",
        help="Re-queue rejected raw (dry-run unless --reprocess-apply)",
    )
    parser.add_argument(
        "--reprocess-apply",
        action="store_true",
        help="Apply reprocess (default is dry-run)",
    )
    parser.add_argument(
        "--reprocess-hosts",
        default="",
        help="Comma-separated article hosts to reprocess (e.g. wto.org,customs.gov.ru)",
    )
    parser.add_argument(
        "--reprocess-limit",
        type=int,
        default=200,
        help="Max rejected rows to consider",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        if args.reprocess_rejected:
            hosts = [h.strip() for h in args.reprocess_hosts.split(",") if h.strip()]
            plan, result = reprocess_rejected(
                db,
                dry_run=not args.reprocess_apply,
                prefer_live_enrich=not args.heuristic_enrich,
                article_hosts=hosts or None,
                feed_hosts=hosts or None,
                errors=["unverified_single_source"],
                only_would_be_official=True,
                limit=args.reprocess_limit,
            )
            out = {
                "mode": "reprocess_rejected",
                "dry_run": plan.dry_run,
                "candidate_ids": plan.candidate_ids,
                "would_be_official": plan.would_be_official,
                "skipped": plan.skipped,
            }
            if result is not None:
                out["process"] = {
                    "clusters": result.clusters,
                    "published": result.published,
                    "rejected": result.rejected,
                    "event_ids": result.event_ids,
                    "errors": result.errors,
                }
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0

        result = run_ingestion(
            db,
            fetch=not args.no_fetch,
            process=not args.no_process,
            prefer_live_enrich=not args.heuristic_enrich,
        )
    finally:
        db.close()

    print(
        json.dumps(
            {
                "fetched": result.fetched,
                "inserted": result.inserted,
                "duplicates": result.duplicates,
                "clusters": result.clusters,
                "published": result.published,
                "rejected": result.rejected,
                "event_ids": result.event_ids,
                "errors": result.errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not result.errors else 0  # soft-fail providers are listed, exit 0


if __name__ == "__main__":
    sys.exit(main())
