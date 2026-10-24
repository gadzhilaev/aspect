"""Stage 6.4 — storage survives full fixture bootstrap without repair scripts.

Proof relates to a *standard* bootstrap finish (not a manually repaired stand).
Uses tiny synthetic CSV/PDF/OCR/QA — not the 1.38M payment import.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from app.services.bank_materials.prepare import build_prepared_document, stage_corpus
from app.services.competition_stand.bootstrap import run_bootstrap
from app.services.competition_stand.preflight import POLICY_RATE_SLUG, _ocr_fingerprint
from tests.test_bank_import_dry_run import _build_valid_corpus
from tests.test_bank_qa_revisions import _qa_artifact

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = Path(__file__).resolve().parent / "fixtures" / "competition_stand" / "csv"
UIDS = ["U_900001", "U_900002"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_policy_rate_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """OCR+PDF+QA for Policy Rate slug, coherent fingerprints."""
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
    ocr_dir, pdf_dir = _build_valid_corpus(
        tmp_path / "corp",
        slug=POLICY_RATE_SLUG,
        pages=1,
        fragments=fragments,
    )
    # QA binding must match loader fingerprint; preflight must agree (same algo).
    staging = stage_corpus(
        input_dir=ocr_dir, pdf_dir=pdf_dir, staging_parent=tmp_path / "stage"
    )
    plan, errs, _ = build_prepared_document(
        staging.ocr_dir / POLICY_RATE_SLUG,
        input_dir=staging.ocr_dir,
        pdf_dir=staging.pdf_dir,
        storage_root=staging.storage_root,
    )
    assert plan is not None and not errs, errs
    pf_sha, pf_fp, _ = _ocr_fingerprint(ocr_dir / POLICY_RATE_SLUG)
    assert pf_sha == plan.source_sha256
    assert pf_fp == plan.fingerprint_hash
    qa_dir = tmp_path / "qa"
    qa_dir.mkdir()
    _qa_artifact(plan, out=qa_dir / "policy_rate_qa.json")
    return ocr_dir, pdf_dir, qa_dir


def _storage_file_inventory(storage_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not storage_root.is_dir():
        return out
    for p in sorted(storage_root.rglob("*")):
        if p.is_file():
            out[p.relative_to(storage_root).as_posix()] = _sha256(p)
    return out


def test_fixture_bootstrap_storage_survives_verify_relocate_noop(tmp_path: Path):
    ocr_dir, pdf_dir, qa_dir = _build_policy_rate_inputs(tmp_path)
    source_pdf = pdf_dir / f"{POLICY_RATE_SLUG}.pdf"
    assert source_pdf.is_file()
    expected_pdf_sha = _sha256(source_pdf)

    stand_dir = tmp_path / "stand_clean_64"
    result = run_bootstrap(
        csv_dir=CSV_DIR,
        pdf_dir=pdf_dir,
        ocr_dir=ocr_dir,
        qa_dir=qa_dir,
        output_dir=stand_dir,
        external_uids=UIDS,
    )
    assert result.ok is True, result.as_dict()
    assert result.noop is False
    assert result.status == "ready"
    assert (stand_dir / "stand.db").is_file()
    assert (stand_dir / "stand_manifest.json").is_file()
    assert (stand_dir / "demo_password.local").is_file()

    storage_root = stand_dir / "storage"
    inv_after_bootstrap = _storage_file_inventory(storage_root)
    assert inv_after_bootstrap, "storage empty after bootstrap (would require repair — fail)"
    pdf_keys = [k for k in inv_after_bootstrap if k.lower().endswith(".pdf")]
    assert pdf_keys, "no PDF under storage after bootstrap"
    assert any(inv_after_bootstrap[k] == expected_pdf_sha for k in pdf_keys)

    # OCR artifacts must exist under storage (png / meta / fragments paths vary by loader).
    assert any(k.endswith(".png") or "/pages/" in k for k in inv_after_bootstrap), (
        "expected OCR page artifacts in storage"
    )

    # New process: verify via API (login / PDF / SHA) — no repair script.
    verify = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_competition_stand.py"),
            "--stand-dir",
            str(stand_dir),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "COMPETITION_MODE": "true"},
        check=False,
    )
    assert verify.returncode == 0, f"stdout={verify.stdout}\nstderr={verify.stderr}"

    # Relocate stand and re-verify in yet another process.
    relocated = tmp_path / "stand_relocated_64"
    verify2 = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_competition_stand.py"),
            "--stand-dir",
            str(stand_dir),
            "--relocate-to",
            str(relocated),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "COMPETITION_MODE": "true"},
        check=False,
    )
    assert verify2.returncode == 0, f"stdout={verify2.stdout}\nstderr={verify2.stderr}"
    inv_relocated = _storage_file_inventory(relocated / "storage")
    assert inv_relocated == inv_after_bootstrap

    # Re-bootstrap same inputs → no-op; storage unchanged (no repair).
    result2 = run_bootstrap(
        csv_dir=CSV_DIR,
        pdf_dir=pdf_dir,
        ocr_dir=ocr_dir,
        qa_dir=qa_dir,
        output_dir=stand_dir,
        external_uids=UIDS,
    )
    assert result2.ok is True, result2.as_dict()
    assert result2.noop is True
    inv_after_noop = _storage_file_inventory(storage_root)
    assert inv_after_noop == inv_after_bootstrap


def test_bootstrap_does_not_invoke_repair_module():
    """Guard: storage proof must not rely on one-shot repair."""
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.append(node.module)
            imported.extend(a.name for a in node.names)
    blob = " ".join(imported)
    assert "repair" not in blob.lower()
