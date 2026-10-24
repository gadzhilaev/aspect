"""One-shot repair: restore durable PDF/OCR files for a stand whose bank load
deleted staging under storage_root (pre-fix). Does not touch the DB schema.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    stand = Path(sys.argv[1] if len(sys.argv) > 1 else "data/competition_stand/jury_63b")
    pdf_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "data/bank_materials/raw")
    ocr_dir = Path(sys.argv[3] if len(sys.argv) > 3 else "data/bank_materials/ocr")
    storage = stand / "storage"
    db = stand / "stand.db"
    conn = sqlite3.connect(db)
    rows = list(conn.execute("select original_filename, storage_key from bank_document_files"))
    n = 0
    for filename, key in rows:
        if not key:
            continue
        dest = storage / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = pdf_dir / filename
        if not src.is_file():
            print(f"missing pdf {src}")
            continue
        shutil.copy2(src, dest)
        n += 1
        print(f"pdf -> {key}")
        # Also restore OCR dir next to pdf staging prefix if key looks like stage/pdf/name
        # e.g. bank_import_stage_xxx/pdf/Foo.pdf → bank_import_stage_xxx/ocr/Foo/
        parts = Path(key).parts
        if len(parts) >= 3 and parts[1] == "pdf":
            stage = parts[0]
            slug = Path(filename).stem
            # OCR slug folders use full document dir names
            src_ocr = ocr_dir / slug
            # Try exact slug match among OCR dirs
            if not src_ocr.is_dir():
                matches = [p for p in ocr_dir.iterdir() if p.is_dir() and p.name.startswith(slug[:20])]
                # Prefer filename stem matching pdf name without .pdf
                for cand in ocr_dir.iterdir():
                    if cand.is_dir() and (cand / "manifest.json").is_file():
                        man = (cand / "manifest.json").read_text(encoding="utf-8")
                        if filename in man:
                            src_ocr = cand
                            break
            dest_ocr = storage / stage / "ocr" / src_ocr.name
            if src_ocr.is_dir() and not dest_ocr.exists():
                shutil.copytree(src_ocr, dest_ocr)
                print(f"ocr -> {dest_ocr.relative_to(storage).as_posix()}")
    conn.close()
    print(f"restored_pdfs={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
