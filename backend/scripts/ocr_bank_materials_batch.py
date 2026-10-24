"""Batch local OCR for bank materials PDFs (stage 2.3).

Processes image-only PDFs page-by-page with Tesseract (rus+eng).
Does not modify originals, call external OCR/AI, or touch backend/DB/API.

Resume: skip a finished page only when source PDF hash, OCR params,
Tesseract version, language-file hashes, and expected outputs all match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "bank_materials" / "raw"
DEFAULT_OUTPUT = ROOT / "data" / "bank_materials" / "ocr"
DEFAULT_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
DEFAULT_TESSDATA = ROOT / "tools" / "tessdata"
LANG = "rus+eng"
PSM = "3"
OCR_TIMEOUT_SEC = 180
SCHEMA_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def tess_version(tesseract: Path) -> str:
    r = subprocess.run(
        [str(tesseract), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    line = (r.stdout or r.stderr or "").splitlines()
    return line[0] if line else "unknown"


def ensure_tessdata_configs(tessdata: Path, tesseract: Path) -> None:
    """tsv/txt configs must exist under tessdata/configs when --tessdata-dir is used."""
    cfg_dst = tessdata / "configs"
    if (cfg_dst / "tsv").is_file() and (cfg_dst / "txt").is_file():
        return
    cfg_src = tesseract.parent / "tessdata" / "configs"
    if not cfg_src.is_dir():
        raise RuntimeError(
            f"missing tesseract configs at {cfg_src}; copy tsv/txt into {cfg_dst}"
        )
    cfg_dst.mkdir(parents=True, exist_ok=True)
    for item in cfg_src.iterdir():
        shutil.copy2(item, cfg_dst / item.name)


def light_clean(raw: str) -> str:
    """Safe whitespace/newline cleanup only. Do not invent numbers/dates/%."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    return cleaned


def parse_tsv(tsv_path: Path) -> list[dict[str, Any]]:
    if not tsv_path.is_file():
        return []
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    words: list[dict[str, Any]] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            continue
        row = dict(zip(header, parts))
        try:
            level = int(row.get("level", "0"))
            conf = float(row.get("conf", "-1"))
        except ValueError:
            continue
        text = row.get("text", "")
        if level != 5 or not text.strip():
            continue
        words.append(
            {
                "text": text,
                "conf": conf,
                "left": int(float(row["left"])),
                "top": int(float(row["top"])),
                "width": int(float(row["width"])),
                "height": int(float(row["height"])),
                "block_num": int(row.get("block_num", 0)),
                "par_num": int(row.get("par_num", 0)),
                "line_num": int(row.get("line_num", 0)),
                "word_num": int(row.get("word_num", 0)),
                "page_num": int(row.get("page_num", 1)),
            }
        )
    return words


def build_fingerprint(
    *,
    pdf_sha256: str,
    tesseract: Path,
    tessdata: Path,
    version_line: str,
) -> dict[str, Any]:
    eng = tessdata / "eng.traineddata"
    rus = tessdata / "rus.traineddata"
    return {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": pdf_sha256,
        "tesseract_binary": str(tesseract),
        "tesseract_version_line": version_line,
        "lang": LANG,
        "psm": int(PSM),
        "preserve_interword_spaces": True,
        "tessdata_dir": str(tessdata),
        "eng_traineddata_sha256": sha256_file(eng),
        "rus_traineddata_sha256": sha256_file(rus),
        "ocr_timeout_sec": OCR_TIMEOUT_SEC,
    }


def expected_page_files(doc_dir: Path, page: int) -> dict[str, Path]:
    return {
        "png": doc_dir / "pages" / f"page_{page:03d}.png",
        "raw": doc_dir / f"page_{page:03d}_raw.txt",
        "cleaned": doc_dir / f"page_{page:03d}_cleaned.txt",
        "tsv": doc_dir / f"page_{page:03d}_ocr.tsv",
        "words": doc_dir / f"page_{page:03d}_words.json",
        "page_meta": doc_dir / f"page_{page:03d}_meta.json",
    }


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def page_is_complete(
    doc_dir: Path,
    page: int,
    fingerprint: dict[str, Any],
) -> tuple[bool, str]:
    files = expected_page_files(doc_dir, page)
    missing = [k for k, p in files.items() if not p.is_file()]
    if missing:
        return False, f"missing_files:{','.join(missing)}"

    meta = load_json(files["page_meta"])
    if not meta:
        return False, "page_meta_unreadable"
    if meta.get("processing_status") != "ok":
        return False, f"processing_status={meta.get('processing_status')}"

    prev_fp = meta.get("fingerprint") or {}
    for key in (
        "source_sha256",
        "tesseract_version_line",
        "lang",
        "psm",
        "preserve_interword_spaces",
        "eng_traineddata_sha256",
        "rus_traineddata_sha256",
    ):
        if prev_fp.get(key) != fingerprint.get(key):
            return False, f"fingerprint_mismatch:{key}"

    raw = files["raw"].read_text(encoding="utf-8")
    if not raw.strip():
        return False, "empty_raw"
    tsv_text = files["tsv"].read_text(encoding="utf-8")
    if not tsv_text.strip() or len(tsv_text.splitlines()) < 2:
        return False, "empty_or_header_only_tsv"
    return True, "ok"


