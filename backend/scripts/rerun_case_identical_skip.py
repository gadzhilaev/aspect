"""Re-run import expecting identical_skip; compare case table counts."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.services.case_data.import_pipeline import run_case_import

ROOT = Path(__file__).resolve().parents[1]
VER = ROOT / "data" / "case" / "verification"

TABLES = (
    "case_snapshots",
    "case_import_runs",
    "case_import_files",
    "case_org",
    "case_org_catalog_rows",
    "case_org_product_marks",
    "case_org_field_resolution",
    "case_org_groups",
    "case_org_group_members",
    "case_payments",
    "case_persons",
    "case_person_org_links",
    "case_active_snapshot",
    "case_org_company_links",
)


def _counts(url: str) -> dict[str, int]:
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Session = sessionmaker(bind=engine)
    with Session() as s:
        out = {t: int(s.scalar(text(f"SELECT COUNT(*) FROM {t}")) or 0) for t in TABLES}
    engine.dispose()
    return out


def main() -> None:
    url = (VER / "latest_db_url.txt").read_text(encoding="utf-8").strip()
    before = _counts(url)
    prev = json.loads((VER / "import_status.json").read_text(encoding="utf-8"))
    result = run_case_import(
        input_dir=(ROOT / "data" / "case" / "raw").resolve(),
        database_url=url,
        slot_key="competition_default",
        version_label="hack-raw-v2-rerun",
        report_dir=VER / "reports" / "import_hack_raw_v2_rerun",
        batch_size=2000,
    )
    after = _counts(url)
    delta = {t: after[t] - before[t] for t in TABLES}
    out = {
        "status": result.status,
        "snapshot_id": result.snapshot_id,
        "previous_snapshot_id": prev.get("snapshot_id"),
        "same_snapshot": result.snapshot_id == prev.get("snapshot_id"),
        "counts_before": before,
        "counts_after": after,
        "delta": delta,
        "no_new_rows": all(v == 0 for v in delta.values()),
    }
    path = VER / "identical_skip_verify.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if result.status != "identical_skip" or not out["same_snapshot"] or not out["no_new_rows"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
