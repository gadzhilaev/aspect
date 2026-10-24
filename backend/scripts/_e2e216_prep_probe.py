from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

SRC = Path("data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db")
EXPECTED = "92a96805f2b720f76bd0c52d2491044812b38401ab62d0f4a9157b4ca81c49bb"

PDF_CANDIDATES = [
    Path("bank_materials/raw/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"),
    Path("data/bank_materials/raw/ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"),
]


def main() -> None:
    con = sqlite3.connect(SRC)
    tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
        ).fetchall()
    ]
    print("tables", len(tables))
    for t in (
        "users",
        "companies",
        "events",
        "event_impacts",
        "assistant_conversations",
        "bank_fragments",
        "alembic_version",
    ):
        if t in tables:
            print(t, con.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
        else:
            print(t, "MISSING")
    ver = con.execute("SELECT version_num FROM alembic_version").fetchall()
    print("alembic", ver)
    con.close()

    for p in PDF_CANDIDATES:
        print("cand", p.as_posix(), "exists", p.is_file())
        if p.is_file():
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            print("  sha_match", h == EXPECTED, "prefix", h[:16])

    # search any matching pdf under data/bank_materials
    root = Path("data/bank_materials")
    if root.is_dir():
        for pdf in root.rglob("ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"):
            h = hashlib.sha256(pdf.read_bytes()).hexdigest()
            print("found", pdf.as_posix(), "match", h == EXPECTED)


if __name__ == "__main__":
    main()