def archive_page_outputs(doc_dir: Path, page: int, reason: str) -> Path | None:
    """Preserve prior outputs when params change; do not destroy verified fragments."""
    files = expected_page_files(doc_dir, page)
    existing = [p for p in files.values() if p.is_file()]
    # also archive embedded raster if present
    emb = doc_dir / "pages" / f"page_{page:03d}_embedded.png"
    if emb.is_file():
        existing.append(emb)
    if not existing:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = doc_dir / "archive" / f"page_{page:03d}_{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    for src in existing:
        shutil.copy2(src, dest / src.name)
    (dest / "archive_reason.txt").write_text(reason + "\n", encoding="utf-8")
    # mark fragments for re-verification if present
    fragments_path = doc_dir / "fragments.json"
    fr = load_json(fragments_path)
    if fr:
        fr["needs_reverification"] = True
        fr["reverification_reason"] = reason
        fr["archived_page_snapshot"] = str(dest.relative_to(doc_dir)).replace("\\", "/")
        fr["updated_at"] = utc_now()
        for frag in fr.get("fragments") or []:
            if isinstance(frag, dict) and frag.get("page") == page:
                frag["verification_status"] = "needs_reverification"
                frag["previous_verification_status"] = frag.get(
                    "verification_status", "unknown"
                )
        fragments_path.write_text(
            json.dumps(fr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return dest


def extract_one_page_image(
    pdf_path: Path, page_index_0: int, doc_dir: Path
) -> dict[str, Any]:
    """Extract a single page raster; close PDF and image promptly (low memory)."""
    page_num = page_index_0 + 1
    reader = PdfReader(str(pdf_path), strict=False)
    try:
        page = reader.pages[page_index_0]
        resources = page["/Resources"].get_object()
        xobjects = resources["/XObject"].get_object()
        image_names = [
            name
            for name in xobjects
            if xobjects[name].get_object().get("/Subtype") == "/Image"
        ]
        if len(image_names) != 1:
            raise RuntimeError(
                f"page {page_num}: expected 1 image XObject, found {len(image_names)}"
            )
        images = getattr(page, "images", None)
        if not images:
            raise RuntimeError(f"page {page_num}: page.images empty")
        pdf_image = images[0]
        img_dir = doc_dir / "pages"
        img_dir.mkdir(parents=True, exist_ok=True)
        ext = pdf_image.name.split(".")[-1] if "." in pdf_image.name else "bin"
        raw_path = img_dir / f"page_{page_num:03d}_embedded.{ext}"
        raw_path.write_bytes(pdf_image.data)
        with Image.open(raw_path) as pil:
            if pil.mode not in ("RGB", "L"):
                pil = pil.convert("RGB")
            width, height, mode = pil.width, pil.height, pil.mode
            png_path = img_dir / f"page_{page_num:03d}.png"
            pil.save(png_path, format="PNG")
        return {
            "page": page_num,
            "embedded_name": str(image_names[0]),
            "embedded_path": str(raw_path.relative_to(doc_dir)).replace("\\", "/"),
            "png_path": str(png_path.relative_to(doc_dir)).replace("\\", "/"),
            "width": width,
            "height": height,
            "mode": mode,
            "upscaled": False,
        }
    finally:
        # help GC on large PDFs
        del reader


def run_tesseract_once(
    *,
    tesseract: Path,
    tessdata: Path,
    png_path: Path,
    base_out: Path,
    psm: str,
) -> dict[str, Any]:
    def _run(fmt: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(tesseract),
                str(png_path),
                str(base_out),
                "-l",
                LANG,
                "--tessdata-dir",
                str(tessdata),
                "--psm",
                psm,
                "-c",
                "preserve_interword_spaces=1",
                fmt,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=OCR_TIMEOUT_SEC,
        )

    warnings: list[str] = []
    try:
        r1 = _run("txt")
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "warnings": [f"txt_timeout>{OCR_TIMEOUT_SEC}s psm={psm}"],
            "raw_text": "",
            "words": [],
            "tsv_path": Path(str(base_out) + ".tsv"),
            "txt_path": Path(str(base_out) + ".txt"),
            "word_count": 0,
            "mean_confidence": None,
            "median_confidence": None,
            "psm_used": int(psm),
        }
    try:
        r2 = _run("tsv")
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "warnings": [f"tsv_timeout>{OCR_TIMEOUT_SEC}s psm={psm}"],
            "raw_text": "",
            "words": [],
            "tsv_path": Path(str(base_out) + ".tsv"),
            "txt_path": Path(str(base_out) + ".txt"),
            "word_count": 0,
            "mean_confidence": None,
            "median_confidence": None,
            "psm_used": int(psm),
        }

    if r1.returncode != 0:
        warnings.append(f"txt_rc={r1.returncode} psm={psm} stderr={(r1.stderr or '')[-500:]}")
    if r2.returncode != 0:
        warnings.append(f"tsv_rc={r2.returncode} psm={psm} stderr={(r2.stderr or '')[-500:]}")

    txt_path = Path(str(base_out) + ".txt")
    tsv_path = Path(str(base_out) + ".tsv")
    raw_text = txt_path.read_text(encoding="utf-8") if txt_path.is_file() else ""
    words = parse_tsv(tsv_path) if tsv_path.is_file() else []
    confs = [w["conf"] for w in words if w["conf"] >= 0]

    ok = (
        r1.returncode == 0
        and r2.returncode == 0
        and txt_path.is_file()
        and tsv_path.is_file()
        and bool(raw_text.strip())
        and len(tsv_path.read_text(encoding="utf-8").splitlines()) >= 2
        and len(words) > 0
    )
    return {
        "status": "ok" if ok else "failed",
        "warnings": warnings,
        "raw_text": raw_text,
        "words": words,
        "tsv_path": tsv_path,
        "txt_path": txt_path,
        "word_count": len(words),
        "mean_confidence": (sum(confs) / len(confs)) if confs else None,
        "median_confidence": (sorted(confs)[len(confs) // 2] if confs else None),
        "stderr_txt": (r1.stderr or "").strip()[-1000:],
        "stderr_tsv": (r2.stderr or "").strip()[-1000:],
        "psm_used": int(psm),
    }


def run_tesseract(
    *,
    tesseract: Path,
    tessdata: Path,
    png_path: Path,
    base_out: Path,
) -> dict[str, Any]:
    """Primary PSM 3; on empty/failed sparse pages try PSM 6 then 11."""
    attempts: list[dict[str, Any]] = []
    for psm in (PSM, "6", "11"):
        result = run_tesseract_once(
            tesseract=tesseract,
            tessdata=tessdata,
            png_path=png_path,
            base_out=base_out,
            psm=psm,
        )
        attempts.append({"psm": int(psm), "status": result["status"], "words": result["word_count"]})
        if result["status"] == "ok":
            if psm != PSM:
                result["warnings"] = list(result.get("warnings") or []) + [
                    f"primary_psm_{PSM}_empty_or_failed; recovered_with_psm_{psm}"
                ]
            result["psm_attempts"] = attempts
            return result
    result["psm_attempts"] = attempts
    result["warnings"] = list(result.get("warnings") or []) + [
        "all_psm_attempts_failed_or_empty"
    ]
    return result


def blank_visual_fields() -> dict[str, Any]:
    return {
        "visual_verification_status": "unverified",
        "content_regions": [
            {
                "type": "unverified",
                "status": "unverified",
                "notes": "Not visually checked in this OCR run.",
            }
        ],
        "visual_checks": {
            "title": {"value": None, "status": "unknown"},
            "publication_date": {"value": None, "status": "unknown"},
            "period_covered": {"value": None, "status": "unknown"},
            "main_takeaway": {"value": None, "status": "unknown"},
        },
        "note": (
            "OCR confidence is technical only and does not confirm facts. "
            "Publication date must come from page content, not PDF export metadata."
        ),
    }


def process_page(
    *,
    pdf_path: Path,
    doc_dir: Path,
    page_index_0: int,
    page_count: int,
    fingerprint: dict[str, Any],
    tesseract: Path,
    tessdata: Path,
    force: bool,
) -> dict[str, Any]:
    page = page_index_0 + 1
    doc_name = pdf_path.name
    print(
        f"[{doc_name}] page {page}/{page_count} …",
        flush=True,
    )

    complete, reason = page_is_complete(doc_dir, page, fingerprint)
    if complete and not force:
        meta = load_json(expected_page_files(doc_dir, page)["page_meta"]) or {}
        print(
            f"[{doc_name}] page {page}/{page_count} SKIP (resume match)",
            flush=True,
        )
        meta["skipped_resume"] = True
        return meta

    if expected_page_files(doc_dir, page)["page_meta"].is_file() and not complete:
        archive_page_outputs(doc_dir, page, f"reprocess:{reason}")

    try:
        image_meta = extract_one_page_image(pdf_path, page_index_0, doc_dir)
    except Exception as exc:  # noqa: BLE001 — record in manifest
        err = {
            "page": page,
            "processing_status": "failed",
            "error": f"extract_failed: {exc}",
            "fingerprint": fingerprint,
            "processed_at": utc_now(),
            **blank_visual_fields(),
        }
        expected_page_files(doc_dir, page)["page_meta"].write_text(
            json.dumps(err, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"[{doc_name}] page {page}/{page_count} FAIL extract: {exc}",
            flush=True,
        )
        return err

    png = doc_dir / image_meta["png_path"]
    base = doc_dir / f"page_{page:03d}_ocr"
    ocr = run_tesseract(
        tesseract=tesseract, tessdata=tessdata, png_path=png, base_out=base
    )
    files = expected_page_files(doc_dir, page)

    cleaned = light_clean(ocr["raw_text"]) if ocr["raw_text"] else ""
    files["raw"].write_text(ocr["raw_text"], encoding="utf-8")
    files["cleaned"].write_text(cleaned, encoding="utf-8")
    files["words"].write_text(
        json.dumps(ocr["words"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # normalize tsv name: tesseract writes page_NNN_ocr.tsv already via base_out
    # raw txt from tesseract may sit as page_NNN_ocr.txt — keep alongside raw copy
    status = ocr["status"]
    page_meta: dict[str, Any] = {
        "page": page,
        "processing_status": status,
        "warnings": ocr.get("warnings") or [],
        "fingerprint": fingerprint,
        "processed_at": utc_now(),
        "image": image_meta,
        "ocr": {
            "raw_txt": files["raw"].name,
            "cleaned_txt": files["cleaned"].name,
            "tsv": files["tsv"].name,
            "words_json": files["words"].name,
            "tesseract_txt": Path(str(base) + ".txt").name,
            "word_count": ocr["word_count"],
            "mean_confidence": ocr["mean_confidence"],
            "median_confidence": ocr["median_confidence"],
            "raw_char_count": len(ocr["raw_text"]),
            "cleaned_char_count": len(cleaned),
            "cyrillic_char_count": sum(
                1 for ch in cleaned if ("А" <= ch <= "я") or ch in "ёЁ"
            ),
            "psm_used": ocr.get("psm_used"),
            "psm_attempts": ocr.get("psm_attempts"),
            "confidence_note": (
                "Technical OCR confidence only; not fact verification."
            ),
        },
        "preview": cleaned[:800],
        **blank_visual_fields(),
    }
    if status != "ok":
        page_meta["error"] = "ocr_failed_or_empty"
    files["page_meta"].write_text(
        json.dumps(page_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[{doc_name}] page {page}/{page_count} "
        f"{'OK' if status == 'ok' else 'FAIL'} "
        f"words={ocr['word_count']} mean_conf={ocr['mean_confidence']}",
        flush=True,
    )
    return page_meta


def merge_visual_from_existing(
    new_page: dict[str, Any], old_page: dict[str, Any] | None
) -> dict[str, Any]:
    """Preserve prior visual QA when page was skipped or re-OCR kept same fingerprint."""
    if not old_page:
        return new_page
    for key in (
        "visual_verification_status",
        "content_regions",
        "visual_checks",
        "visual_notes",
    ):
        if key in old_page and old_page[key] is not None:
            # only keep if new page is resume-skip or still unverified skeleton
            if new_page.get("skipped_resume") or new_page.get(
                "visual_verification_status"
            ) in (None, "unverified"):
                if old_page.get("visual_verification_status") not in (
                    None,
                    "unverified",
                ):
                    new_page[key] = old_page[key]
                elif key not in new_page or new_page.get(key) is None:
                    new_page[key] = old_page[key]
    return new_page


def write_doc_manifest(
    *,
    doc_dir: Path,
    pdf_path: Path,
    pdf_sha256: str,
    fingerprint: dict[str, Any],
    pages: list[dict[str, Any]],
    version_line: str,
    tesseract: Path,
    tessdata: Path,
) -> dict[str, Any]:
    ok_pages = [p["page"] for p in pages if p.get("processing_status") == "ok"]
    failed_pages = [p["page"] for p in pages if p.get("processing_status") != "ok"]
    verified_pages = [
        p["page"]
        for p in pages
        if p.get("visual_verification_status")
        in ("verified_partial", "verified_spot_check", "verified")
    ]
    unverified_pages = [
        p["page"]
        for p in pages
        if p.get("visual_verification_status") in (None, "unverified")
    ]

    processing_complete = len(failed_pages) == 0 and len(pages) > 0
    # Never mark whole document verified from title+one paragraph alone
    doc_visual = "unverified"
    if verified_pages and unverified_pages:
        doc_visual = "partial_spot_check"
    elif verified_pages and not unverified_pages:
        # still not full doc verification unless every region verified — keep cautious
        doc_visual = "partial_spot_check"

    existing = load_json(doc_dir / "manifest.json") or {}
    identity = existing.get("document_identity") or {
        "confirmed_title": None,
        "confirmed_title_status": "unknown",
        "confirmed_publication_date": None,
        "confirmed_publication_date_status": "unknown",
        "period_covered": None,
        "period_covered_status": "unknown",
        "topics": [],
        "topics_status": "unknown",
        "staleness_note": None,
    }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source_pdf": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
        "source_filename": pdf_path.name,
        "source_sha256": pdf_sha256,
        "page_count": len(pages),
        "processing_status": "complete" if processing_complete else "incomplete",
        "document_visual_status": doc_visual,
        "pages_ok": ok_pages,
        "pages_failed": failed_pages,
        "pages_visually_checked": verified_pages,
        "pages_visually_unverified": unverified_pages,
        "fingerprint": fingerprint,
        "tesseract": {
            "binary": str(tesseract),
            "version_line": version_line,
            "lang": LANG,
            "tessdata_dir": str(tessdata.relative_to(ROOT)).replace("\\", "/"),
            "psm": int(PSM),
            "preserve_interword_spaces": True,
            "timeout_sec": OCR_TIMEOUT_SEC,
        },
        "document_identity": identity,
        "citation_limits": existing.get("citation_limits")
        or {
            "ocr_confidence_is_not_fact_confirmation": True,
            "tables_and_charts_not_trusted_from_labels_alone": True,
            "unverified_regions_remain_unverified": True,
            "pdf_export_date_is_not_publication_date": True,
            "filename_is_hint_only": True,
            "do_not_treat_spot_check_as_full_document_verification": True,
        },
        "pages": pages,
    }
    (doc_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    combined: list[str] = []
    for pr in pages:
        combined.append(f"\n\n===== PDF_PAGE {pr['page']} =====\n\n")
        cleaned_name = (pr.get("ocr") or {}).get("cleaned_txt")
        if cleaned_name and (doc_dir / cleaned_name).is_file():
            combined.append((doc_dir / cleaned_name).read_text(encoding="utf-8"))
        else:
            combined.append("[OCR missing or failed]\n")
    (doc_dir / "all_pages_cleaned_bounded.txt").write_text(
        "".join(combined), encoding="utf-8"
    )
    return manifest


def process_document(
    *,
    pdf_path: Path,
    output_dir: Path,
    tesseract: Path,
    tessdata: Path,
    version_line: str,
    force: bool,
) -> dict[str, Any]:
    doc_dir = output_dir / pdf_path.stem
    doc_dir.mkdir(parents=True, exist_ok=True)
    pdf_sha256 = sha256_file(pdf_path)
    fingerprint = build_fingerprint(
        pdf_sha256=pdf_sha256,
        tesseract=tesseract,
        tessdata=tessdata,
        version_line=version_line,
    )

    reader = PdfReader(str(pdf_path), strict=False)
    page_count = len(reader.pages)
    del reader

    print(
        f"=== {pdf_path.name} pages={page_count} sha256={pdf_sha256[:12]}… ===",
        flush=True,
    )

    old_manifest = load_json(doc_dir / "manifest.json") or {}
    old_by_page = {
        p["page"]: p for p in (old_manifest.get("pages") or []) if "page" in p
    }

    pages: list[dict[str, Any]] = []
    for i in range(page_count):
        page_meta = process_page(
            pdf_path=pdf_path,
            doc_dir=doc_dir,
            page_index_0=i,
            page_count=page_count,
            fingerprint=fingerprint,
            tesseract=tesseract,
            tessdata=tessdata,
            force=force,
        )
        page_meta = merge_visual_from_existing(page_meta, old_by_page.get(i + 1))
        # persist merged visual back to page_meta file
        files = expected_page_files(doc_dir, i + 1)
        files["page_meta"].write_text(
            json.dumps(page_meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        pages.append(page_meta)

    return write_doc_manifest(
        doc_dir=doc_dir,
        pdf_path=pdf_path,
        pdf_sha256=pdf_sha256,
        fingerprint=fingerprint,
        pages=pages,
        version_line=version_line,
        tesseract=tesseract,
        tessdata=tessdata,
    )


def migrate_policy_rate_pilot(
    *,
    output_dir: Path,
    tesseract: Path,
    tessdata: Path,
    version_line: str,
) -> None:
    """Upgrade pilot Policy Rate artifacts to schema v2 without re-OCR."""
    stem = "ALFA-Macro_Insights-Policy_Rate_11Sep"
    doc_dir = output_dir / stem
    pdf_path = DEFAULT_INPUT / f"{stem}.pdf"
    if not doc_dir.is_dir() or not pdf_path.is_file():
        return
    old = load_json(doc_dir / "manifest.json")
    if not old:
        return
    pdf_sha256 = sha256_file(pdf_path)
    fingerprint = build_fingerprint(
        pdf_sha256=pdf_sha256,
        tesseract=tesseract,
        tessdata=tessdata,
        version_line=version_line,
    )
    pages_out: list[dict[str, Any]] = []
    for p in old.get("pages") or []:
        page = int(p["page"])
        files = expected_page_files(doc_dir, page)
        # ensure page_meta exists
        if not files["page_meta"].is_file():
            status = "ok" if p.get("status") == "ok" else "failed"
            # validate outputs exist
            if status == "ok":
                ok, reason = True, "migrated"
                for key in ("png", "raw", "cleaned", "tsv", "words"):
                    if not files[key].is_file():
                        ok, reason = False, f"missing_{key}"
                        break
                if ok:
                    raw = files["raw"].read_text(encoding="utf-8")
                    tsv = files["tsv"].read_text(encoding="utf-8")
                    if not raw.strip() or len(tsv.splitlines()) < 2:
                        ok, reason = False, "empty_ocr"
                status = "ok" if ok else "failed"
            image = p.get("image") or {}
            # normalize paths
            if "png_path" in image:
                image["png_path"] = str(image["png_path"]).replace("\\", "/")
            if "embedded_path" in image:
                image["embedded_path"] = str(image["embedded_path"]).replace("\\", "/")
            visual = blank_visual_fields()
            if page == 1:
                visual = {
                    "visual_verification_status": "verified_spot_check",
                    "content_regions": [
                        {
                            "type": "prose",
                            "status": "verified_ok",
                            "notes": "Title, date, main takeaways spot-checked vs page image (pilot 2.2).",
                        },
                        {
                            "type": "contacts_disclaimer",
                            "status": "unverified",
                            "notes": "Author emails in header not fully region-mapped.",
                        },
                    ],
                    "visual_checks": {
                        "title": {
                            "value": "Ключевая ставка ЦБ РФ",
                            "status": "confirmed",
                        },
                        "publication_date": {
                            "value": "11 сентября 2026 г.",
                            "status": "confirmed",
                            "note": "From page content; not PDF export metadata.",
                        },
                        "period_covered": {
                            "value": "решение ЦБ на дату материала; прогнозы до конца 2026–2027",
                            "status": "confirmed",
                        },
                        "main_takeaway": {
                            "value": "ЦБ оставил ставку 14,0%; риторика жёстче; банк ждёт 14,0% до конца 2026 и 12,0% к концу 2027",
                            "status": "confirmed",
                        },
                    },
                    "note": "Spot-check only; not full-page/document verification.",
                }
            elif page in (2, 3):
                visual = {
                    "visual_verification_status": "verified_spot_check",
                    "content_regions": [
                        {
                            "type": "table" if page == 2 else "chart",
                            "status": "verified_unreliable",
                            "notes": (
                                "Labels partially readable; table/chart numeric extraction "
                                "NOT confirmed. Do not cite numeric series from OCR alone."
                            ),
                        },
                        {
                            "type": "prose",
                            "status": "unverified",
                            "notes": "Captions only partially checked.",
                        },
                    ],
                    "visual_checks": {
                        "title": {"value": None, "status": "unknown"},
                        "publication_date": {"value": None, "status": "unknown"},
                        "period_covered": {"value": None, "status": "unknown"},
                        "main_takeaway": {
                            "value": "Tables/charts present; OCR not trusted for values",
                            "status": "confirmed",
                        },
                    },
                    "note": "Presence of chart/table captions ≠ correct extraction.",
                }
            else:
                visual = {
                    "visual_verification_status": "verified_spot_check",
                    "content_regions": [
                        {
                            "type": "contacts_disclaimer",
                            "status": "verified_ok",
                            "notes": "Contacts/disclaimer prose; OCR quality good in pilot.",
                        }
                    ],
                    "visual_checks": {
                        "title": {"value": None, "status": "unknown"},
                        "publication_date": {"value": None, "status": "unknown"},
                        "period_covered": {"value": None, "status": "unknown"},
                        "main_takeaway": {
                            "value": "Contacts and disclaimer page",
                            "status": "confirmed",
                        },
                    },
                    "note": "Spot-check; not a full legal review of disclaimer.",
                }
            meta = {
                "page": page,
                "processing_status": status,
                "warnings": p.get("warnings") or [],
                "fingerprint": fingerprint,
                "processed_at": old.get("generated_at") or utc_now(),
                "migrated_from_pilot": True,
                "image": image,
                "ocr": p.get("ocr") or {},
                "preview": p.get("preview"),
                **visual,
            }
            if status != "ok":
                meta["error"] = "migration_incomplete_missing_or_empty_outputs"
            files["page_meta"].write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            pages_out.append(meta)
        else:
            pages_out.append(load_json(files["page_meta"]) or p)

    manifest = write_doc_manifest(
        doc_dir=doc_dir,
        pdf_path=pdf_path,
        pdf_sha256=pdf_sha256,
        fingerprint=fingerprint,
        pages=pages_out,
        version_line=version_line,
        tesseract=tesseract,
        tessdata=tessdata,
    )
    # document identity from pilot QA
    manifest["document_identity"] = {
        "confirmed_title": "Ключевая ставка ЦБ РФ",
        "confirmed_title_status": "confirmed",
        "confirmed_publication_date": "2026-09-11",
        "confirmed_publication_date_status": "confirmed",
        "confirmed_publication_date_display": "11 сентября 2026 г.",
        "period_covered": "решение ЦБ на дату note; прогнозы банка до конца 2026 и 2027",
        "period_covered_status": "confirmed",
        "topics": [
            "ключевая ставка ЦБ РФ",
            "монетарная политика",
            "прогноз ставки банка",
        ],
        "topics_status": "confirmed",
        "staleness_note": None,
    }
    manifest["document_visual_status"] = "partial_spot_check"
    (doc_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Fixed fragment format (stage 2.3)
    fragments = {
        "schema_version": SCHEMA_VERSION,
        "document": stem,
        "source_pdf": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
        "needs_reverification": False,
        "updated_at": utc_now(),
        "fragments": [
            {
                "id": "policy_rate_cb_decision",
                "kind": "exact_quote",
                "content_type": "fact",
                "source_document": stem,
                "source_role": "bank_material_reporting_cb_decision",
                "page": 1,
                "regions": [
                    {
                        "bbox": {
                            "left": 109,
                            "top": 411,
                            "width": 1155,
                            "height": 47,
                        },
                        "note": "Primary line containing the decision sentence.",
                    }
                ],
                "ocr_text": (
                    "ЦБ РФ принял решение оставить ставку неизменной на уровне 14,0%"
                ),
                "exact_quote": (
                    "ЦБ РФ принял решение оставить ставку неизменной на уровне 14,0%"
                ),
                "summary": None,
                "verification_status": "verified",
                "notes": (
                    "Fact about CBR decision as stated in this bank note. "
                    "Source is this bank material, not an opened CBR primary link."
                ),
            },
            {
                "id": "policy_rate_rhetoric",
                "kind": "exact_quote",
                "content_type": "interpretation",
                "source_document": stem,
                "page": 1,
                "regions": [
                    {
                        "bbox": {
                            "left": 109,
                            "top": 355,
                            "width": 834,
                            "height": 78,
                        }
                    }
                ],
                "ocr_text": "Ставка без изменения на 14,0%, риторика cTana жестче",
                "exact_quote": "Ставка без изменения на 14,0%, риторика стала жестче",
                "ocr_correction": {
                    "from": "cTana",
                    "to": "стала",
                    "basis": "visual_check_of_page_image",
                },
                "summary": None,
                "verification_status": "verified",
                "notes": "Bank interpretation of CBR rhetoric; OCR typo corrected after visual QA.",
            },
            {
                "id": "policy_rate_bank_forecast",
                "kind": "exact_quote",
                "content_type": "forecast",
                "source_document": stem,
                "page": 1,
                "regions": [
                    {
                        "bbox": {
                            "left": 153,
                            "top": 1610,
                            "width": 1037,
                            "height": 20,
                        },
                        "note": "Anchor region; full forecast spans multiple lines — see ocr_text.",
                    }
                ],
                "ocr_text": (
                    "Мы ожидаем сохранения паузы на заседании 23 октября… "
                    "теперь мы ожидаем ее сохранения на текущем значении 14,0% до конца года… "
                    "прогноз по ставке на конец 2027 г. остаётся на уровне 12,0%"
                ),
                "exact_quote": (
                    "Мы ожидаем сохранения паузы на заседании 23 октября… "
                    "теперь мы ожидаем ее сохранения на текущем значении 14,0% до конца года… "
                    "прогноз по ставке на конец 2027 г. остаётся на уровне 12,0%"
                ),
                "summary": None,
                "verification_status": "verified",
                "notes": "Alfa-Bank forecast/expectation, not a CBR decision.",
            },
            {
                "id": "policy_rate_credit_monitoring",
                "kind": "summary",
                "content_type": "interpretation",
                "source_document": stem,
                "page": 1,
                "regions": [
                    {
                        "bbox": {
                            "left": 109,
                            "top": 1425,
                            "width": 1156,
                            "height": 41,
                        }
                    }
                ],
                "ocr_text": None,
                "exact_quote": None,
                "summary": (
                    "Банк указывает на мониторинг спроса через динамику корпоративного "
                    "кредитования и параметры бюджета; корпоративное кредитование идёт "
                    "быстрее прогнозов ЦБ."
                ),
                "verification_status": "verified",
                "notes": (
                    "Explicitly a summary, not an exact quote. Does not yield client loan terms."
                ),
            },
        ],
    }
    (doc_dir / "fragments.json").write_text(
        json.dumps(fragments, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"migrated pilot → schema v2: {doc_dir}", flush=True)


def write_corpus_manifest(output_dir: Path, docs: list[dict[str, Any]]) -> dict[str, Any]:
    corpus = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "output_dir": str(output_dir.relative_to(ROOT)).replace("\\", "/"),
        "document_count": len(docs),
        "documents": [],
        "global_limits": {
            "no_rag_yet": True,
            "no_db_import_yet": True,
            "no_external_ocr_ai": True,
            "ocr_confidence_is_not_fact_confirmation": True,
            "spot_check_is_not_full_document_verification": True,
            "tables_charts_untrusted_without_cell_qa": True,
            "old_materials_are_not_current_bank_stance": True,
        },
    }
    for m in docs:
        identity = m.get("document_identity") or {}
        corpus["documents"].append(
            {
                "source_filename": m.get("source_filename"),
                "source_pdf": m.get("source_pdf"),
                "source_sha256": m.get("source_sha256"),
                "page_count": m.get("page_count"),
                "processing_status": m.get("processing_status"),
                "document_visual_status": m.get("document_visual_status"),
                "pages_ok": m.get("pages_ok"),
                "pages_failed": m.get("pages_failed"),
                "pages_visually_checked": m.get("pages_visually_checked"),
                "pages_visually_unverified": m.get("pages_visually_unverified"),
                "confirmed_title": identity.get("confirmed_title"),
                "confirmed_title_status": identity.get("confirmed_title_status", "unknown"),
                "confirmed_publication_date": identity.get("confirmed_publication_date"),
                "confirmed_publication_date_status": identity.get(
                    "confirmed_publication_date_status", "unknown"
                ),
                "period_covered": identity.get("period_covered"),
                "period_covered_status": identity.get("period_covered_status", "unknown"),
                "topics": identity.get("topics") or [],
                "topics_status": identity.get("topics_status", "unknown"),
                "staleness_note": identity.get("staleness_note"),
                "ocr_dir": str(
                    (output_dir / Path(m["source_pdf"]).stem).relative_to(ROOT)
                ).replace("\\", "/"),
            }
        )
    path = output_dir / "_corpus_manifest.json"
    path.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}", flush=True)
    return corpus


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch local OCR for bank materials")
    p.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--tesseract", type=Path, default=DEFAULT_TESSERACT)
    p.add_argument("--tessdata-dir", type=Path, default=DEFAULT_TESSDATA)
    p.add_argument(
        "--only",
        action="append",
        default=[],
        help="Process only PDFs whose filename contains this substring (repeatable)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-OCR even when resume fingerprint matches",
    )
    p.add_argument(
        "--migrate-pilot-only",
        action="store_true",
        help="Only migrate Policy Rate pilot to schema v2 (no OCR)",
    )
    p.add_argument(
        "--corpus-only",
        action="store_true",
        help="Rebuild corpus manifest from existing doc manifests",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir
    tesseract: Path = args.tesseract
    tessdata: Path = args.tessdata_dir

    if not tesseract.is_file():
        print(f"missing tesseract: {tesseract}", file=sys.stderr)
        return 1
    if not (tessdata / "rus.traineddata").is_file() or not (
        tessdata / "eng.traineddata"
    ).is_file():
        print(f"missing rus/eng in {tessdata}", file=sys.stderr)
        return 1

    try:
        ensure_tessdata_configs(tessdata, tesseract)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    version_line = tess_version(tesseract)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.migrate_pilot_only:
        migrate_policy_rate_pilot(
            output_dir=output_dir,
            tesseract=tesseract,
            tessdata=tessdata,
            version_line=version_line,
        )
        return 0

    if args.corpus_only:
        docs = []
        for man in sorted(output_dir.glob("*/manifest.json")):
            data = load_json(man)
            if data:
                docs.append(data)
        write_corpus_manifest(output_dir, docs)
        return 0

    # Always migrate pilot first so Policy Rate is schema-compatible and skippable
    migrate_policy_rate_pilot(
        output_dir=output_dir,
        tesseract=tesseract,
        tessdata=tessdata,
        version_line=version_line,
    )

    pdfs = sorted(input_dir.glob("*.pdf"))
    if args.only:
        pdfs = [
            p
            for p in pdfs
            if any(token.lower() in p.name.lower() for token in args.only)
        ]
    if not pdfs:
        print(f"no PDFs in {input_dir}", file=sys.stderr)
        return 1

    manifests: list[dict[str, Any]] = []
    for pdf in pdfs:
        try:
            man = process_document(
                pdf_path=pdf,
                output_dir=output_dir,
                tesseract=tesseract,
                tessdata=tessdata,
                version_line=version_line,
                force=args.force,
            )
            manifests.append(man)
        except Exception as exc:  # noqa: BLE001
            print(f"DOCUMENT FAIL {pdf.name}: {exc}", file=sys.stderr)
            traceback.print_exc()
            manifests.append(
                {
                    "source_filename": pdf.name,
                    "source_pdf": str(pdf.relative_to(ROOT)).replace("\\", "/"),
                    "source_sha256": sha256_file(pdf) if pdf.is_file() else None,
                    "page_count": None,
                    "processing_status": "incomplete",
                    "document_visual_status": "unverified",
                    "pages_ok": [],
                    "pages_failed": [],
                    "pages_visually_checked": [],
                    "pages_visually_unverified": [],
                    "document_identity": {"error": str(exc)},
                    "error": str(exc),
                }
            )

    write_corpus_manifest(output_dir, manifests)
    incomplete = [
        m["source_filename"]
        for m in manifests
        if m.get("processing_status") != "complete"
    ]
    if incomplete:
        print(f"incomplete documents: {incomplete}", flush=True)
        return 2
    print(f"all {len(manifests)} documents processing_status=complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
