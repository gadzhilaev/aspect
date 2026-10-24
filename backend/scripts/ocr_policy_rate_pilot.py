"""Local OCR pilot for ALFA-Macro_Insights-Policy_Rate_11Sep.pdf (stage 2.2).

Uses project-local tessdata (eng+rus) and Tesseract binary by absolute path.
Does not modify the original PDF or send data to external OCR/AI services.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data" / "bank_materials" / "raw" / "ALFA-Macro_Insights-Policy_Rate_11Sep.pdf"
OUT = ROOT / "data" / "bank_materials" / "ocr" / "ALFA-Macro_Insights-Policy_Rate_11Sep"
TESSDATA = ROOT / "tools" / "tessdata"
TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
LANG = "rus+eng"
# tsv/txt configs live under tessdata/configs (must exist when using --tessdata-dir)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def extract_page_images(pdf_path: Path, out_dir: Path) -> list[dict]:
    """Extract embedded page rasters (one Image XObject per page)."""
    reader = PdfReader(str(pdf_path), strict=False)
    pages_meta: list[dict] = []
    img_dir = out_dir / "pages"
    img_dir.mkdir(parents=True, exist_ok=True)

    for i, page in enumerate(reader.pages, start=1):
        resources = page["/Resources"].get_object()
        xobjects = resources["/XObject"].get_object()
        image_names = [
            name
            for name in xobjects
            if xobjects[name].get_object().get("/Subtype") == "/Image"
        ]
        if len(image_names) != 1:
            raise RuntimeError(
                f"page {i}: expected 1 image XObject, found {len(image_names)}"
            )
        name = image_names[0]
        # pypdf ImageFile abstraction
        pdf_image = page.images[0] if getattr(page, "images", None) else None
        if pdf_image is None:
            # Fallback via xobject
            from pypdf.generic import EncodedStreamObject

            raise RuntimeError(f"page {i}: page.images empty")

        raw_path = img_dir / f"page_{i:03d}_embedded.{pdf_image.name.split('.')[-1]}"
        # page.images[0].data / .image
        data = pdf_image.data
        raw_path.write_bytes(data)

        # Normalize to PNG via Pillow for OCR (preserve orientation, no upscale)
        pil = Image.open(raw_path)
        if pil.mode not in ("RGB", "L"):
            pil = pil.convert("RGB")
        png_path = img_dir / f"page_{i:03d}.png"
        pil.save(png_path, format="PNG")
        pages_meta.append(
            {
                "page": i,
                "embedded_name": name,
                "embedded_path": str(raw_path.relative_to(out_dir)),
                "png_path": str(png_path.relative_to(out_dir)),
                "width": pil.width,
                "height": pil.height,
                "mode": pil.mode,
                "upscaled": False,
            }
        )
        print(
            f"extracted page {i}: {pil.width}x{pil.height} mode={pil.mode}",
            flush=True,
        )
    return pages_meta


def run_tesseract(png_path: Path, base_out: Path) -> dict:
    """Run tesseract with TSV + TXT; keep raw outputs."""

    def _run(fmt: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(TESSERACT),
                str(png_path),
                str(base_out),
                "-l",
                LANG,
                "--tessdata-dir",
                str(TESSDATA),
                "--psm",
                "3",
                "-c",
                "preserve_interword_spaces=1",
                fmt,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    r1 = _run("txt")
    r2 = _run("tsv")
    warnings: list[str] = []
    if r1.returncode != 0:
        warnings.append(f"txt_rc={r1.returncode} stderr={r1.stderr[-500:]}")
    if r2.returncode != 0:
        warnings.append(f"tsv_rc={r2.returncode} stderr={r2.stderr[-500:]}")

    txt_path = Path(str(base_out) + ".txt")
    tsv_path = Path(str(base_out) + ".tsv")
    raw_text = txt_path.read_text(encoding="utf-8") if txt_path.is_file() else ""

    words = parse_tsv(tsv_path) if tsv_path.is_file() else []
    confs = [w["conf"] for w in words if w["conf"] >= 0]
    return {
        "raw_txt_path": str(txt_path.name),
        "tsv_path": str(tsv_path.name),
        "raw_text": raw_text,
        "word_count": len(words),
        "mean_confidence": (sum(confs) / len(confs)) if confs else None,
        "median_confidence": (sorted(confs)[len(confs) // 2] if confs else None),
        "words": words,
        "stderr_txt": r1.stderr.strip()[-1000:] if r1.stderr else "",
        "stderr_tsv": r2.stderr.strip()[-1000:] if r2.stderr else "",
        "warnings": warnings,
        "status": "ok" if r1.returncode == 0 and raw_text.strip() else "failed",
    }


def parse_tsv(tsv_path: Path) -> list[dict]:
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    words: list[dict] = []
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


def light_clean(raw: str) -> str:
    """Minimal cleanup: normalize newlines/spaces only. Do not invent numbers."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # collapse horizontal whitespace but keep paragraph breaks
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)
    # collapse 3+ blank lines to 2
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    return cleaned


