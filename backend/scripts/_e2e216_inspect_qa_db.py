"""Inspect Policy Rate rev2 in QA verification DB (no secrets)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SRC = Path("data/bank_materials/verification/bank_real_import_20261021T124200__qa_revisions_copy.db")


def main() -> None:
    print("src_exists", SRC.is_file(), "size", SRC.stat().st_size if SRC.is_file() else None)
    con = sqlite3.connect(SRC)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT f.id, f.stable_key, f.revision, f.content_type, f.verification_status,
               f.primary_region_type, f.kind,
               length(COALESCE(f.verified_transcript, '')) AS tlen,
               substr(COALESCE(f.verified_transcript, ''), 1, 80) AS tpreview,
               d.slug, d.publication_date, d.publication_date_precision, d.title,
               file.storage_key, file.sha256, file.id AS file_id,
               r.id AS ocr_run_id, r.fingerprint_hash
        FROM bank_fragments f
        JOIN bank_ocr_runs r ON r.id = f.ocr_run_id
        JOIN bank_document_files file ON file.id = r.document_file_id
        JOIN bank_documents d ON d.id = file.document_id
        WHERE d.slug LIKE '%Policy_Rate%' AND f.revision = 2
        ORDER BY f.stable_key
        """
    ).fetchall()
    print("rev2_count", len(rows))
    for r in rows:
        print(dict(r))
    cols = [c[1] for c in con.execute("PRAGMA table_info(bank_fragments)").fetchall()]
    print("fragment_columns_sample", [c for c in cols if "elig" in c or "verif" in c or "qa" in c.lower()])
    # find storage file on disk
    for root_name in (
        "data/bank_materials/verification/storage_run1",
        "data/bank_materials/verification/storage_run2",
        "data/bank_materials/storage",
    ):
        root = Path(root_name)
        print("root", root_name, "exists", root.is_dir())
        if rows and root.is_dir():
            sk = rows[0]["storage_key"]
            cand = root / sk
            print("  try", cand.as_posix(), "exists", cand.is_file())
    con.close()


if __name__ == "__main__":
    main()
