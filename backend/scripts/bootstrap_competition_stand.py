"""Bootstrap competition stand from explicit CSV/PDF/OCR/QA inputs (stage 6.3).

Does not copy verification/e2e databases. Does not call live LLM.
Does not modify root .env, kontur.db, or existing agent_demo stand.

Example:
  python scripts/bootstrap_competition_stand.py \\
    --csv-dir data/case/raw \\
    --pdf-dir data/bank_materials/raw \\
    --ocr-dir data/bank_materials/ocr \\
    --qa-dir data/bank_materials/verification/policy_rate_qa \\
    --output-dir data/competition_stand/jury_63 \\
    --external-uid U_264 \\
    --external-uid U_92
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a new competition stand DB from explicit file inputs"
    )
    parser.add_argument("--csv-dir", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--ocr-dir", type=Path, required=True)
    parser.add_argument("--qa-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Required unless --preflight-only",
    )
    parser.add_argument(
        "--external-uid",
        action="append",
        dest="external_uids",
        required=True,
        help="Competition U_* to profile (repeat once or twice)",
    )
    parser.add_argument("--slot-key", default="competition_default")
    parser.add_argument("--version-label", default="competition-stand-v1")
    parser.add_argument("--api-port", type=int, default=8018)
    parser.add_argument("--web-port", type=int, default=5178)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate inputs and exit without creating a DB",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from app.services.competition_stand.bootstrap import run_bootstrap
    from app.services.competition_stand.preflight import run_preflight

    if args.preflight_only:
        pf = run_preflight(
            csv_dir=args.csv_dir,
            pdf_dir=args.pdf_dir,
            ocr_dir=args.ocr_dir,
            qa_dir=args.qa_dir,
            external_uids=args.external_uids,
        )
        print(json.dumps(pf.as_dict(), ensure_ascii=False, indent=2))
        if not pf.ok:
            print("MISSING:", file=sys.stderr)
            for m in pf.missing:
                print(f"  [{m.kind}] {m.path}: {m.detail}", file=sys.stderr)
        return 0 if pf.ok else 1

    if args.output_dir is None:
        print("--output-dir is required unless --preflight-only", file=sys.stderr)
        return 2

    result = run_bootstrap(
        csv_dir=args.csv_dir,
        pdf_dir=args.pdf_dir,
        ocr_dir=args.ocr_dir,
        qa_dir=args.qa_dir,
        output_dir=args.output_dir,
        external_uids=args.external_uids,
        slot_key=args.slot_key,
        version_label=args.version_label,
        api_port=args.api_port,
        web_port=args.web_port,
    )
    # Never print demo password.
    safe = result.as_dict()
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    if result.ok:
        print(
            f"ok status={result.status} noop={result.noop} "
            f"output={result.output_dir} password_file=demo_password.local",
            file=sys.stderr,
        )
        return 0
    print(f"failed: {result.detail}", file=sys.stderr)
    for e in result.errors:
        print(f"  - {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
