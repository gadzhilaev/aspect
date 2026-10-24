"""HTTP smoke against running competition Docker stack (stage 6.14). No live LLM.

Reads credentials from the named stand volume (not printed). Writes JSON report
under data/competition_docker_smoke/ (gitignored).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
WEB = "http://127.0.0.1:18080"
API = "http://127.0.0.1:18019"
VOLUME = "kontur_comp_smoke_614_stand_data"
OUT = ROOT / "data" / "competition_docker_smoke" / "smoke_614_report.json"
PROJECT = "kontur_comp_smoke_614"


def _volume_cat(rel: str) -> str:
    r = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{VOLUME}:/stand:ro",
            "alpine:3.20",
            "cat",
            f"/stand/{rel}",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"volume cat {rel} failed: {r.stderr[:300]}")
    return r.stdout


def _sqlite_one(sql: str) -> str:
    """Query stand.db in the volume without invoking the API entrypoint."""
    r = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "-v",
            f"{VOLUME}:/stand:ro",
            "kontur-competition-api:local",
            "-c",
            "import sqlite3; c=sqlite3.connect('/stand/stand.db'); "
            f"row=c.execute({sql!r}).fetchone(); "
            "print('|'.join('' if x is None else str(x) for x in row) if row else '')",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"sqlite query failed: {r.stderr[:300]}")
    return (r.stdout or "").strip()


def _parse_password(raw: str) -> tuple[str, str]:
    email = None
    password = None
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("email="):
            email = s.split("=", 1)[1].strip()
        elif s.startswith("password="):
            password = s.split("=", 1)[1].strip()
        elif s and "@" in s and email is None and "=" not in s:
            email = s
        elif s and password is None and "=" not in s and "@" not in s:
            password = s
    # bootstrap may write bare password only; email from manifest
    if password and not email:
        man = json.loads(_volume_cat("stand_manifest.json"))
        email = (man.get("demo_login") or {}).get("email") or man.get("email")
        if not email and man.get("profiles"):
            # fall back: competition seed emails
            email = "competition-demo-a@example.com"
    if not email or not password:
        raise RuntimeError("could not parse demo credentials from volume")
    return email, password


def _wait(url: str, *, timeout: float = 60.0) -> None:
    # trust_env=False: Windows system proxy can otherwise intercept 127.0.0.1 → 503.
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=3.0, trust_env=False)
            if r.status_code < 500:
                return
            last = r.status_code
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(1.0)
    raise RuntimeError(f"timeout waiting {url}: {last}")


def main() -> int:
    report: dict[str, Any] = {
        "stage": "6.14",
        "project": PROJECT,
        "web_base": WEB,
        "api_base": API,
        "volume": VOLUME,
        "checks": {},
        "ok": False,
    }
    _wait(f"{API}/health")
    _wait(f"{WEB}/healthz")

    email, password = _parse_password(_volume_cat("demo_password.local"))
    manifest = json.loads(_volume_cat("stand_manifest.json"))
    company_id = (manifest.get("profiles") or [{}])[0].get("company_id")
    event_id = (manifest.get("event") or {}).get("id")
    report["company_id_present"] = bool(company_id)
    report["event_id_present"] = bool(event_id)
    report["email_domain"] = email.split("@")[-1] if email else None

    with httpx.Client(timeout=30.0, follow_redirects=True, trust_env=False) as client:
        # Health
        hz = client.get(f"{WEB}/healthz")
        report["checks"]["web_healthz"] = hz.status_code == 200 and "ok" in hz.text.lower()
        ha = client.get(f"{API}/health")
        report["checks"]["api_health"] = ha.status_code == 200
        # same-origin /health via nginx proxy
        hw = client.get(f"{WEB}/health")
        report["checks"]["web_proxied_health"] = hw.status_code == 200

        # Frontend + SPA
        home = client.get(f"{WEB}/")
        report["checks"]["frontend_index"] = home.status_code == 200 and (
            "html" in home.headers.get("content-type", "").lower()
            or "<!doctype" in home.text[:200].lower()
            or "<html" in home.text[:200].lower()
        )
        spa = client.get(f"{WEB}/news/for-you")
        report["checks"]["spa_deep_link"] = spa.status_code == 200 and (
            "html" in spa.headers.get("content-type", "").lower()
            or "<div id=\"root\"" in spa.text
            or "<div id='root'" in spa.text
            or "index-" in spa.text
        )

        # same-origin public API
        pub = client.get(f"{WEB}/api/v1/public/news", params={"limit": 10})
        report["checks"]["same_origin_public_news"] = pub.status_code == 200
        pub_items = []
        if pub.status_code == 200:
            body = pub.json()
            pub_items = body.get("items") or []
        report["public_news_count"] = len(pub_items)
        report["checks"]["public_news_nonempty"] = len(pub_items) >= 1

        # Login + ACL
        login = client.post(
            f"{WEB}/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        report["checks"]["login"] = login.status_code == 200
        token = login.json().get("access_token") if login.status_code == 200 else None
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        me = client.get(f"{WEB}/api/v1/users/me", headers=headers)
        report["checks"]["me"] = me.status_code == 200
        companies = (me.json().get("companies") or []) if me.status_code == 200 else []
        ids = [c.get("company_id") for c in companies]
        report["checks"]["acl_membership"] = bool(company_id and company_id in ids)
        if not company_id and ids:
            company_id = ids[0]

        # Foreign company should 403/404
        foreign = client.get(
            f"{WEB}/api/v1/companies/00000000-0000-0000-0000-000000000099/context",
            headers=headers,
        )
        report["checks"]["acl_foreign_denied"] = foreign.status_code in (403, 404)

        # Case context
        ctx = client.get(f"{WEB}/api/v1/companies/{company_id}/context", headers=headers)
        report["checks"]["company_context"] = ctx.status_code == 200
        ctx_body = ctx.json() if ctx.status_code == 200 else {}
        blob = json.dumps(ctx_body, ensure_ascii=False)
        report["checks"]["context_mentions_uid"] = "U_900001" in blob or "U_900002" in blob

        # Personal feed
        feed = client.get(
            f"{WEB}/api/v1/companies/{company_id}/events",
            headers=headers,
            params={"limit": 20},
        )
        report["checks"]["personal_feed"] = feed.status_code == 200
        feed_items = (feed.json().get("items") or []) if feed.status_code == 200 else []
        report["personal_feed_count"] = len(feed_items)

        dash = client.get(
            f"{WEB}/api/v1/companies/{company_id}/dashboard",
            headers=headers,
        )
        report["checks"]["dashboard"] = dash.status_code == 200

        # Bank fragment + document + PDF SHA (no list endpoint by design)
        frag_row = _sqlite_one("select id, document_id from bank_fragments limit 1")
        fragment_id = frag_row.split("|")[0] if "|" in frag_row else frag_row or None
        document_id = frag_row.split("|")[1] if "|" in frag_row else None
        frag = (
            client.get(
                f"{WEB}/api/v1/bank-materials/fragments/{fragment_id}",
                headers=headers,
            )
            if fragment_id
            else None
        )
        report["checks"]["bank_fragment"] = bool(frag and frag.status_code == 200)
        doc = (
            client.get(
                f"{WEB}/api/v1/bank-materials/documents/{document_id}",
                headers=headers,
            )
            if document_id
            else None
        )
        report["checks"]["bank_document"] = bool(doc and doc.status_code == 200)

        file_row = _sqlite_one("select id, sha256 from bank_document_files limit 1")
        file_id = None
        expected_sha = None
        if "|" in file_row:
            file_id, expected_sha = file_row.split("|", 1)
        report["bank_file_id_present"] = bool(file_id)
        pdf_ok = False
        sha_ok = False
        if file_id:
            pdf = client.get(
                f"{WEB}/api/v1/bank-materials/files/{file_id}/content",
                headers=headers,
            )
            pdf_ok = pdf.status_code == 200 and len(pdf.content) > 100
            if pdf_ok:
                digest = hashlib.sha256(pdf.content).hexdigest()
                report["pdf_sha256"] = digest
                sha_ok = (not expected_sha) or digest == expected_sha
                report["expected_sha_match"] = sha_ok
                report["expected_sha_present"] = bool(expected_sha)
            # unauthenticated must fail
            pdf_anon = client.get(
                f"{WEB}/api/v1/bank-materials/files/{file_id}/content",
            )
            report["checks"]["pdf_requires_auth"] = pdf_anon.status_code in (401, 403)
        report["checks"]["bank_pdf"] = pdf_ok
        report["checks"]["bank_pdf_sha"] = sha_ok if pdf_ok else False

        if event_id:
            evid = client.get(
                f"{WEB}/api/v1/events/{event_id}/bank-evidence",
                headers=headers,
                params={"company_id": company_id},
            )
            report["checks"]["event_bank_evidence"] = evid.status_code in (200, 404)

    report["ok"] = all(
        v is True
        for k, v in report["checks"].items()
        if k != "event_bank_evidence"  # 404 acceptable on tiny smoke
    ) and report["checks"].get("bank_pdf") and report["checks"].get("bank_pdf_sha")

    # Soft: event_bank_evidence optional
    critical = [
        "web_healthz",
        "api_health",
        "web_proxied_health",
        "frontend_index",
        "spa_deep_link",
        "same_origin_public_news",
        "public_news_nonempty",
        "login",
        "me",
        "acl_membership",
        "acl_foreign_denied",
        "company_context",
        "personal_feed",
        "dashboard",
        "bank_fragment",
        "bank_document",
        "bank_pdf",
        "bank_pdf_sha",
        "pdf_requires_auth",
    ]
    report["ok"] = all(report["checks"].get(k) is True for k in critical)
    report["failed"] = [k for k in critical if report["checks"].get(k) is not True]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "failed": report["failed"], "report": str(OUT.relative_to(ROOT)).replace("\\", "/")}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
