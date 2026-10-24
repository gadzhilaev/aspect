"""Independent SQL checks after real case import (verification DB only)."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker

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
    User,
)
from app.services.case_data.csv_io import payment_content_sha256, sha256_file
from app.services.case_data.validate import parse_money_numeric_20_1

ROOT = Path(__file__).resolve().parents[1]
VER = ROOT / "data" / "case" / "verification"
RAW = ROOT / "data" / "case" / "raw"


def main() -> None:
    url = (VER / "latest_db_url.txt").read_text(encoding="utf-8").strip()
    status = json.loads((VER / "import_status.json").read_text(encoding="utf-8"))
    snap_id = status["snapshot_id"]
    run_id = status["import_run_id"]
    manifest = {m["role"]: m for m in status["manifest"]}

    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Session = sessionmaker(bind=engine)
    checks: dict = {"ok": True, "details": {}}

    def fail(name: str, msg: str) -> None:
        checks["ok"] = False
        checks["details"][name] = {"ok": False, "error": msg}

    def ok(name: str, data) -> None:
        checks["details"][name] = {"ok": True, "data": data}

    with Session() as s:
        snap = s.get(CaseSnapshot, snap_id)
        run = s.get(CaseImportRun, run_id)
        if not snap or snap.status != "ready":
            fail("snapshot_ready", f"status={getattr(snap, 'status', None)}")
        else:
            ok("snapshot_ready", {"status": snap.status, "built_at": str(snap.built_at)})
        if not run or run.status != "completed":
            fail("run_completed", f"status={getattr(run, 'status', None)}")
        else:
            ok("run_completed", {"status": run.status})

        files = list(
            s.scalars(select(CaseImportFile).where(CaseImportFile.import_run_id == run_id)).all()
        )
        file_map = {f.source_file: f for f in files}
        if len(files) != 3 or any(f.status != "completed" for f in files):
            fail(
                "files_completed",
                {f.source_file: f.status for f in files},
            )
        else:
            ok(
                "files_completed",
                {
                    f.source_file: {
                        "status": f.status,
                        "row_count_loaded": f.row_count_loaded,
                        "sha256": f.content_sha256,
                    }
                    for f in files
                },
            )

        # Counts vs manifest
        cat_n = s.scalar(
            select(func.count())
            .select_from(CaseOrgCatalogRow)
            .where(CaseOrgCatalogRow.snapshot_id == snap_id)
        )
        pay_n = s.scalar(
            select(func.count()).select_from(CasePayment).where(CasePayment.snapshot_id == snap_id)
        )
        link_n = s.scalar(
            select(func.count())
            .select_from(CasePersonOrgLink)
            .where(CasePersonOrgLink.snapshot_id == snap_id)
        )
        counts = {
            "catalog": cat_n,
            "payments": pay_n,
            "person_links": link_n,
            "manifest": {
                "companies": manifest["companies"]["record_count"],
                "payments": manifest["payments"]["record_count"],
                "person_links": manifest["person_links"]["record_count"],
            },
        }
        if (
            cat_n != manifest["companies"]["record_count"]
            or pay_n != manifest["payments"]["record_count"]
            or link_n != manifest["person_links"]["record_count"]
        ):
            fail("counts_match_manifest", counts)
        else:
            ok("counts_match_manifest", counts)

        # SHA vs disk files used for import (raw sources)
        sha_checks = {}
        for role, fname in (
            ("companies", "df_Uid_data_hack.csv"),
            ("payments", "df_Uid_payment_hack.csv"),
            ("person_links", "df_Fid_Uid_link_hack.csv"),
        ):
            disk_sha, _ = sha256_file(RAW / fname)
            db_sha = file_map[fname].content_sha256
            man_sha = manifest[role]["sha256"]
            sha_checks[role] = {
                "disk": disk_sha,
                "db": db_sha,
                "manifest": man_sha,
                "match": disk_sha == db_sha == man_sha,
            }
        if not all(v["match"] for v in sha_checks.values()):
            fail("sha256_match", sha_checks)
        else:
            ok("sha256_match", {k: v["disk"] for k, v in sha_checks.items()})

        # Snapshot isolation
        foreign = {
            "catalog": s.scalar(
                select(func.count())
                .select_from(CaseOrgCatalogRow)
                .where(
                    CaseOrgCatalogRow.import_run_id == run_id,
                    CaseOrgCatalogRow.snapshot_id != snap_id,
                )
            ),
            "payments": s.scalar(
                select(func.count())
                .select_from(CasePayment)
                .where(CasePayment.import_run_id == run_id, CasePayment.snapshot_id != snap_id)
            ),
            "links": s.scalar(
                select(func.count())
                .select_from(CasePersonOrgLink)
                .where(
                    CasePersonOrgLink.import_run_id == run_id,
                    CasePersonOrgLink.snapshot_id != snap_id,
                )
            ),
        }
        if any(foreign.values()):
            fail("snapshot_isolation", foreign)
        else:
            ok("snapshot_isolation", foreign)

        # FK check
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=ON"))
            fk_rows = list(conn.execute(text("PRAGMA foreign_key_check")).mappings())
        if fk_rows:
            fail("foreign_key_check", [dict(r) for r in fk_rows[:20]])
        else:
            ok("foreign_key_check", {"violations": 0})

        # Orphans without invented profile
        orphans = s.scalar(
            select(func.count())
            .select_from(CaseOrg)
            .where(
                CaseOrg.snapshot_id == snap_id,
                CaseOrg.has_catalog_profile.is_(False),
                CaseOrg.profile_resolution == "absent",
            )
        )
        bad_orphans = s.scalar(
            select(func.count())
            .select_from(CaseOrg)
            .where(
                CaseOrg.snapshot_id == snap_id,
                CaseOrg.has_catalog_profile.is_(False),
                CaseOrg.profile_resolution != "absent",
            )
        )
        if bad_orphans:
            fail("orphans", {"bad": bad_orphans, "absent_orphans": orphans})
        else:
            ok("orphans", {"absent_profile_orgs": orphans})

        # Conflicting UID U_428697 — all variants kept
        conflict_uid = "U_428697"
        org = s.scalar(
            select(CaseOrg).where(
                CaseOrg.snapshot_id == snap_id, CaseOrg.external_uid == conflict_uid
            )
        )
        if org is None:
            fail("conflict_uid", "U_428697 missing")
        else:
            variants = s.scalar(
                select(func.count())
                .select_from(CaseOrgCatalogRow)
                .where(CaseOrgCatalogRow.case_org_id == org.id)
            )
            ok(
                "conflict_uid",
                {
                    "uid": conflict_uid,
                    "variants": variants,
                    "profile_resolution": org.profile_resolution,
                },
            )

        # Payment dups: identical content ranks
        # Find one sha with count>1 from DB
        dup = s.execute(
            text(
                """
                SELECT row_content_sha256, COUNT(*) AS c
                FROM case_payments
                WHERE snapshot_id = :sid
                GROUP BY row_content_sha256
                HAVING c > 1
                ORDER BY c DESC
                LIMIT 1
                """
            ),
            {"sid": snap_id},
        ).mappings().first()
        if dup:
            ranks = list(
                s.scalars(
                    select(CasePayment.intra_file_dup_rank)
                    .where(
                        CasePayment.snapshot_id == snap_id,
                        CasePayment.row_content_sha256 == dup["row_content_sha256"],
                    )
                    .order_by(CasePayment.intra_file_dup_rank)
                ).all()
            )
            expected = list(range(1, int(dup["c"]) + 1))
            if ranks != expected:
                fail("payment_dup_ranks", {"ranks": ranks, "expected": expected})
            else:
                ok(
                    "payment_dup_ranks",
                    {"sha_prefix": dup["row_content_sha256"][:12], "count": dup["c"], "ranks": ranks},
                )
        else:
            ok("payment_dup_ranks", {"note": "no duplicate content hashes in DB"})

        # F-U relation_kind
        non_unspec = s.scalar(
            select(func.count())
            .select_from(CasePersonOrgLink)
            .where(
                CasePersonOrgLink.snapshot_id == snap_id,
                CasePersonOrgLink.relation_kind != "unspecified",
            )
        )
        if non_unspec:
            fail("relation_kind", {"non_unspecified": non_unspec})
        else:
            ok("relation_kind", {"all_unspecified": True, "rows": link_n})

        # Money units NULL
        pay_units = s.execute(
            text(
                """
                SELECT
                  SUM(CASE WHEN amount_unit IS NOT NULL THEN 1 ELSE 0 END) AS u,
                  SUM(CASE WHEN amount_currency IS NOT NULL THEN 1 ELSE 0 END) AS c,
                  SUM(CASE WHEN period_label IS NOT NULL THEN 1 ELSE 0 END) AS p
                FROM case_payments WHERE snapshot_id = :sid
                """
            ),
            {"sid": snap_id},
        ).mappings().one()
        rev_units = s.execute(
            text(
                """
                SELECT
                  SUM(CASE WHEN revenue_unit IS NOT NULL THEN 1 ELSE 0 END) AS u,
                  SUM(CASE WHEN revenue_currency IS NOT NULL THEN 1 ELSE 0 END) AS c
                FROM case_org_catalog_rows WHERE snapshot_id = :sid
                """
            ),
            {"sid": snap_id},
        ).mappings().one()
        if any(pay_units.values()) or any(rev_units.values()):
            fail("units_null", {"payments": dict(pay_units), "revenue": dict(rev_units)})
        else:
            ok("units_null", {"payments": dict(pay_units), "revenue": dict(rev_units)})

        # No user/company side effects
        side = {
            "companies": s.scalar(select(func.count()).select_from(Company)),
            "users": s.scalar(select(func.count()).select_from(User)),
            "memberships": s.scalar(select(func.count()).select_from(CompanyMembership)),
            "identity_links": s.scalar(select(func.count()).select_from(CaseOrgCompanyLink)),
            "active_pointer": s.get(CaseActiveSnapshot, "competition_default"),
        }
        if (
            side["companies"]
            or side["users"]
            or side["memberships"]
            or side["identity_links"]
            or side["active_pointer"] is not None
        ):
            fail("no_side_effects", {k: (str(v) if k == "active_pointer" else v) for k, v in side.items()})
        else:
            ok("no_side_effects", side)

        # Decimal spot-check: largest PAY_AMT and a few samples from CSV→DB
        samples = _money_samples(s, snap_id)
        if not samples["ok"]:
            fail("money_precision", samples)
        else:
            ok("money_precision", samples)

    # Table row totals for identical_skip comparison later
    with Session() as s:
        table_counts = {}
        for table in (
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
            "companies",
            "users",
            "company_memberships",
        ):
            table_counts[table] = s.scalar(text(f"SELECT COUNT(*) FROM {table}"))

    out = {
        "snapshot_id": snap_id,
        "import_run_id": run_id,
        "checks": checks,
        "table_counts": table_counts,
        "db_size_bytes": Path(
            (VER / "latest_db_path.txt").read_text(encoding="utf-8").strip()
        ).stat().st_size,
    }
    out_path = VER / "independent_verify.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"ok": checks["ok"], "path": str(out_path)}, ensure_ascii=False))
    if not checks["ok"]:
        raise SystemExit(1)


def _money_samples(session, snap_id: str) -> dict:
    # Largest pay_amt from DB
    row = session.execute(
        text(
            """
            SELECT pay_amt_raw, pay_amt, source_row_number
            FROM case_payments
            WHERE snapshot_id = :sid AND pay_amt IS NOT NULL
            ORDER BY pay_amt DESC
            LIMIT 1
            """
        ),
        {"sid": snap_id},
    ).mappings().one()
    parsed = parse_money_numeric_20_1(row["pay_amt_raw"])
    largest_ok = (
        parsed.ok
        and parsed.value == Decimal(str(row["pay_amt"]))
        and row["pay_amt_raw"] == parsed.raw
    )

    # Spot-check a few revenues from CSV file vs DB by source_row_number
    csv_path = RAW / "df_Uid_data_hack.csv"
    spot = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for i, rec in enumerate(reader, start=1):
            if i in {1, 1000, 50000, 85525}:
                raw = rec.get("REVENUE_COMPANY", "")
                db = session.execute(
                    text(
                        """
                        SELECT revenue_raw, revenue_amount
                        FROM case_org_catalog_rows
                        WHERE snapshot_id = :sid AND source_row_number = :n
                        """
                    ),
                    {"sid": snap_id, "n": i},
                ).mappings().one()
                p = parse_money_numeric_20_1(raw)
                spot.append(
                    {
                        "row": i,
                        "csv_raw": raw,
                        "db_raw": db["revenue_raw"],
                        "db_amount": str(db["revenue_amount"]),
                        "parsed": str(p.value) if p.ok else None,
                        "match": p.ok
                        and db["revenue_raw"] == raw
                        and Decimal(str(db["revenue_amount"])) == p.value,
                    }
                )
    return {
        "ok": largest_ok and all(x["match"] for x in spot),
        "largest_payment": {
            "raw": row["pay_amt_raw"],
            "amount": str(row["pay_amt"]),
            "source_row_number": row["source_row_number"],
            "match": largest_ok,
        },
        "revenue_spots": spot,
    }


if __name__ == "__main__":
    main()