def tess_version() -> str:
    r = subprocess.run(
        [str(TESSERACT), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (r.stdout or r.stderr).splitlines()[0] if (r.stdout or r.stderr) else "unknown"


def main() -> int:
    if not PDF.is_file():
        print(f"missing PDF: {PDF}", file=sys.stderr)
        return 1
    if not TESSERACT.is_file():
        print(f"missing tesseract: {TESSERACT}", file=sys.stderr)
        return 1
    if not (TESSDATA / "rus.traineddata").is_file() or not (TESSDATA / "eng.traineddata").is_file():
        print(f"missing rus/eng in {TESSDATA}", file=sys.stderr)
        return 1
    # tsv/txt are configfiles under tessdata/configs when --tessdata-dir is used
    cfg_src = Path(r"C:\Program Files\Tesseract-OCR\tessdata\configs")
    cfg_dst = TESSDATA / "configs"
    if cfg_src.is_dir() and not (cfg_dst / "tsv").is_file():
        cfg_dst.mkdir(parents=True, exist_ok=True)
        for item in cfg_src.iterdir():
            shutil.copy2(item, cfg_dst / item.name)

    OUT.mkdir(parents=True, exist_ok=True)
    pdf_hash = sha256_file(PDF)
    version = tess_version()
    print(f"tesseract={version}", flush=True)
    print(f"pdf_sha256={pdf_hash}", flush=True)

    pages_meta = extract_page_images(PDF, OUT)

    page_results = []
    for meta in pages_meta:
        page = meta["page"]
        png = OUT / meta["png_path"]
        base = OUT / f"page_{page:03d}_ocr"
        print(f"OCR page {page}…", flush=True)
        ocr = run_tesseract(png, base)
        cleaned = light_clean(ocr["raw_text"])
        cleaned_path = OUT / f"page_{page:03d}_cleaned.txt"
        cleaned_path.write_text(cleaned, encoding="utf-8")
        # Persist words JSON separately (can be large)
        words_path = OUT / f"page_{page:03d}_words.json"
        words_path.write_text(
            json.dumps(ocr["words"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Keep raw text copy with explicit name
        raw_copy = OUT / f"page_{page:03d}_raw.txt"
        raw_copy.write_text(ocr["raw_text"], encoding="utf-8")

        page_results.append(
            {
                "page": page,
                "status": ocr["status"],
                "warnings": ocr["warnings"],
                "image": meta,
                "ocr": {
                    "raw_txt": raw_copy.name,
                    "cleaned_txt": cleaned_path.name,
                    "tsv": ocr["tsv_path"],
                    "words_json": words_path.name,
                    "word_count": ocr["word_count"],
                    "mean_confidence": ocr["mean_confidence"],
                    "median_confidence": ocr["median_confidence"],
                    "raw_char_count": len(ocr["raw_text"]),
                    "cleaned_char_count": len(cleaned),
                    "cyrillic_char_count": sum(
                        1 for ch in cleaned if ("А" <= ch <= "я") or ch in "ёЁ"
                    ),
                },
                "preview": cleaned[:800],
            }
        )
        print(
            f"  status={ocr['status']} words={ocr['word_count']} "
            f"mean_conf={ocr['mean_confidence']} cyr={page_results[-1]['ocr']['cyrillic_char_count']}",
            flush=True,
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pdf": str(PDF.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": pdf_hash,
        "page_count": len(page_results),
        "tesseract": {
            "binary": str(TESSERACT),
            "version_line": version,
            "lang": LANG,
            "tessdata_dir": str(TESSDATA.relative_to(ROOT)).replace("\\", "/"),
            "psm": 3,
            "preserve_interword_spaces": True,
            "installation_note": (
                "UB-Mannheim.TesseractOCR 5.4.0.20240606 via winget; "
                "called by absolute path (PATH unchanged). "
                "rus.traineddata from github.com/tesseract-ocr/tessdata (main)."
            ),
        },
        "pages": page_results,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Combined for convenience but with clear page boundaries
    combined = []
    for pr in page_results:
        combined.append(f"\n\n===== PDF_PAGE {pr['page']} =====\n\n")
        combined.append((OUT / pr["ocr"]["cleaned_txt"]).read_text(encoding="utf-8"))
    (OUT / "all_pages_cleaned_bounded.txt").write_text("".join(combined), encoding="utf-8")
    print(f"wrote {OUT / 'manifest.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
