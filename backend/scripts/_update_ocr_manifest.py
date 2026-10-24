"""One-off: parse TSV into words.json and refresh OCR pilot manifest stats."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median

OUT = Path("data/bank_materials/ocr/ALFA-Macro_Insights-Policy_Rate_11Sep")


def parse_tsv(tsv_path: Path) -> list[dict]:
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    words: list[dict] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            continue
        row = dict(zip(header, parts))
        if int(row.get("level", 0)) != 5:
            continue
        text = row.get("text", "")
        if not text.strip():
            continue
        words.append(
            {
                "text": text,
                "conf": float(row.get("conf", "-1")),
                "left": int(float(row["left"])),
                "top": int(float(row["top"])),
                "width": int(float(row["width"])),
                "height": int(float(row["height"])),
                "block_num": int(row.get("block_num", 0)),
                "par_num": int(row.get("par_num", 0)),
                "line_num": int(row.get("line_num", 0)),
                "word_num": int(row.get("word_num", 0)),
            }
        )
    return words


def find_span(words: list[dict], token: str) -> dict | None:
    for i, w in enumerate(words):
        if token in w["text"]:
            window = words[i : i + 10]
            left = min(x["left"] for x in window)
            top = min(x["top"] for x in window)
            right = max(x["left"] + x["width"] for x in window)
            bottom = max(x["top"] + x["height"] for x in window)
            confs = [x["conf"] for x in window if x["conf"] >= 0]
            return {
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
                "mean_conf": round(mean(confs), 1) if confs else None,
                "sample": " ".join(x["text"] for x in window),
            }
    return None


def main() -> None:
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    for pr in manifest["pages"]:
        page = pr["page"]
        words = parse_tsv(OUT / f"page_{page:03d}_ocr.tsv")
        confs = [w["conf"] for w in words if w["conf"] >= 0]
        (OUT / f"page_{page:03d}_words.json").write_text(
            json.dumps(words, ensure_ascii=False), encoding="utf-8"
        )
        pr["ocr"]["tsv"] = f"page_{page:03d}_ocr.tsv"
        pr["ocr"]["word_count"] = len(words)
        pr["ocr"]["mean_confidence"] = round(mean(confs), 2) if confs else None
        pr["ocr"]["median_confidence"] = round(median(confs), 2) if confs else None
        print(
            f"page {page}: words={len(words)} "
            f"mean={pr['ocr']['mean_confidence']} median={pr['ocr']['median_confidence']}"
        )

    words1 = json.loads((OUT / "page_001_words.json").read_text(encoding="utf-8"))
    anchors = {}
    for token in ("14,0%", "неизменной", "23 октября", "13,5%", "12,0%", "корпоративного"):
        anchors[token] = find_span(words1, token)
        print(token, anchors[token])

    manifest["page1_anchors"] = anchors
    manifest["tesseract"]["tessdata_configs"] = (
        "tools/tessdata/configs copied from UB-Mannheim install "
        "(required for tsv/txt configfiles when using --tessdata-dir)"
    )
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
