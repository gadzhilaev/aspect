"""Case CSV dry-run: validators + fixtures; must not touch application DB."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.jobs import import_case_data as import_job
from app.services.case_data.csv_io import iter_csv_rows
from app.services.case_data.dry_run import run_dry_run
from app.services.case_data.validate import (
    ParseStatus,
    parse_bool_flag,
    parse_external_fid,
    parse_external_uid,
    parse_money_numeric_20_1,
    parse_pay_cnt,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "case_dry_run"
ROOT = Path(__file__).resolve().parents[1]


def test_parse_ids_and_flags():
    assert parse_external_uid("U_12").ok
    assert parse_external_uid("").status is ParseStatus.MISSING
    assert parse_external_uid("X_1").status is ParseStatus.INVALID
    assert parse_external_fid("F_9").ok
    assert parse_bool_flag("1.0").value is True
    assert parse_bool_flag("0").value is False
    assert parse_bool_flag("yes").status is ParseStatus.INVALID
    assert parse_bool_flag("").status is ParseStatus.MISSING


def test_parse_money_exact_numeric_20_1():
    ok = parse_money_numeric_20_1("1000.0")
    assert ok.ok and ok.value == Decimal("1000.0")
    assert parse_money_numeric_20_1("1.23").error == "too_many_fraction_digits"
    assert parse_money_numeric_20_1("12345678901234567890.0").error == "overflow"
    assert parse_money_numeric_20_1("nan").error == "nan_or_infinity"
    assert parse_money_numeric_20_1("").status is ParseStatus.MISSING
    # float path rejected
    assert parse_money_numeric_20_1(1.5).status is ParseStatus.INVALID
    assert parse_pay_cnt("3").value == 3
    assert parse_pay_cnt("0").status is ParseStatus.INVALID
    assert parse_pay_cnt("1.5").status is ParseStatus.INVALID


def test_quoted_newline_is_one_record():
    path = FIX / "quoted_newline" / "df_Uid_data_hack.csv"
    rows = list(iter_csv_rows(path))
    assert len(rows) == 1
    assert rows[0].record_number == 1
    assert "line2" in rows[0].values["ECO_MARK_LABEL"]


def test_dry_run_valid_ok(tmp_path: Path):
    result = run_dry_run(input_dir=FIX / "valid", report_dir=tmp_path / "reports")
    assert result.ok
    assert result.can_proceed_to_load
    assert (tmp_path / "reports" / "case_dry_run_latest.json").is_file()
    assert result.stats["companies"]["records"] == 2


def test_dry_run_bad_flags(tmp_path: Path):
    result = run_dry_run(input_dir=FIX / "bad_flags", report_dir=tmp_path / "reports")
    assert not result.ok
    assert result.errors["invalid_bool_flag"].count >= 2


def test_dry_run_money(tmp_path: Path):
    result = run_dry_run(input_dir=FIX / "money", report_dir=tmp_path / "reports")
    assert not result.ok
    assert result.errors["invalid_revenue"].count >= 3
    assert result.errors["invalid_pay_amt"].count >= 2
    assert result.errors["invalid_pay_cnt"].count >= 1


def test_dry_run_conflict_uid(tmp_path: Path):
    result = run_dry_run(input_dir=FIX / "conflict_uid", report_dir=tmp_path / "reports")
    assert result.ok  # conflicts are warnings
    assert result.warnings["duplicate_company_uid"].count >= 1
    assert result.warnings["conflicting_company_uid"].count >= 1
    assert result.stats["companies"]["uids_with_field_conflicts"] == 1


def test_dry_run_orphans_are_warnings(tmp_path: Path):
    result = run_dry_run(input_dir=FIX / "orphans", report_dir=tmp_path / "reports")
    assert result.ok
    assert result.warnings["payment_party_not_in_catalog"].count >= 2
    assert result.warnings["person_link_org_not_in_catalog"].count >= 1
    assert result.stats["payments"]["one_end_in_catalog"] == 2


def test_dry_run_dup_payments(tmp_path: Path):
    result = run_dry_run(input_dir=FIX / "dup_payments", report_dir=tmp_path / "reports")
    assert result.ok
    assert result.warnings["identical_payment_rows"].count == 1
    assert result.stats["payments"]["pairs_with_multiple_value_variants"] == 1
    assert result.stats["payments"]["identical_content_extra_rows"] == 1


def test_cli_requires_mode():
    assert import_job.main([]) == 2
    assert import_job.main(["--input-dir", str(FIX / "valid")]) == 2


def test_dry_run_does_not_use_application_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./should_never_open_case_dry_run.db")
    import app.db.session as session_mod

    def _boom(*_a, **_k):
        raise AssertionError("application DB must not be used during dry-run")

    monkeypatch.setattr(session_mod, "SessionLocal", _boom)

    code = import_job.main(
        [
            "--dry-run",
            "--input-dir",
            str(FIX / "valid"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert code == 0
    assert not (ROOT / "should_never_open_case_dry_run.db").exists()


def test_quoted_newline_fixture_dry_run(tmp_path: Path):
    result = run_dry_run(input_dir=FIX / "quoted_newline", report_dir=tmp_path / "reports")
    assert result.ok
    assert result.stats["companies"]["records"] == 1
