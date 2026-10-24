"""Prepare isolated DB copy for case context HTTP integration (stage 1.14).

- SQLite online backup of successful 1.9 DB
- Activate ready snapshot (expect-no-active)
- Seed demo users/companies + link two distinct catalog orgs
Does not touch root .env, working DB, or the source 1.9 file.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLOT = "competition_default"
SOURCE_DB = ROOT / "data" / "case" / "verification" / "case_verify_20261020T121608Z.db"
OUT_DIR = ROOT / "data" / "case" / "verification"
ARTIFACT = OUT_DIR / "case_context_integration_latest.json"


def _uid() -> str:
    return str(uuid.uuid4())


def backup_db(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise SystemExit(f"source DB missing: {src}")
    free = None
    try:
        import shutil

        free = shutil.disk_usage(dst.parent).free
    except OSError:
        pass
    size = src.stat().st_size
    if free is not None and free < size + 200 * 1024 * 1024:
        raise SystemExit(
            f"insufficient free space: need ~{size // (1024**3) + 1} GiB, "
            f"free={free // (1024**3)} GiB"
        )
    print(f"backup start src_bytes={size} dst={dst.name}", flush=True)
    src_conn = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    try:
        dst_conn = sqlite3.connect(dst.as_posix())
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    print(f"backup done dst_bytes={dst.stat().st_size}", flush=True)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    copy_path = OUT_DIR / f"case_ctx_integration_{stamp}.db"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Isolated copy via SQLite backup API
    backup_db(SOURCE_DB, copy_path)
    db_url = f"sqlite:///{copy_path.as_posix()}"

    from sqlalchemy import create_engine, event, func, select, text
    from sqlalchemy.orm import sessionmaker

    from app.core.security import hash_password
    from app.models import (
        CaseActiveSnapshot,
        CaseOrg,
        CaseOrgCompanyLink,
        CaseOrgFieldResolution,
        CaseSnapshot,
        Company,
        CompanyMembership,
        User,
    )
    from app.services.case_data.activate_snapshot import run_activation
    from app.services.case_data.link_org_company import run_link

    engine = create_engine(db_url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False)

    # 2) Find ready snapshot + activate
    with SessionLocal() as s:
        ready = list(
            s.scalars(
                select(CaseSnapshot).where(
                    CaseSnapshot.slot_key == SLOT,
                    CaseSnapshot.status == "ready",
                )
            )
        )
        if not ready:
            raise SystemExit("no ready snapshot in copy")
        # Prefer known 1.9 id if present; else highest version_seq
        preferred = "d8fa5477-058e-47c2-9c88-030a20ea92fe"
        snap = next((x for x in ready if x.id == preferred), None)
        if snap is None:
            snap = max(ready, key=lambda x: x.version_seq)
        snap_id = snap.id
        version_label = snap.version_label
        version_seq = snap.version_seq
        print(
            f"ready snapshot id={snap_id} label={version_label!r} seq={version_seq} "
            f"status={snap.status}",
            flush=True,
        )

    r1 = run_activation(
        database_url=db_url,
        slot_key=SLOT,
        snapshot_id=snap_id,
        expect_no_active=True,
    )
    print(f"activate outcome={r1.outcome} current={r1.current_snapshot_id}", flush=True)
    r2 = run_activation(
        database_url=db_url,
        slot_key=SLOT,
        snapshot_id=snap_id,
        expected_active_snapshot_id=snap_id,
    )
    print(f"re-activate outcome={r2.outcome}", flush=True)
    if r2.outcome != "already_active":
        raise SystemExit(f"expected already_active, got {r2.outcome}")

    # Source 1.9 DB must remain ready / no active pointer
    src_engine = create_engine(f"sqlite:///{SOURCE_DB.as_posix()}")

    @event.listens_for(src_engine, "connect")
    def _fk_src(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SrcSession = sessionmaker(bind=src_engine, autoflush=False)
    with SrcSession() as s:
        src_snap = s.get(CaseSnapshot, snap_id)
        src_ptr = s.get(CaseActiveSnapshot, SLOT)
        src_status = src_snap.status if src_snap else None
        src_ptr_id = src_ptr.active_snapshot_id if src_ptr else None
        print(
            f"source_db snapshot_status={src_status} pointer={src_ptr_id}",
            flush=True,
        )
        if src_status != "ready":
            raise SystemExit("source 1.9 snapshot is no longer ready")
        if src_ptr_id is not None:
            raise SystemExit("source 1.9 unexpectedly has active pointer")
    src_engine.dispose()

    # 3) Pick two orgs with distinct confirmed product marks (LOA / DEP)
    with SessionLocal() as s:
        # SQLite JSON extract on consensus products
        rows = s.execute(
            text(
                """
                SELECT o.external_uid,
                       json_extract(r.consensus_json, '$.products.LOA') AS loa,
                       json_extract(r.consensus_json, '$.products.DEP') AS dep,
                       json_extract(r.consensus_json, '$.products.RKO') AS rko,
                       json_extract(r.consensus_json, '$.factoring_mark') AS fac,
                       json_extract(r.consensus_json, '$.mainokved_code') AS okved,
                       json_extract(r.consensus_json, '$.city') AS city
                FROM case_org o
                JOIN case_org_field_resolution r
                  ON r.case_org_id = o.id AND r.snapshot_id = o.snapshot_id
                WHERE o.snapshot_id = :sid
                  AND o.has_catalog_profile = 1
                  AND json_extract(r.consensus_json, '$.products.LOA') IS NOT NULL
                  AND json_extract(r.consensus_json, '$.products.DEP') IS NOT NULL
                LIMIT 4000
                """
            ),
            {"sid": snap_id},
        ).mappings().all()

        pick_a = None
        pick_b = None
        for row in rows:
            loa = bool(row["loa"])
            dep = bool(row["dep"])
            if pick_a is None and loa and not dep:
                pick_a = dict(row)
            if pick_b is None and dep and not loa:
                pick_b = dict(row)
            if pick_a and pick_b:
                break
        if not pick_a or not pick_b:
            # fallback: any differing LOA
            for row in rows:
                if pick_a is None:
                    pick_a = dict(row)
                    continue
                if bool(row["loa"]) != bool(pick_a["loa"]):
                    pick_b = dict(row)
                    break
        if not pick_a or not pick_b:
            raise SystemExit("could not find two orgs with distinct product marks")

        print(
            f"org_a uid={pick_a['external_uid']} loa={pick_a['loa']} dep={pick_a['dep']} "
            f"okved={pick_a['okved']!r} city={pick_a['city']!r}",
            flush=True,
        )
        print(
            f"org_b uid={pick_b['external_uid']} loa={pick_b['loa']} dep={pick_b['dep']} "
            f"okved={pick_b['okved']!r} city={pick_b['city']!r}",
            flush=True,
        )

        # Seed users / companies (demo names only)
        now = datetime.now(timezone.utc)
        password = "CaseCtxDemo1!"
        user_a = User(
            id=_uid(),
            email="case-demo-a@example.com",
            password_hash=hash_password(password),
            display_name="Case Demo A",
            email_verified_at=now,
        )
        user_b = User(
            id=_uid(),
            email="case-demo-b@example.com",
            password_hash=hash_password(password),
            display_name="Case Demo B",
            email_verified_at=now,
        )
        user_x = User(
            id=_uid(),
            email="case-demo-outsider@example.com",
            password_hash=hash_password(password),
            display_name="Case Demo Outsider",
            email_verified_at=now,
        )
        s.add_all([user_a, user_b, user_x])
        s.flush()
        company_a = Company(
            id=_uid(),
            name="Демо-контур Альфа (стенд)",
            industry="electronics",
            size_band="medium",
            hq_region="Демо-регион А",
            profile_status="ready",
            digital_twin_status="not_built",
            digital_twin_coverage=0.0,
            is_demo=True,
            created_by=user_a.id,
        )
        company_b = Company(
            id=_uid(),
            name="Демо-контур Бета (стенд)",
            industry="logistics",
            size_band="small",
            hq_region="Демо-регион Б",
            profile_status="ready",
            digital_twin_status="not_built",
            digital_twin_coverage=0.0,
            is_demo=True,
            created_by=user_b.id,
        )
        s.add_all([company_a, company_b])
        s.flush()
        s.add_all(
            [
                CompanyMembership(
                    id=_uid(), user_id=user_a.id, company_id=company_a.id, role="owner"
                ),
                CompanyMembership(
                    id=_uid(), user_id=user_b.id, company_id=company_b.id, role="owner"
                ),
            ]
        )
        s.commit()
        company_a_id = company_a.id
        company_b_id = company_b.id
        uid_a = pick_a["external_uid"]
        uid_b = pick_b["external_uid"]

    link_a = run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid=uid_a,
        company_id=company_a_id,
        linked_by="case-ctx-integration",
    )
    link_b = run_link(
        database_url=db_url,
        slot_key=SLOT,
        external_uid=uid_b,
        company_id=company_b_id,
        linked_by="case-ctx-integration",
    )
    print(f"link_a={link_a.outcome} link_b={link_b.outcome}", flush=True)

    with SessionLocal() as s:
        links = s.scalar(select(func.count()).select_from(CaseOrgCompanyLink))
        memberships = s.scalar(select(func.count()).select_from(CompanyMembership))
        ptr = s.get(CaseActiveSnapshot, SLOT)
        active = s.scalars(
            select(CaseSnapshot).where(
                CaseSnapshot.slot_key == SLOT, CaseSnapshot.status == "active"
            )
        ).all()
        artifact = {
            "copy_db": str(copy_path),
            "database_url": db_url,
            "slot_key": SLOT,
            "snapshot_id": snap_id,
            "version_label": version_label,
            "version_seq": version_seq,
            "activation": {"first": r1.outcome, "second": r2.outcome},
            "source_1_9_status": "ready",
            "source_1_9_pointer": None,
            "company_a": {
                "id": company_a_id,
                "name": "Демо-контур Альфа (стенд)",
                "external_uid": uid_a,
                "expected_loa": bool(pick_a["loa"]),
                "expected_dep": bool(pick_a["dep"]),
                "expected_okved": pick_a["okved"],
            },
            "company_b": {
                "id": company_b_id,
                "name": "Демо-контур Бета (стенд)",
                "external_uid": uid_b,
                "expected_loa": bool(pick_b["loa"]),
                "expected_dep": bool(pick_b["dep"]),
                "expected_okved": pick_b["okved"],
            },
            "users": {
                "a": "case-demo-a@example.com",
                "b": "case-demo-b@example.com",
                "outsider": "case-demo-outsider@example.com",
                "password_hint": "CaseCtxDemo1!",
            },
            "counts": {"links": links, "memberships": memberships},
            "pointer": ptr.active_snapshot_id if ptr else None,
            "active_count": len(active),
        }
    ARTIFACT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"artifact={ARTIFACT}", flush=True)
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
