"""Materialize tiny synthetic CSV/PDF/OCR/QA inputs for competition Docker smoke.

Writes under data/competition_docker_smoke/inputs/ (gitignored).
Does not touch jury_63b, root .env, or live servers.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "competition_docker_smoke" / "inputs"
CSV_FIX = ROOT / "tests" / "fixtures" / "competition_stand" / "csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from app.services.competition_stand.preflight import POLICY_RATE_SLUG, _ocr_fingerprint
    from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
    from tests.test_bank_import_dry_run import _build_valid_corpus
    from tests.test_bank_qa_revisions import _qa_artifact

    out = args.out_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    csv_dir = out / "csv"
    pdf_dir = out / "pdf"
    ocr_dir = out / "ocr"
    qa_dir = out / "qa"
    csv_dir.mkdir(parents=True)
    for name in ("companies.csv", "payments.csv", "person_links.csv"):
        shutil.copy2(CSV_FIX / name, csv_dir / name)

    fragments = [
        {
            "id": "policy_rate_cb_decision",
            "kind": "exact_quote",
            "content_type": "fact",
            "page": 1,
            "regions": [{"bbox": {"left": 10, "top": 10, "width": 50, "height": 20}}],
            "ocr_text": "decision ocr",
            "exact_quote": "decision ocr",
            "verification_status": "verified",
        },
        {
            "id": "policy_rate_rhetoric",
            "kind": "exact_quote",
            "content_type": "interpretation",
            "page": 1,
            "regions": [{"bbox": {"left": 10, "top": 40, "width": 50, "height": 20}}],
            "ocr_text": "rhetoric cTana",
            "exact_quote": "rhetoric became tougher",
            "verification_status": "verified",
        },
        {
            "id": "policy_rate_bank_forecast",
            "kind": "exact_quote",
            "content_type": "forecast",
            "page": 1,
            "regions": [{"bbox": {"left": 10, "top": 70, "width": 50, "height": 20}}],
            "ocr_text": "forecast ellipsis…",
            "exact_quote": "forecast ellipsis…",
            "verification_status": "verified",
        },
    ]
    stage_root = out / "_build"
    ocr_src, pdf_src = _build_valid_corpus(
        stage_root / "corp",
        slug=POLICY_RATE_SLUG,
        pages=1,
        fragments=fragments,
    )
    # Flatten into expected mount layout: ocr/<slug>/..., pdf/*.pdf
    shutil.copytree(ocr_src / POLICY_RATE_SLUG, ocr_dir / POLICY_RATE_SLUG)
    pdf_dir.mkdir(parents=True)
    shutil.copy2(pdf_src / f"{POLICY_RATE_SLUG}.pdf", pdf_dir / f"{POLICY_RATE_SLUG}.pdf")

    staging = stage_corpus(
        input_dir=ocr_dir, pdf_dir=pdf_dir, staging_parent=stage_root / "stage"
    )
    plan, errs, _ = build_prepared_document(
        staging.ocr_dir / POLICY_RATE_SLUG,
        input_dir=staging.ocr_dir,
        pdf_dir=staging.pdf_dir,
        storage_root=staging.storage_root,
    )
    if plan is None or errs:
        print(f"prepare failed: {errs}", file=sys.stderr)
        return 1
    pf_sha, pf_fp, _ = _ocr_fingerprint(ocr_dir / POLICY_RATE_SLUG)
    assert pf_sha == plan.source_sha256 and pf_fp == plan.fingerprint_hash

    qa_dir.mkdir(parents=True)
    _qa_artifact(plan, out=qa_dir / "policy_rate_qa.json")

    # Drop build scratch (not part of inputs mount).
    shutil.rmtree(stage_root, ignore_errors=True)

    print(f"ok inputs={out}")
    print("uids=U_900001 U_900002")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
