"""HTTP verification against isolated case-context backend (no token logging)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "data" / "case" / "verification" / "case_context_integration_latest.json"
RESULT = ROOT / "data" / "case" / "verification" / "case_context_http_verify.json"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_case_context_http.py <base_url>", file=sys.stderr)
        return 2
    base = sys.argv[1].rstrip("/")
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    password = art["users"]["password_hint"]
    company_a = art["company_a"]
    company_b = art["company_b"]
    snap_id = art["snapshot_id"]

    report: dict = {"base_url": base, "checks": []}

    def ok(name: str, detail: dict | None = None) -> None:
        report["checks"].append({"name": name, "ok": True, **(detail or {})})
        print(f"OK {name}", flush=True)

    def fail(name: str, detail: dict | None = None) -> None:
        report["checks"].append({"name": name, "ok": False, **(detail or {})})
        print(f"FAIL {name} {detail}", flush=True)

    with httpx.Client(base_url=base, timeout=120.0, trust_env=False) as client:
        # health
        h = client.get("/health")
        if h.status_code != 200:
            fail("health", {"status": h.status_code})
            RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1
        ok("health")

        def login(email: str) -> str:
            r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
            r.raise_for_status()
            return r.json()["access_token"]

        token_a = login(art["users"]["a"])
        token_b = login(art["users"]["b"])
        token_x = login(art["users"]["outsider"])
        ok("login_a_b_outsider")

        me = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        me.raise_for_status()
        me_body = me.json()
        if me_body.get("email") != art["users"]["a"]:
            fail("users_me_email", {"got": me_body.get("email")})
        else:
            ok("users_me")

        # Count links/memberships before GET context
        # (via a second login-only path — we compare after via artifact counts later)

        ctx_a = client.get(
            f"/api/v1/companies/{company_a['id']}/context",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        if ctx_a.status_code != 200:
            fail("context_a", {"status": ctx_a.status_code})
            RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1
        body_a = ctx_a.json()
        cc = body_a.get("case_context") or {}
        if cc.get("status") != "profile_available":
            fail("context_a_status", {"status": cc.get("status")})
        elif cc.get("snapshot_id") != snap_id:
            fail("context_a_snapshot", {"got": cc.get("snapshot_id")})
        elif cc.get("external_uid") != company_a["external_uid"]:
            fail("context_a_uid", {"got": cc.get("external_uid")})
        else:
            ok(
                "context_a_profile_available",
                {
                    "external_uid": cc.get("external_uid"),
                    "version_label": cc.get("version_label"),
                },
            )

        # Manual fields preserved
        if body_a.get("company_name") != company_a["name"]:
            fail("manual_name", {"got": body_a.get("company_name")})
        else:
            ok("manual_company_name")

        profile = cc.get("profile") or {}
        products = {p["code"]: p["status"] for p in profile.get("products") or []}
        exp_loa = "true" if company_a["expected_loa"] else "false"
        exp_dep = "true" if company_a["expected_dep"] else "false"
        if products.get("LOA") != exp_loa or products.get("DEP") != exp_dep:
            fail("products_a", {"products": products, "expected_loa": exp_loa, "expected_dep": exp_dep})
        else:
            ok("products_a_loa_dep", {"LOA": products.get("LOA"), "DEP": products.get("DEP")})

        fac = (profile.get("factoring") or {}).get("status")
        if fac not in {"true", "false", "unknown", "conflict"}:
            fail("factoring_a", {"status": fac})
        else:
            ok("factoring_a", {"status": fac})

        revenue = profile.get("revenue") or {}
        limitations = revenue.get("limitations") or []
        revenue_blob = json.dumps(revenue, ensure_ascii=False)
        if "do_not_treat_as_rub" not in limitations and "₽" in revenue_blob:
            fail("revenue_rub_guard", {"revenue": revenue})
        elif "₽" in revenue_blob or "руб" in revenue_blob.lower():
            fail("revenue_rub_text", {})
        else:
            ok("revenue_units_guard", {"unit": revenue.get("unit"), "limitations": limitations})

        prov = profile.get("provenance") or {}
        if prov.get("snapshot_id") != snap_id:
            fail("provenance_snapshot", {"got": prov.get("snapshot_id")})
        else:
            ok(
                "provenance",
                {
                    "source_file": prov.get("source_file"),
                    "version_label": prov.get("version_label"),
                },
            )

        # ACL: A cannot read B
        forbidden = client.get(
            f"/api/v1/companies/{company_b['id']}/context",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        if forbidden.status_code != 403:
            fail("acl_a_cannot_read_b", {"status": forbidden.status_code})
        else:
            ok("acl_a_cannot_read_b")

        # B can read own company with different products
        ctx_b = client.get(
            f"/api/v1/companies/{company_b['id']}/context",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        if ctx_b.status_code != 200:
            fail("context_b", {"status": ctx_b.status_code})
        else:
            cc_b = ctx_b.json().get("case_context") or {}
            prof_b = cc_b.get("profile") or {}
            products_b = {p["code"]: p["status"] for p in prof_b.get("products") or []}
            exp_loa_b = "true" if company_b["expected_loa"] else "false"
            exp_dep_b = "true" if company_b["expected_dep"] else "false"
            if cc_b.get("status") != "profile_available":
                fail("context_b_status", {"status": cc_b.get("status")})
            elif products_b.get("LOA") != exp_loa_b or products_b.get("DEP") != exp_dep_b:
                fail("products_b", {"products": products_b})
            elif products_b.get("LOA") == products.get("LOA") and products_b.get("DEP") == products.get(
                "DEP"
            ):
                fail("products_not_distinct", {"a": products, "b": products_b})
            else:
                ok(
                    "context_b_distinct_products",
                    {"LOA": products_b.get("LOA"), "DEP": products_b.get("DEP")},
                )

        # Outsider forbidden for both
        for label, cid in (("a", company_a["id"]), ("b", company_b["id"])):
            r = client.get(
                f"/api/v1/companies/{cid}/context",
                headers={"Authorization": f"Bearer {token_x}"},
            )
            if r.status_code != 403:
                fail(f"acl_outsider_{label}", {"status": r.status_code})
            else:
                ok(f"acl_outsider_{label}")

        # raw_json / secrets not in response
        blob = ctx_a.text
        if "raw_json" in blob or "must-not-leak" in blob:
            fail("no_raw_json")
        else:
            ok("no_raw_json")

    # GET must not change DB link/membership counts
    from sqlalchemy import create_engine, event, func, select
    from sqlalchemy.orm import sessionmaker

    from app.models import CaseOrgCompanyLink, CompanyMembership

    engine = create_engine(art["database_url"])

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False)
    with SessionLocal() as s:
        links = s.scalar(select(func.count()).select_from(CaseOrgCompanyLink))
        memberships = s.scalar(select(func.count()).select_from(CompanyMembership))
    engine.dispose()
    if links != art["counts"]["links"] or memberships != art["counts"]["memberships"]:
        fail(
            "get_no_write",
            {
                "links": links,
                "memberships": memberships,
                "expected": art["counts"],
            },
        )
    else:
        ok("get_no_write", {"links": links, "memberships": memberships})

    failed = [c for c in report["checks"] if not c["ok"]]
    report["passed"] = len(failed) == 0
    report["failed_count"] = len(failed)
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"result_file={RESULT} passed={report['passed']}", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
