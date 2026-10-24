"""Stage 6.3 — competition stand bootstrap (fixtures + mocked heavy import)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.services.competition_stand.bootstrap import run_bootstrap
from app.services.competition_stand.pack import pack_bank_artifacts
from app.services.competition_stand.preflight import run_preflight

FIX = Path(__file__).resolve().parent / "fixtures" / "competition_stand"
CSV_DIR = FIX / "csv"
ROOT = Path(__file__).resolve().parents[1]


def test_preflight_lists_missing_inputs(tmp_path: Path):
    pf = run_preflight(
        csv_dir=tmp_path / "no_csv",
        pdf_dir=tmp_path / "no_pdf",
        ocr_dir=tmp_path / "no_ocr",
        qa_dir=tmp_path / "no_qa",
        external_uids=["U_1"],
    )
    assert pf.ok is False
    kinds = {m.kind for m in pf.missing}
    assert "csv_dir" in kinds
    assert "pdf_dir" in kinds
    assert "ocr_dir" in kinds
    assert "qa_dir" in kinds


def test_preflight_fixture_csv_uids():
    # Incomplete bank dirs on purpose — expect OCR/PDF/QA missing, but UID found in CSV.
    empty = Path(__file__).resolve().parent / "fixtures" / "competition_stand" / "_empty"
    empty.mkdir(exist_ok=True)
    pf = run_preflight(
        csv_dir=CSV_DIR,
        pdf_dir=empty,
        ocr_dir=empty,
        qa_dir=empty,
        external_uids=["U_900001", "U_900002"],
        require_policy_rate=True,
    )
    assert pf.uids_found_in_catalog.get("U_900001") is True
    assert pf.uids_found_in_catalog.get("U_900002") is True
    assert pf.ok is False
    assert any(m.kind == "ocr_policy_rate" for m in pf.missing)


def test_preflight_unknown_uid():
    empty = FIX / "_empty"
    empty.mkdir(exist_ok=True)
    pf = run_preflight(
        csv_dir=CSV_DIR,
        pdf_dir=empty,
        ocr_dir=empty,
        qa_dir=empty,
        external_uids=["U_999999999"],
        require_policy_rate=False,
    )
    assert pf.uids_found_in_catalog.get("U_999999999") is False
    assert any(m.kind == "uid" for m in pf.missing)


def test_pack_refuses_nonempty_and_copies_relative(tmp_path: Path):
    # Use real Policy Rate OCR if present; otherwise skip.
    ocr = ROOT / "data/bank_materials/ocr"
    pdf = ROOT / "data/bank_materials/raw"
    qa = ROOT / "data/bank_materials/verification/policy_rate_qa"
    if not (ocr / "ALFA-Macro_Insights-Policy_Rate_11Sep" / "manifest.json").is_file():
        pytest.skip("local OCR corpus not available")
    if not (pdf / "ALFA-Macro_Insights-Policy_Rate_11Sep.pdf").is_file():
        pytest.skip("local PDF not available")

    pack_dir = tmp_path / "pack"
    result = pack_bank_artifacts(
        ocr_dir=ocr,
        pdf_dir=pdf,
        qa_dir=qa,
        pack_dir=pack_dir,
        slugs=["ALFA-Macro_Insights-Policy_Rate_11Sep"],
    )
    assert result.ok, result.errors
    man = json.loads((pack_dir / "pack_manifest.json").read_text(encoding="utf-8"))
    assert man["documents"][0]["ocr_rel"].startswith("ocr/")
    assert man["documents"][0]["pdf_rel"].startswith("pdf/")
    assert not any(
        "C:\\" in json.dumps(man) or "/Users/" in json.dumps(man) for _ in [0]
    )
    # absolute host paths must not be required — relative tree exists
    assert (pack_dir / man["documents"][0]["ocr_rel"] / "manifest.json").is_file()

    occupied = pack_bank_artifacts(
        ocr_dir=ocr,
        pdf_dir=pdf,
        qa_dir=qa,
        pack_dir=pack_dir,
        slugs=["ALFA-Macro_Insights-Policy_Rate_11Sep"],
    )
    assert occupied.ok is False
    assert "not empty" in occupied.errors[0]


def test_bootstrap_refuses_occupied_unknown_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "out"
    out.mkdir()
    (out / "noise.txt").write_text("x", encoding="utf-8")

    # Preflight will fail first if dirs empty — create minimal dirs so we hit occupy check
    # after a successful fingerprint match attempt. Use monkeypatch of run_preflight.
    from app.services.competition_stand import bootstrap as boot_mod
    from app.services.competition_stand.preflight import PreflightResult

    def fake_preflight(**kwargs):  # noqa: ANN003
        return PreflightResult(
            ok=True,
            external_uids=["U_900001"],
            inputs_fingerprint={"csv": {"companies": "abc"}, "external_uids": ["U_900001"]},
        )

    monkeypatch.setattr(boot_mod, "run_preflight", fake_preflight)
    result = run_bootstrap(
        csv_dir=CSV_DIR,
        pdf_dir=tmp_path,
        ocr_dir=tmp_path,
        qa_dir=tmp_path,
        output_dir=out,
        external_uids=["U_900001"],
    )
    assert result.ok is False
    assert "output_dir_occupied" in result.errors


def test_bootstrap_noop_on_matching_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.services.competition_stand import bootstrap as boot_mod
    from app.services.competition_stand.preflight import PreflightResult

    fp = {"csv": {"companies": "abc"}, "external_uids": ["U_900001"]}
    out = tmp_path / "stand"
    out.mkdir()
    (out / "stand.db").write_bytes(b"sqlite")
    (out / "stand_status.json").write_text(
        json.dumps({"status": "ready"}), encoding="utf-8"
    )
    (out / "stand_manifest.json").write_text(
        json.dumps({"inputs_fingerprint": fp, "status": "ready"}), encoding="utf-8"
    )

    def fake_preflight(**kwargs):  # noqa: ANN003
        return PreflightResult(ok=True, external_uids=["U_900001"], inputs_fingerprint=fp)

    monkeypatch.setattr(boot_mod, "run_preflight", fake_preflight)
    result = run_bootstrap(
        csv_dir=CSV_DIR,
        pdf_dir=tmp_path,
        ocr_dir=tmp_path,
        qa_dir=tmp_path,
        output_dir=out,
        external_uids=["U_900001"],
    )
    assert result.ok and result.noop


def test_case_fixture_dry_run_ok():
    from app.services.case_data.dry_run import run_dry_run

    report = FIX / "_reports"
    report.mkdir(exist_ok=True)
    r = run_dry_run(input_dir=CSV_DIR, report_dir=report)
    assert r.ok, {k: v.count for k, v in r.errors.items()}
    assert r.can_proceed_to_load
