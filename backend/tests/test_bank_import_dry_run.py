"""Bank materials dry-run validator: synthetic fixtures + no application DB."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter

from app.jobs.import_bank_materials import main as cli_main
from app.services.bank_materials.dry_run import run_bank_materials_dry_run
from app.services.bank_materials.fingerprint import canonicalize_fingerprint, fingerprint_hash


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _write_pdf(path: Path, pages: int = 1, *, unique_seed: int = 0) -> None:
    writer = PdfWriter()
    # Vary geometry so distinct slugs do not collide on SHA-256 of blank PDFs.
    width = 200 + (unique_seed % 50)
    height = 300 + (unique_seed % 37)
    for _ in range(pages):
        writer.add_blank_page(width=width, height=height)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        writer.write(f)


def _write_png(path: Path, w: int = 200, h: int = 300) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color=(255, 255, 255)).save(path)


def _build_valid_corpus(
    root: Path,
    *,
    slug: str = "sample-doc",
    pages: int = 2,
    fragments: list[dict] | None = None,
    identity: dict | None = None,
    mutate_manifest: Callable[[dict], None] | None = None,
) -> tuple[Path, Path]:
    """Create pdf-dir + ocr-dir with a coherent schema-shaped document."""
    pdf_dir = root / "raw"
    ocr_root = root / "ocr"
    doc_dir = ocr_root / slug
    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True)
    pdf_dir.mkdir(parents=True)

    pdf_path = pdf_dir / f"{slug}.pdf"
    _write_pdf(pdf_path, pages=pages, unique_seed=sum(ord(c) for c in slug))
    sha = _sha256(pdf_path)

    page_entries = []
    for n in range(1, pages + 1):
        _write_png(pages_dir / f"page_{n:03d}.png")
        (doc_dir / f"page_{n:03d}_raw.txt").write_text("raw\n", encoding="utf-8")
        (doc_dir / f"page_{n:03d}_cleaned.txt").write_text("cleaned\n", encoding="utf-8")
        (doc_dir / f"page_{n:03d}_ocr.tsv").write_text(
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t10\t10\t20\t10\t90.0\thello\n",
            encoding="utf-8",
        )
        (doc_dir / f"page_{n:03d}_words.json").write_text("[]\n", encoding="utf-8")
        meta = {
            "page": n,
            "processing_status": "ok",
            "fingerprint": {
                "source_sha256": sha,
                "tesseract_version_line": "tesseract v5.4.0",
                "lang": "rus+eng",
                "psm": 3,
                "preserve_interword_spaces": True,
                "eng_traineddata_sha256": "a" * 64,
                "rus_traineddata_sha256": "b" * 64,
                "schema_version": 2,
                "tesseract_binary": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                "tessdata_dir": r"C:\proj\tools\tessdata",
            },
            "image": {
                "page": n,
                "png_path": f"pages/page_{n:03d}.png",
                "width": 200,
                "height": 300,
            },
            "ocr": {
                "psm_used": 3,
                "mean_confidence": 90.0,
                "word_count": 1,
            },
            "visual_verification_status": "unverified",
            "content_regions": [{"type": "prose", "status": "unverified"}],
            "visual_checks": {},
        }
        (doc_dir / f"page_{n:03d}_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        page_entries.append(
            {
                "page": n,
                "processing_status": "ok",
                "image": {"width": 200, "height": 300, "png_path": f"pages/page_{n:03d}.png"},
                "ocr": {"mean_confidence": 90.0, "word_count": 1},
            }
        )

    if fragments is None:
        fragments = [
            {
                "id": "quote_1",
                "kind": "exact_quote",
                "content_type": "fact",
                "page": 1,
                "regions": [
                    {"bbox": {"left": 10, "top": 10, "width": 50, "height": 20}, "note": "r1"}
                ],
                "ocr_text": "hello",
                "exact_quote": "hello",
                "verification_status": "verified",
            }
        ]

    default_identity = {
        "confirmed_title": "Sample",
        "confirmed_title_status": "confirmed",
        "confirmed_publication_date": "2026-09-11",
        "confirmed_publication_date_status": "confirmed",
        "confirmed_publication_date_display": "11 сентября 2026 г.",
        "period_covered": "2026",
        "period_covered_status": "confirmed",
        "topics": ["test"],
        "topics_status": "confirmed",
        "staleness_note": None,
    }
    identity = identity if identity is not None else default_identity

    fp = {
        "schema_version": 2,
        "source_sha256": sha,
        "tesseract_version_line": "tesseract v5.4.0",
        "lang": "rus+eng",
        "psm": 3,
        "preserve_interword_spaces": True,
        "eng_traineddata_sha256": "a" * 64,
        "rus_traineddata_sha256": "b" * 64,
        "tesseract_binary": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        "tessdata_dir": r"C:\proj\tools\tessdata",
    }
    manifest = {
        "schema_version": 2,
        "source_filename": f"{slug}.pdf",
        "source_pdf": f"data/bank_materials/raw/{slug}.pdf",
        "source_sha256": sha,
        "page_count": pages,
        "processing_status": "complete",
        "document_visual_status": "partial_spot_check",
        "fingerprint": fp,
        "tesseract": {
            "version_line": "tesseract v5.4.0",
            "lang": "rus+eng",
            "psm": 3,
            "preserve_interword_spaces": True,
        },
        "document_identity": identity,
        "pages": page_entries,
    }
    if mutate_manifest:
        mutate_manifest(manifest)

    (doc_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (doc_dir / "fragments.json").write_text(
        json.dumps({"schema_version": 2, "fragments": fragments}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return ocr_root, pdf_dir


def test_cli_requires_dry_run():
    assert cli_main([]) == 2


def _confirmed_fragment(**overrides: object) -> dict:
    base = {
        "id": "quote_confirmed",
        "kind": "exact_quote",
        "content_type": "fact",
        "content_type_status": "confirmed",
        "primary_region_type": "prose",
        "page": 1,
        "regions": [
            {
                "region_type": "prose",
                "bbox": {"left": 10, "top": 10, "width": 50, "height": 20},
            }
        ],
        "ocr_text": "hello",
        "exact_quote": "hello",
        "verification_status": "verified",
    }
    base.update(overrides)
    return base


def test_valid_corpus_dry_run(tmp_path: Path):
    """Corpus without explicit trust fields remains importable but not AI-eligible."""
    ocr, pdf = _build_valid_corpus(tmp_path)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert result.ok, [e.detail for e in result.errors]
    assert result.totals["documents"] == 1
    assert result.totals["fragments"] == 1
    assert result.totals["eligible_search"] == 1
    assert result.totals["eligible_exact_quote"] == 0
    assert result.totals["eligible_ai_evidence"] == 0
    assert any(
        w.code == "primary_region_type_missing_treated_as_unverified" for w in result.warnings
    )
    assert any(
        w.code == "content_type_status_missing_treated_as_unknown" for w in result.warnings
    )


def test_explicitly_confirmed_prose_allows_quote(tmp_path: Path):
    ocr, pdf = _build_valid_corpus(tmp_path, fragments=[_confirmed_fragment()])
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert result.ok, [e.code for e in result.errors]
    assert result.totals["eligible_exact_quote"] == 1
    assert result.totals["eligible_ai_evidence"] == 1
    detail = result.documents[0]["fragment_details"][0]
    assert detail["primary_region_type_source"] == "fragments[].primary_region_type"
    assert detail["content_type_status_source"] == "fragments[].content_type_status"


def test_wrong_sha_and_missing_pdf(tmp_path: Path):
    ocr, pdf = _build_valid_corpus(tmp_path)

    def bad_sha(man: dict) -> None:
        man["source_sha256"] = "0" * 64

    ocr2, pdf2 = _build_valid_corpus(tmp_path / "sha", mutate_manifest=bad_sha)
    result = run_bank_materials_dry_run(input_dir=ocr2, pdf_dir=pdf2)
    assert not result.ok
    assert any(e.code == "pdf_sha_mismatch" for e in result.errors)

    # missing pdf
    ocr3, pdf3 = _build_valid_corpus(tmp_path / "miss")
    list(pdf3.glob("*.pdf"))[0].unlink()
    result = run_bank_materials_dry_run(input_dir=ocr3, pdf_dir=pdf3)
    assert not result.ok
    assert any(e.code == "pdf_missing" for e in result.errors)


def test_duplicate_pages_and_keys(tmp_path: Path):
    def dup_page(man: dict) -> None:
        man["pages"].append(dict(man["pages"][0]))

    ocr, pdf = _build_valid_corpus(tmp_path / "dup_page", mutate_manifest=dup_page)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert not result.ok
    assert any(e.code == "duplicate_page_number" for e in result.errors)

    frags = [
        {
            "id": "same",
            "revision": 1,
            "kind": "exact_quote",
            "content_type": "fact",
            "page": 1,
            "regions": [{"bbox": {"left": 1, "top": 1, "width": 2, "height": 2}}],
            "exact_quote": "a",
            "verification_status": "verified",
        },
        {
            "id": "same",
            "revision": 1,
            "kind": "exact_quote",
            "content_type": "fact",
            "page": 1,
            "regions": [{"bbox": {"left": 1, "top": 1, "width": 2, "height": 2}}],
            "exact_quote": "b",
            "verification_status": "verified",
        },
    ]
    ocr2, pdf2 = _build_valid_corpus(tmp_path / "dup_key", fragments=frags)
    result = run_bank_materials_dry_run(input_dir=ocr2, pdf_dir=pdf2)
    assert not result.ok
    assert any(e.code == "duplicate_stable_key_revision" for e in result.errors)


def test_bad_dates(tmp_path: Path):
    ocr, pdf = _build_valid_corpus(
        tmp_path / "bad_date",
        identity={
            "confirmed_title": "X",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-13",
            "confirmed_publication_date_status": "confirmed",
            "period_covered_status": "unknown",
            "topics_status": "unknown",
        },
    )
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert not result.ok
    assert any(e.code == "publication_month_out_of_range" for e in result.errors)

    # month precision must not invent day — YYYY-MM is OK
    ocr2, pdf2 = _build_valid_corpus(
        tmp_path / "month",
        identity={
            "confirmed_title": "Gold",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-08",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "АВГУСТ 2026",
            "period_covered_status": "confirmed",
            "topics_status": "confirmed",
        },
    )
    result = run_bank_materials_dry_run(input_dir=ocr2, pdf_dir=pdf2)
    assert result.ok, [e.code for e in result.errors]
    pub = result.documents[0]["publication"]
    assert pub["precision"] == "month"
    assert pub["publication_date"] is None


def test_bbox_outside_page(tmp_path: Path):
    frags = [
        {
            "id": "big",
            "kind": "exact_quote",
            "content_type": "fact",
            "page": 1,
            "regions": [{"bbox": {"left": 10, "top": 10, "width": 500, "height": 20}}],
            "exact_quote": "x",
            "verification_status": "verified",
        }
    ]
    ocr, pdf = _build_valid_corpus(tmp_path, fragments=frags)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert not result.ok
    assert any(e.code == "bbox_outside_page" for e in result.errors)


def test_fragment_page_mismatch(tmp_path: Path):
    frags = [
        {
            "id": "orphan",
            "kind": "exact_quote",
            "content_type": "fact",
            "page": 9,
            "regions": [{"bbox": {"left": 1, "top": 1, "width": 2, "height": 2}}],
            "exact_quote": "x",
            "verification_status": "verified",
        }
    ]
    ocr, pdf = _build_valid_corpus(tmp_path, fragments=frags)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert not result.ok
    assert any(e.code == "fragment_page_missing" for e in result.errors)


def test_summary_mislabeled_as_quote(tmp_path: Path):
    frags = [
        {
            "id": "mis",
            "kind": "exact_quote",
            "content_type": "interpretation",
            "page": 1,
            "regions": [{"bbox": {"left": 1, "top": 1, "width": 2, "height": 2}}],
            "summary": "This is only a paraphrase",
            "verification_status": "verified",
        }
    ]
    ocr, pdf = _build_valid_corpus(tmp_path, fragments=frags)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert not result.ok
    assert any(
        e.code in ("summary_mislabeled_as_exact_quote", "exact_quote_marked_as_summary_text_only")
        for e in result.errors
    )


def test_verified_without_regions(tmp_path: Path):
    frags = [
        {
            "id": "noreg",
            "kind": "exact_quote",
            "content_type": "fact",
            "page": 1,
            "regions": [],
            "exact_quote": "hello",
            "verification_status": "verified",
        }
    ]
    ocr, pdf = _build_valid_corpus(tmp_path, fragments=frags)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert not result.ok
    assert any(e.code == "verified_without_regions" for e in result.errors)
    # eligibility must not grant quote
    detail = result.documents[0]["fragment_details"][0]["eligibility"]
    assert not detail["eligible_exact_quote"]
    assert not detail["eligible_ai_evidence"]


def test_needs_reverification_not_evidence(tmp_path: Path):
    frags = [
        {
            "id": "nr",
            "kind": "exact_quote",
            "content_type": "fact",
            "page": 1,
            "regions": [{"bbox": {"left": 1, "top": 1, "width": 2, "height": 2}}],
            "exact_quote": "hello",
            "verification_status": "needs_reverification",
        }
    ]
    ocr, pdf = _build_valid_corpus(tmp_path, fragments=frags)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert result.ok, [e.code for e in result.errors]
    el = result.documents[0]["fragment_details"][0]["eligibility"]
    assert el["eligible_search"]
    assert not el["eligible_ai_evidence"]
    assert not el["eligible_exact_quote"]


def test_path_escape_rejected(tmp_path: Path):
    ocr, pdf = _build_valid_corpus(tmp_path)

    def escape(man: dict) -> None:
        man["pages"][0]["image"]["png_path"] = "../secret.png"

    ocr2, pdf2 = _build_valid_corpus(tmp_path / "esc", mutate_manifest=escape)
    # also plant escaping path inside page meta
    meta_path = next((ocr2 / "sample-doc").glob("page_*_meta.json"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["image"]["png_path"] = "../../outside.png"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    result = run_bank_materials_dry_run(input_dir=ocr2, pdf_dir=pdf2)
    assert not result.ok
    assert any(e.code == "artifact_path_escape" for e in result.errors)


def test_fingerprint_strips_absolute_paths(tmp_path: Path):
    ocr, pdf = _build_valid_corpus(tmp_path)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert result.ok
    canon = result.documents[0]["fingerprint_canonical"]
    assert "tesseract_binary" not in canon
    assert "tessdata_dir" not in canon
    assert canon["lang"] == "rus+eng"
    assert "a" * 64 == canon["eng_traineddata_sha256"]
    # Host path keys must not affect hash of canonical payload
    base = {k: canon[k] for k in ("schema_version", "source_sha256", "lang", "psm") if k in canon}
    h1 = fingerprint_hash(canonicalize_fingerprint({**base, "tesseract_binary": r"C:\a.exe"}))
    h2 = fingerprint_hash(canonicalize_fingerprint({**base, "tesseract_binary": r"D:\b.exe"}))
    assert h1 == h2


def test_cli_dry_run_writes_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ocr, pdf = _build_valid_corpus(tmp_path / "corpus")
    report = tmp_path / "reports"
    code = cli_main(
        [
            "--dry-run",
            "--input-dir",
            str(ocr),
            "--pdf-dir",
            str(pdf),
            "--report-dir",
            str(report),
        ]
    )
    assert code == 0
    assert (report / "bank_import_dry_run_latest.json").is_file()
    assert (report / "bank_import_dry_run_latest.md").is_file()


def test_trust_verified_missing_region_type_no_ai(tmp_path: Path):
    frags = [
        {
            "id": "v_no_type",
            "kind": "exact_quote",
            "content_type": "fact",
            "content_type_status": "confirmed",
            "page": 1,
            "regions": [{"bbox": {"left": 1, "top": 1, "width": 2, "height": 2}}],
            "exact_quote": "hello",
            "verification_status": "verified",
        }
    ]
    ocr, pdf = _build_valid_corpus(tmp_path, fragments=frags)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert result.ok
    el = result.documents[0]["fragment_details"][0]
    assert el["primary_region_type"] == "unverified"
    assert el["suitable_for_storage"] is True
    assert el["suitable_for_ai_evidence"] is False
    assert el["suitable_for_exact_quote"] is False
    assert el["eligibility"]["eligible_search"] is True


def test_trust_verified_missing_content_type_status_no_ai(tmp_path: Path):
    frags = [
        {
            "id": "v_no_cts",
            "kind": "exact_quote",
            "content_type": "fact",
            "primary_region_type": "prose",
            "page": 1,
            "regions": [
                {
                    "region_type": "prose",
                    "bbox": {"left": 1, "top": 1, "width": 2, "height": 2},
                }
            ],
            "exact_quote": "hello",
            "verification_status": "verified",
        }
    ]
    ocr, pdf = _build_valid_corpus(tmp_path, fragments=frags)
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert result.ok
    el = result.documents[0]["fragment_details"][0]
    assert el["content_type_status"] == "unknown"
    assert el["suitable_for_ai_evidence"] is False
    assert el["suitable_for_exact_quote"] is False
    assert "content_type_status" in el["missing_trust_fields"]


def test_trust_high_confidence_and_page_spot_check_do_not_elevate(tmp_path: Path):
    from app.services.bank_materials.eligibility import compute_fragment_eligibility

    e = compute_fragment_eligibility(
        verification_status="verified",
        kind="exact_quote",
        primary_region_type="unverified",
        content_type="fact",
        content_type_status="unknown",
        verified_transcript="x",
        summary_text=None,
        region_count=1,
        page_visual_verification_status="verified_spot_check",
        mean_confidence=99.9,
    )
    assert e.eligible_search
    assert not e.eligible_ai_evidence
    assert not e.eligible_exact_quote


def test_trust_verified_summary_never_exact_quote(tmp_path: Path):
    ocr, pdf = _build_valid_corpus(
        tmp_path,
        fragments=[
            _confirmed_fragment(
                id="sum1",
                kind="summary",
                exact_quote=None,
                summary="Bank paraphrase only",
                content_type="interpretation",
            )
        ],
    )
    result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
    assert result.ok
    el = result.documents[0]["fragment_details"][0]
    assert el["suitable_for_ai_evidence"] is True
    assert el["suitable_for_exact_quote"] is False
    assert el["eligibility"]["evidence_as_summary_only"] is True


def test_trust_blocked_region_types(tmp_path: Path):
    for rtype in ("table", "chart", "contacts_disclaimer", "mixed"):
        ocr, pdf = _build_valid_corpus(
            tmp_path / rtype,
            fragments=[_confirmed_fragment(id=f"t_{rtype}", primary_region_type=rtype)],
        )
        result = run_bank_materials_dry_run(input_dir=ocr, pdf_dir=pdf)
        el = result.documents[0]["fragment_details"][0]
        assert el["suitable_for_ai_evidence"] is False, rtype
        assert el["suitable_for_exact_quote"] is False, rtype
        assert el["eligibility"]["eligible_search"] is False, rtype


def test_normalize_does_not_elevate_unknown_fields():
    from app.services.bank_materials.normalize import map_fragment

    mapped, issues = map_fragment(
        {
            "id": "x",
            "kind": "exact_quote",
            "content_type": "fact",
            "page": 1,
            "regions": [{"bbox": {"left": 1, "top": 1, "width": 2, "height": 2}}],
            "exact_quote": "hello",
            "verification_status": "verified",
        },
        document="doc",
        page_dims={1: (200, 300)},
        known_pages={1},
    )
    assert mapped is not None
    assert mapped.primary_region_type == "unverified"
    assert mapped.content_type_status == "unknown"
    assert mapped.suitable_for_ai_evidence is False
    codes = {i.code for i in issues}
    assert "primary_region_type_missing_treated_as_unverified" in codes
    assert "content_type_status_missing_treated_as_unknown" in codes
    assert "primary_region_type_provisional_prose" not in codes
    assert "content_type_status_inferred_confirmed" not in codes
