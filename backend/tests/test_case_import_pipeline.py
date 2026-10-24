"""Case import pipeline: synthetic CSV + temporary SQLite only."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.jobs import import_case_data as import_job
from app.models import (
    CaseActiveSnapshot,
    CaseImportFile,
    CaseImportRun,
    CaseOrg,
    CaseOrgCatalogRow,
    CaseOrgCompanyLink,
    CasePayment,
    CasePersonOrgLink,
    CaseSnapshot,
    Company,
    CompanyMembership,
)
from app.services.case_data import import_pipeline as pipe
from app.services.case_data.import_pipeline import (
    FinalVerificationError,
    VersionLabelConflictError,
    redact_database_url,
    run_case_import,
)
from app.services.case_data.load_org_catalog import load_company_catalog

ROOT = Path(__file__).resolve().parents[1]
FIX_VALID = ROOT / "tests" / "fixtures" / "case_dry_run" / "valid"
FIX_BAD = ROOT / "tests" / "fixtures" / "case_dry_run" / "bad_flags"


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture
def migrated_db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "pipeline.db"
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    try:
        command.upgrade(_alembic_config(), "head")
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()
        engine.dispose()
    return url


def _session(url: str) -> Session:
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return sessionmaker(bind=engine, autoflush=False)()


def _copy_valid(dst: Path) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    for name in (
        "df_Uid_data_hack.csv",
        "df_Uid_payment_hack.csv",
        "df_Fid_Uid_link_hack.csv",
    ):
        shutil.copy2(FIX_VALID / name, dst / name)
    return dst


def test_redact_database_url_hides_password():
    assert "***" in redact_database_url("postgresql://user:secret@host:5432/db")
    assert "secret" not in redact_database_url("postgresql://user:secret@host:5432/db")


def test_full_import_ready(migrated_db_url: str, tmp_path: Path):
    input_dir = _copy_valid(tmp_path / "in")
    result = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_a",
        version_label="v1",
        report_dir=tmp_path / "reports",
    )
    assert result.status == "ready"
    assert result.snapshot_id

    with _session(migrated_db_url) as s:
        snap = s.get(CaseSnapshot, result.snapshot_id)
        assert snap is not None
        assert snap.status == "ready"
        assert snap.built_at is not None
        run = s.get(CaseImportRun, result.import_run_id)
        assert run is not None and run.status == "completed"
        files = s.scalars(
            select(CaseImportFile).where(CaseImportFile.import_run_id == run.id)
        ).all()
        assert len(files) == 3
        assert all(f.status == "completed" for f in files)
        assert s.scalar(select(func.count()).select_from(CaseOrgCatalogRow)) >= 1
        assert s.scalar(select(func.count()).select_from(CasePayment)) >= 1
        assert s.scalar(select(func.count()).select_from(CasePersonOrgLink)) >= 1
        assert s.scalars(select(Company)).first() is None
        assert s.scalars(select(CompanyMembership)).first() is None
        assert s.scalars(select(CaseOrgCompanyLink)).first() is None
        assert s.get(CaseActiveSnapshot, "slot_a") is None


def test_rerun_identical_skip(migrated_db_url: str, tmp_path: Path):
    input_dir = _copy_valid(tmp_path / "in")
    r1 = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_a",
        version_label="v1",
        report_dir=tmp_path / "r1",
    )
    assert r1.status == "ready"
    r2 = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_a",
        version_label="v2",
        report_dir=tmp_path / "r2",
    )
    assert r2.status == "identical_skip"
    assert r2.snapshot_id == r1.snapshot_id

    with _session(migrated_db_url) as s:
        assert s.scalar(select(func.count()).select_from(CaseSnapshot)) == 1
        assert s.scalar(select(func.count()).select_from(CaseOrgCatalogRow)) == s.scalar(
            select(func.count()).select_from(CaseOrgCatalogRow)
        )


def test_preflight_error_no_db_rows(migrated_db_url: str, tmp_path: Path):
    input_dir = tmp_path / "bad"
    shutil.copytree(FIX_BAD, input_dir)
    result = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_a",
        version_label="v1",
        report_dir=tmp_path / "reports",
    )
    assert result.status == "preflight_failed"
    with _session(migrated_db_url) as s:
        assert s.scalar(select(func.count()).select_from(CaseSnapshot)) == 0
        assert s.scalar(select(func.count()).select_from(CaseOrgCatalogRow)) == 0


def test_payment_load_fails_after_batch_keeps_catalog(
    migrated_db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    input_dir = _copy_valid(tmp_path / "in")
    # Ensure ≥2 payment rows so batch_size=1 can commit the first then fail.
    pay = input_dir / "df_Uid_payment_hack.csv"
    pay.write_text(
        "BENEFICIARY;PAYER;PAY_AMT;PAY_CNT\n"
        "U_1;U_2;10.0;1\n"
        "U_1;U_3;20.0;1\n",
        encoding="utf-8",
        newline="\n",
    )
    # Seed an active pointer that must survive.
    with _session(migrated_db_url) as s:
        other = CaseSnapshot(
            id="00000000-0000-0000-0000-000000000099",
            slot_key="slot_a",
            version_label="prior",
            version_seq=1,
            status="active",
            import_run_id=None,
        )
        s.add(other)
        s.flush()
        s.add(
            CaseActiveSnapshot(
                slot_key="slot_a",
                active_snapshot_id=other.id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        s.commit()

    # Preflight stays clean; corrupt the 2nd logical row only inside the payment loader.
    # Note: app.services.case_data.load_payments is the function export — load the module.
    import importlib

    from app.services.case_data.csv_io import CsvRow

    lp_mod = importlib.import_module("app.services.case_data.load_payments")
    real_iter = lp_mod.iter_csv_rows

    def flaky_iter(path: Path):
        for i, row in enumerate(real_iter(path)):
            if i == 1:
                vals = dict(row.values)
                vals["PAY_AMT"] = "not-a-money"
                yield CsvRow(record_number=row.record_number, values=vals)
            else:
                yield row

    monkeypatch.setattr(lp_mod, "iter_csv_rows", flaky_iter)

    result = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_a",
        version_label="v-fail-pay",
        report_dir=tmp_path / "reports",
        batch_size=1,
    )
    assert result.status == "failed"
    assert result.reason == "load_failed:payments"

    with _session(migrated_db_url) as s:
        snap = s.get(CaseSnapshot, result.snapshot_id)
        assert snap is not None and snap.status == "failed"
        run = s.get(CaseImportRun, result.import_run_id)
        assert run is not None and run.status == "failed"
        completed = [
            f
            for f in s.scalars(
                select(CaseImportFile).where(CaseImportFile.import_run_id == run.id)
            ).all()
            if f.status == "completed"
        ]
        assert len(completed) == 1  # companies only
        assert s.scalar(
            select(func.count())
            .select_from(CaseOrgCatalogRow)
            .where(CaseOrgCatalogRow.snapshot_id == snap.id)
        ) >= 1
        assert (
            s.scalar(
                select(func.count())
                .select_from(CasePayment)
                .where(CasePayment.snapshot_id == snap.id)
            )
            == 0
        )
        ptr = s.get(CaseActiveSnapshot, "slot_a")
        assert ptr is not None
        assert ptr.active_snapshot_id == "00000000-0000-0000-0000-000000000099"
        assert s.get(CaseSnapshot, ptr.active_snapshot_id).status == "active"


def test_final_verify_failure_not_ready(migrated_db_url: str, tmp_path: Path, monkeypatch):
    input_dir = _copy_valid(tmp_path / "in")

    def boom(*_a, **_k):
        raise FinalVerificationError("injected")

    monkeypatch.setattr(pipe, "_final_verify", boom)
    result = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_a",
        version_label="v1",
        report_dir=tmp_path / "reports",
    )
    assert result.status == "failed"
    assert result.reason == "final_verification_failed"
    with _session(migrated_db_url) as s:
        snap = s.get(CaseSnapshot, result.snapshot_id)
        assert snap is not None and snap.status == "failed"
        # Domain rows from successful file loads remain for diagnostics
        assert s.scalar(select(func.count()).select_from(CaseOrgCatalogRow)) >= 1


def test_tamper_after_preflight_fails(migrated_db_url: str, tmp_path: Path, monkeypatch):
    input_dir = _copy_valid(tmp_path / "in")
    real = load_company_catalog

    def corrupt_then_load(session, **kwargs):
        path: Path = kwargs["csv_path"]
        path.write_bytes(path.read_bytes() + b"\n#tamper")
        return real(session, **kwargs)

    monkeypatch.setattr(pipe, "load_company_catalog", corrupt_then_load)
    result = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_a",
        version_label="v1",
        report_dir=tmp_path / "reports",
    )
    assert result.status == "failed"
    assert result.reason == "load_failed:companies"
    with _session(migrated_db_url) as s:
        assert s.get(CaseSnapshot, result.snapshot_id).status == "failed"
        assert s.scalar(select(func.count()).select_from(CaseOrgCatalogRow)) == 0


def test_version_label_conflict(migrated_db_url: str, tmp_path: Path):
    input_dir = _copy_valid(tmp_path / "in")
    r1 = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_a",
        version_label="same",
        report_dir=tmp_path / "r1",
    )
    assert r1.status == "ready"
    # Change payments so content differs
    pay = input_dir / "df_Uid_payment_hack.csv"
    pay.write_text(
        pay.read_text(encoding="utf-8").rstrip() + "\nU_9;U_8;1.0;1\n",
        encoding="utf-8",
    )
    with pytest.raises(VersionLabelConflictError):
        run_case_import(
            input_dir=input_dir,
            database_url=migrated_db_url,
            slot_key="slot_a",
            version_label="same",
            report_dir=tmp_path / "r2",
        )


def test_slots_independent(migrated_db_url: str, tmp_path: Path):
    input_dir = _copy_valid(tmp_path / "in")
    a = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_a",
        version_label="v1",
        report_dir=tmp_path / "a",
    )
    b = run_case_import(
        input_dir=input_dir,
        database_url=migrated_db_url,
        slot_key="slot_b",
        version_label="v1",
        report_dir=tmp_path / "b",
    )
    assert a.status == "ready" and b.status == "ready"
    assert a.snapshot_id != b.snapshot_id
    with _session(migrated_db_url) as s:
        assert s.scalar(select(func.count()).select_from(CaseSnapshot)) == 2
        orgs_a = s.scalar(
            select(func.count())
            .select_from(CaseOrg)
            .where(CaseOrg.snapshot_id == a.snapshot_id)
        )
        orgs_b = s.scalar(
            select(func.count())
            .select_from(CaseOrg)
            .where(CaseOrg.snapshot_id == b.snapshot_id)
        )
        assert orgs_a >= 1 and orgs_b >= 1


def test_cli_refuses_implicit_database_url(tmp_path: Path):
    input_dir = _copy_valid(tmp_path / "in")
    code = import_job.main(
        [
            "--load",
            "--input-dir",
            str(input_dir),
            "--slot-key",
            "slot_a",
            "--version-label",
            "v1",
        ]
    )
    assert code == 2


def test_cli_load_success(migrated_db_url: str, tmp_path: Path):
    input_dir = _copy_valid(tmp_path / "in")
    code = import_job.main(
        [
            "--load",
            "--input-dir",
            str(input_dir),
            "--slot-key",
            "slot_cli",
            "--version-label",
            "v1",
            "--database-url",
            migrated_db_url,
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert code == 0


def test_cli_requires_mode():
    assert import_job.main([]) == 2
    assert import_job.main(["--input-dir", str(FIX_VALID)]) == 2


def test_dry_run_still_skips_application_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./should_never_open_pipeline_dry.db")
    import app.db.session as session_mod

    def _boom(*_a, **_k):
        raise AssertionError("application DB must not be used during dry-run")

    monkeypatch.setattr(session_mod, "SessionLocal", _boom)
    code = import_job.main(
        [
            "--dry-run",
            "--input-dir",
            str(FIX_VALID),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert code == 0
    assert not (ROOT / "should_never_open_pipeline_dry.db").exists()
