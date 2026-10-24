"""Apply visual QA / document identity / fragments onto OCR manifests (stage 2.3).

Does not re-run OCR. Edits only JSON metadata under data/bank_materials/ocr/.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OCR_ROOT = ROOT / "data" / "bank_materials" / "ocr"
sys.path.insert(0, str(ROOT / "scripts"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unverified_page(note: str = "Not visually checked in this stage.") -> dict[str, Any]:
    return {
        "visual_verification_status": "unverified",
        "content_regions": [
            {"type": "unverified", "status": "unverified", "notes": note}
        ],
        "visual_checks": {
            "title": {"value": None, "status": "unknown"},
            "publication_date": {"value": None, "status": "unknown"},
            "period_covered": {"value": None, "status": "unknown"},
            "main_takeaway": {"value": None, "status": "unknown"},
        },
    }


def spot_prose(
    *,
    title: str | None,
    pub_date: str | None,
    period: str | None,
    takeaway: str | None,
    extra_regions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    regions = [
        {
            "type": "prose",
            "status": "verified_ok",
            "notes": "Title/date/takeaway spot-checked vs page image.",
        }
    ]
    if extra_regions:
        regions.extend(extra_regions)
    return {
        "visual_verification_status": "verified_spot_check",
        "content_regions": regions,
        "visual_checks": {
            "title": {
                "value": title,
                "status": "confirmed" if title else "unknown",
            },
            "publication_date": {
                "value": pub_date,
                "status": "confirmed" if pub_date else "unknown",
                "note": "From page content; not PDF export metadata.",
            },
            "period_covered": {
                "value": period,
                "status": "confirmed" if period else "unknown",
            },
            "main_takeaway": {
                "value": takeaway,
                "status": "confirmed" if takeaway else "unknown",
            },
        },
        "note": "Spot-check only; not full document verification.",
    }


def update_page_visual(doc_dir: Path, page: int, visual: dict[str, Any]) -> None:
    meta_path = doc_dir / f"page_{page:03d}_meta.json"
    meta = load(meta_path) if meta_path.is_file() else {"page": page}
    meta.update(visual)
    save(meta_path, meta)
    man_path = doc_dir / "manifest.json"
    if not man_path.is_file():
        return
    man = load(man_path)
    pages = man.get("pages") or []
    for i, p in enumerate(pages):
        if p.get("page") == page:
            pages[i] = {**p, **visual}
            break
    man["pages"] = pages
    checked = [
        p["page"]
        for p in pages
        if p.get("visual_verification_status")
        in ("verified_partial", "verified_spot_check", "verified")
    ]
    unverified = [
        p["page"]
        for p in pages
        if p.get("visual_verification_status") in (None, "unverified")
    ]
    man["pages_visually_checked"] = checked
    man["pages_visually_unverified"] = unverified
    man["document_visual_status"] = (
        "partial_spot_check" if checked else "unverified"
    )
    man["generated_at"] = utc_now()
    save(man_path, man)


def set_identity(doc_dir: Path, identity: dict[str, Any]) -> None:
    man_path = doc_dir / "manifest.json"
    man = load(man_path)
    man["document_identity"] = identity
    man["document_visual_status"] = "partial_spot_check"
    man["generated_at"] = utc_now()
    save(man_path, man)


def set_fragments(doc_dir: Path, fragments: dict[str, Any]) -> None:
    fragments = {**fragments, "updated_at": utc_now()}
    save(doc_dir / "fragments.json", fragments)


def fill_remaining_unverified(doc_dir: Path, checked_pages: set[int]) -> None:
    man = load(doc_dir / "manifest.json")
    for p in man.get("pages") or []:
        page = int(p["page"])
        if page in checked_pages:
            continue
        if p.get("visual_verification_status") not in (None, "unverified"):
            continue
        update_page_visual(doc_dir, page, unverified_page())


CHART = {
    "type": "chart",
    "status": "verified_unreliable",
    "notes": "Charts present; numeric series NOT confirmed from OCR. Captions ≠ extraction.",
}
TABLE = {
    "type": "table",
    "status": "verified_unreliable",
    "notes": "Table present; cell values NOT confirmed from OCR alone.",
}
CONTACTS = {
    "type": "contacts_disclaimer",
    "status": "unverified",
    "notes": "Header contacts / footer disclaimer not fully mapped.",
}


QA: dict[str, dict[str, Any]] = {
    "ALFA-7M26": {
        "identity": {
            "confirmed_title": "Макростатистика 7М26",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-09-07",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "7 сентября 2026",
            "period_covered": "7 месяцев 2026; оперативные данные лета–августа 2026",
            "period_covered_status": "confirmed",
            "topics": [
                "макростатистика",
                "рынок труда",
                "розничная торговля",
                "автопродажи",
            ],
            "topics_status": "confirmed",
            "staleness_note": None,
        },
        "pages": {
            1: spot_prose(
                title="Макростатистика 7М26",
                pub_date="7 сентября 2026",
                period="7М26 / лето–август 2026",
                takeaway="Данные по рынку труда не подтверждают охлаждения экономики",
                extra_regions=[CHART, CONTACTS],
            ),
        },
        "fragments": {
            "schema_version": 2,
            "document": "ALFA-7M26",
            "source_pdf": "data/bank_materials/raw/ALFA-7M26.pdf",
            "needs_reverification": False,
            "fragments": [
                {
                    "id": "7m26_lead",
                    "kind": "exact_quote",
                    "content_type": "interpretation",
                    "source_document": "ALFA-7M26",
                    "page": 1,
                    "regions": [
                        {"bbox": None, "note": "Subtitle under title."}
                    ],
                    "ocr_text": "Данные no рынку труда He подтверждают охлаждения экономики",
                    "exact_quote": "Данные по рынку труда не подтверждают охлаждения экономики",
                    "ocr_correction": {
                        "from": "no/He",
                        "to": "по/не",
                        "basis": "visual_check_of_page_image",
                    },
                    "summary": None,
                    "verification_status": "verified",
                },
                {
                    "id": "7m26_retail_july",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "ALFA-7M26",
                    "page": 1,
                    "regions": [
                        {"bbox": None, "note": "Body paragraph on July retail."}
                    ],
                    "ocr_text": "Рост оборота розничной торговли был на уровне 5,3% г/г в июле",
                    "exact_quote": "Рост оборота розничной торговли был на уровне 5,3% г/г в июле",
                    "summary": None,
                    "verification_status": "verified",
                    "notes": "As stated in bank material; Rosstat primary link not opened.",
                },
            ],
        },
    },
    "ALFA-consumption": {
        "identity": {
            "confirmed_title": "Потребление на пике",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-08-05",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "5 августа 2026 г.",
            "period_covered": "июнь–июль 2026; ожидания 2П26 / 4К26",
            "period_covered_status": "confirmed",
            "topics": ["потребление", "розничная торговля", "автопродажи", "рынок труда"],
            "topics_status": "confirmed",
            "staleness_note": None,
        },
        "pages": {
            1: spot_prose(
                title="Потребление на пике",
                pub_date="5 августа 2026 г.",
                period="июнь–июль 2026; прогноз на 2П26/4К26",
                takeaway="Динамика потребления на пике; в 4К26 банк ориентируется на нулевой рост г/г",
                extra_regions=[CHART, CONTACTS],
            ),
        },
        "fragments": {
            "schema_version": 2,
            "document": "ALFA-consumption",
            "source_pdf": "data/bank_materials/raw/ALFA-consumption.pdf",
            "needs_reverification": False,
            "fragments": [
                {
                    "id": "consumption_peak_forecast",
                    "kind": "summary",
                    "content_type": "forecast",
                    "source_document": "ALFA-consumption",
                    "page": 1,
                    "regions": [
                        {"bbox": None, "note": "Lead paragraph under title."}
                    ],
                    "ocr_text": None,
                    "exact_quote": None,
                    "summary": (
                        "Банк считает, что динамика потребления сейчас на пике и в "
                        "следующие месяцы будет охлаждаться; в 4К26 ориентир — рост "
                        "потребления около нуля в годовом выражении."
                    ),
                    "verification_status": "verified",
                    "notes": "Explicit summary, not exact quote.",
                },
                {
                    "id": "consumption_retail_june",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "ALFA-consumption",
                    "page": 1,
                    "regions": [{"bbox": None}],
                    "ocr_text": "Оборот розничной торговли вырос Ha 7,3% г/г в июне",
                    "exact_quote": "Оборот розничной торговли вырос на 7,3% г/г в июне",
                    "ocr_correction": {
                        "from": "Ha",
                        "to": "на",
                        "basis": "visual_check_of_page_image",
                    },
                    "summary": None,
                    "verification_status": "verified",
                },
            ],
        },
    },
    "ALFA-macro_stat1H26": {
        "identity": {
            "confirmed_title": "Макростатистика 1П26",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-07-31",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "31 июля 2026 г.",
            "period_covered": "1 полугодие 2026; прогнозы на 2026",
            "period_covered_status": "confirmed",
            "topics": ["макростатистика", "ВВП", "инфляция", "ставка", "рынок труда"],
            "topics_status": "confirmed",
            "staleness_note": None,
        },
        "pages": {
            1: spot_prose(
                title="Макростатистика 1П26",
                pub_date="31 июля 2026 г.",
                period="1П26; прогноз ВВП/ставки на 2026",
                takeaway="Слабый рост 1П26 смещает прогноз роста ВВП на 0,1% за год",
                extra_regions=[TABLE, CONTACTS],
            ),
        },
        "fragments": {
            "schema_version": 2,
            "document": "ALFA-macro_stat1H26",
            "source_pdf": "data/bank_materials/raw/ALFA-macro_stat1H26.pdf",
            "needs_reverification": False,
            "fragments": [
                {
                    "id": "macro1h26_title",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "ALFA-macro_stat1H26",
                    "page": 1,
                    "regions": [{"bbox": None}],
                    "ocr_text": "Макростатистика 11126",
                    "exact_quote": "Макростатистика 1П26",
                    "ocr_correction": {
                        "from": "11126",
                        "to": "1П26",
                        "basis": "visual_check_of_page_image",
                    },
                    "summary": None,
                    "verification_status": "verified",
                },
                {
                    "id": "macro1h26_gdp_forecast",
                    "kind": "exact_quote",
                    "content_type": "forecast",
                    "source_document": "ALFA-macro_stat1H26",
                    "page": 1,
                    "regions": [
                        {"bbox": None, "note": "Subtitle; may span two lines."}
                    ],
                    "ocr_text": "Слабый poct 1126 смещает наш прогноз pocta ВВП Ha 0,1% за ron,",
                    "exact_quote": "Слабый рост 1П26 смещает наш прогноз роста ВВП на 0,1% за год",
                    "ocr_correction": {
                        "from": "poct/1126/Ha/ron",
                        "to": "рост/1П26/на/год",
                        "basis": "visual_check_of_page_image",
                    },
                    "summary": None,
                    "verification_status": "verified",
                    "notes": "Bank forecast revision, not a statistical agency release.",
                },
            ],
        },
    },
    "ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021": {
        "identity": {
            "confirmed_title": "Российская сталь",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2021-04-15",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "15 April 2021",
            "period_covered": "1К21 preview / update; не текущая позиция 2026",
            "period_covered_status": "confirmed",
            "topics": ["сталь", "металлургия", "дивиденды", "Severstal", "NLMK", "MMK"],
            "topics_status": "confirmed",
            "staleness_note": (
                "Material dated April 2021. Do NOT treat as current 2026 bank stance."
            ),
        },
        "pages": {
            1: spot_prose(
                title="Российская сталь",
                pub_date="15 April 2021",
                period="1К21; прогноз результатов квартала",
                takeaway="Ралли цен продолжается; прогноз результатов за 1К21",
                extra_regions=[
                    TABLE,
                    CHART,
                    {
                        "type": "mixed",
                        "status": "unverified",
                        "notes": "Sidebar recommendations/prices not fully verified.",
                    },
                ],
            ),
        },
        "fragments": {
            "schema_version": 2,
            "document": "ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021",
            "source_pdf": (
                "data/bank_materials/raw/"
                "ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021.pdf"
            ),
            "needs_reverification": False,
            "fragments": [
                {
                    "id": "steels_date_2021",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021",
                    "page": 1,
                    "regions": [{"bbox": None, "note": "Date in header."}],
                    "ocr_text": None,
                    "exact_quote": "15 April 2021",
                    "summary": None,
                    "verification_status": "verified",
                    "notes": (
                        "Publication date confirmed from page content (not filename alone). "
                        "Historical material — not current stance."
                    ),
                },
                {
                    "id": "steels_subtitle",
                    "kind": "exact_quote",
                    "content_type": "forecast",
                    "source_document": "ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021",
                    "page": 1,
                    "regions": [{"bbox": None}],
                    "ocr_text": "Ралли цен продолжается; прогноз результатов за 1К21",
                    "exact_quote": "Ралли цен продолжается; прогноз результатов за 1К21",
                    "summary": None,
                    "verification_status": "verified",
                },
            ],
        },
    },
    "FI_Strategy_3Q26_22072026": {
        "identity": {
            "confirmed_title": (
                "Тактический взгляд на 3-й квартал 2026г: Время собирать камни"
            ),
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-07-22",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "22 июля 2026 г.",
            "period_covered": "тактика на 3К26; обзор долгового рынка / 1П26 section",
            "period_covered_status": "confirmed",
            "topics": [
                "долговой рынок",
                "ОФЗ",
                "корпоративные облигации",
                "ДКП",
                "стратегия FI",
            ],
            "topics_status": "confirmed",
            "staleness_note": None,
        },
        "pages": {
            1: {
                "visual_verification_status": "verified_spot_check",
                "content_regions": [
                    {
                        "type": "prose",
                        "status": "verified_ok",
                        "notes": "Cover title/date/authors spot-checked.",
                    }
                ],
                "visual_checks": {
                    "title": {
                        "value": "Тактический взгляд на 3-й квартал 2026г: Время собирать камни",
                        "status": "confirmed",
                    },
                    "publication_date": {
                        "value": "22 июля 2026 г.",
                        "status": "confirmed",
                        "note": "From cover content.",
                    },
                    "period_covered": {
                        "value": "3К26",
                        "status": "confirmed",
                    },
                    "main_takeaway": {
                        "value": "Cover only; analytical takeaways start later",
                        "status": "confirmed",
                    },
                },
                "note": "Cover page; OCR sparse (white on red).",
            },
            3: spot_prose(
                title="Инвестиционное резюме",
                pub_date=None,
                period="середина 2026 / 3К26",
                takeaway=(
                    "Неприятие риска усиливается; геополитика и высокая ставка "
                    "как контекст для длинных облигаций"
                ),
                extra_regions=[
                    {
                        "type": "prose",
                        "status": "verified_ok",
                        "notes": "Investment summary prose spot-checked for presence of thesis.",
                    }
                ],
            ),
            4: {
                "visual_verification_status": "verified_spot_check",
                "content_regions": [
                    {
                        "type": "prose",
                        "status": "verified_ok",
                        "notes": "Section divider; single title line.",
                    }
                ],
                "visual_checks": {
                    "title": {
                        "value": "Итоги 1-го полугодия 2026 г.",
                        "status": "confirmed",
                    },
                    "publication_date": {"value": None, "status": "unknown"},
                    "period_covered": {
                        "value": "1П26",
                        "status": "confirmed",
                    },
                    "main_takeaway": {
                        "value": "Section divider only",
                        "status": "confirmed",
                    },
                },
                "note": "Recovered via PSM fallback after empty PSM 3.",
            },
        },
        "fragments": {
            "schema_version": 2,
            "document": "FI_Strategy_3Q26_22072026",
            "source_pdf": "data/bank_materials/raw/FI_Strategy_3Q26_22072026.pdf",
            "needs_reverification": False,
            "fragments": [
                {
                    "id": "fi_cover_title",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "FI_Strategy_3Q26_22072026",
                    "page": 1,
                    "regions": [
                        {"bbox": None, "note": "Cover title block."},
                        {"bbox": None, "note": "Cover subtitle line."},
                    ],
                    "ocr_text": "Тактический взгляд на 3-й кварт\n‚ Время собирать камни",
                    "exact_quote": (
                        "Тактический взгляд на 3-й квартал 2026г: Время собирать камни"
                    ),
                    "ocr_correction": {
                        "from": "truncated title on cover",
                        "to": "full title from visual",
                        "basis": "visual_check_of_page_image",
                    },
                    "summary": None,
                    "verification_status": "verified",
                },
                {
                    "id": "fi_section_1h26",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "FI_Strategy_3Q26_22072026",
                    "page": 4,
                    "regions": [{"bbox": None}],
                    "ocr_text": "Итоги 1-го полугодия 2026 г.",
                    "exact_quote": "Итоги 1-го полугодия 2026 г.",
                    "summary": None,
                    "verification_status": "verified",
                },
                {
                    "id": "fi_risk_thesis",
                    "kind": "summary",
                    "content_type": "interpretation",
                    "source_document": "FI_Strategy_3Q26_22072026",
                    "page": 3,
                    "regions": [{"bbox": None, "note": "Investment summary opening."}],
                    "ocr_text": None,
                    "exact_quote": None,
                    "summary": (
                        "В инвестиционном резюме банк отмечает усиление неприятия риска "
                        "на фоне геополитики и всё ещё высокой ключевой ставки; длинные "
                        "облигации с фиксированным купоном отнесены к рисковым активам."
                    ),
                    "verification_status": "verified",
                    "notes": "Summary of page-3 thesis; not a full-doc claim.",
                },
            ],
        },
    },
    "Gold_digest_August26": {
        "identity": {
            "confirmed_title": "Обзор рынка золота",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-08",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "АВГУСТ 2026",
            "period_covered": "август 2026",
            "period_covered_status": "confirmed",
            "topics": ["золото", "драгметаллы", "ставки Fed/CPC", "ETF"],
            "topics_status": "confirmed",
            "staleness_note": None,
        },
        "pages": {
            1: {
                "visual_verification_status": "verified_spot_check",
                "content_regions": [
                    {
                        "type": "prose",
                        "status": "verified_ok",
                        "notes": "Cover title and month/year only.",
                    },
                    {
                        "type": "mixed",
                        "status": "unverified",
                        "notes": "Photographic cover art; no analytical tables.",
                    },
                ],
                "visual_checks": {
                    "title": {
                        "value": "ОБЗОР РЫНКА ЗОЛОТА",
                        "status": "confirmed",
                    },
                    "publication_date": {
                        "value": "АВГУСТ 2026",
                        "status": "confirmed",
                        "note": "Month/year on cover; day-of-month not shown.",
                    },
                    "period_covered": {
                        "value": "август 2026",
                        "status": "confirmed",
                    },
                    "main_takeaway": {
                        "value": "Cover only",
                        "status": "confirmed",
                    },
                },
            },
            2: spot_prose(
                title=None,
                pub_date=None,
                period="август 2026",
                takeaway=(
                    "Золото заметно выросло за август, но жёсткий сигнал CPC охладил ралли"
                ),
                extra_regions=[CHART],
            ),
        },
        "fragments": {
            "schema_version": 2,
            "document": "Gold_digest_August26",
            "source_pdf": "data/bank_materials/raw/Gold_digest_August26.pdf",
            "needs_reverification": False,
            "fragments": [
                {
                    "id": "gold_cover",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "Gold_digest_August26",
                    "page": 1,
                    "regions": [
                        {"bbox": None, "note": "Title"},
                        {"bbox": None, "note": "Month line"},
                    ],
                    "ocr_text": "ОБЗОР РЫНКА ЗОЛОТА\n‚ АВГУСТ 2026",
                    "exact_quote": "ОБЗОР РЫНКА ЗОЛОТА / АВГУСТ 2026",
                    "summary": None,
                    "verification_status": "verified",
                },
                {
                    "id": "gold_august_lead",
                    "kind": "exact_quote",
                    "content_type": "interpretation",
                    "source_document": "Gold_digest_August26",
                    "page": 2,
                    "regions": [
                        {"bbox": None, "note": "Lead headline; may be two lines."}
                    ],
                    "ocr_text": "Золото заметно выросло за август, HO жесткий сигнал\nCPC охладил ралли",
                    "exact_quote": (
                        "Золото заметно выросло за август, но жесткий сигнал CPC охладил ралли"
                    ),
                    "ocr_correction": {
                        "from": "HO",
                        "to": "но",
                        "basis": "visual_check_of_page_image",
                    },
                    "summary": None,
                    "verification_status": "verified",
                },
            ],
        },
    },
    "Inflation_tracker_02": {
        "identity": {
            "confirmed_title": "Инфляция 25-31 августа: основные выводы",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-09-02",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "2 сентября 2026 года",
            "period_covered": "неделя 25–31 августа 2026",
            "period_covered_status": "confirmed",
            "topics": ["инфляция", "Росстат", "недельный ИПЦ", "бензин"],
            "topics_status": "confirmed",
            "staleness_note": None,
        },
        "pages": {
            1: spot_prose(
                title="Инфляция 25-31 августа: основные выводы",
                pub_date="2 сентября 2026 года",
                period="25–31 августа 2026",
                takeaway="За неделю 25–31.08 Росстат зафиксировал дефляцию −0,01% н/н",
                extra_regions=[CHART, CONTACTS],
            ),
        },
        "fragments": {
            "schema_version": 2,
            "document": "Inflation_tracker_02",
            "source_pdf": "data/bank_materials/raw/Inflation_tracker_02.pdf",
            "needs_reverification": False,
            "fragments": [
                {
                    "id": "infl_week_deflation",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "Inflation_tracker_02",
                    "page": 1,
                    "regions": [{"bbox": None}],
                    "ocr_text": (
                        "За прошедшую неделю (25.08-31.08) Росстат "
                        "зафиксировал дефляцию на 0,01% H/H"
                    ),
                    "exact_quote": (
                        "За прошедшую неделю (25.08-31.08) Росстат "
                        "зафиксировал дефляцию на 0,01% н/н"
                    ),
                    "ocr_correction": {
                        "from": "H/H",
                        "to": "н/н",
                        "basis": "visual_check_of_page_image",
                    },
                    "summary": None,
                    "verification_status": "verified",
                    "notes": (
                        "Fact as reported in bank material citing Rosstat; "
                        "Rosstat primary publication not opened here."
                    ),
                },
                {
                    "id": "infl_yoy",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "Inflation_tracker_02",
                    "page": 1,
                    "regions": [{"bbox": None}],
                    "ocr_text": "В — годовом выражении инфляция выросла до 6,32%.",
                    "exact_quote": "В годовом выражении инфляция выросла до 6,32%.",
                    "summary": None,
                    "verification_status": "verified",
                },
            ],
        },
    },
    "Бонд_Бриф_14092026": {
        "identity": {
            "confirmed_title": "Бонд Бриф: Итоги недели",
            "confirmed_title_status": "confirmed",
            "confirmed_publication_date": "2026-09-14",
            "confirmed_publication_date_status": "confirmed",
            "confirmed_publication_date_display": "14 сентября 2026",
            "period_covered": "неделя около 9–14 сентября 2026; заседание ЦБ 11.09",
            "period_covered_status": "confirmed",
            "topics": ["ОФЗ", "ключевая ставка", "аукционы Минфина", "долговой рынок"],
            "topics_status": "confirmed",
            "staleness_note": None,
        },
        "pages": {
            1: spot_prose(
                title="Бонд Бриф: Итоги недели",
                pub_date="14 сентября 2026",
                period="неделя с заседанием ЦБ 11.09.2026",
                takeaway=(
                    "Заседание ЦБ по ставке добавило долговому рынку негатива; "
                    "доходность ОФЗ выросла после паузы"
                ),
                extra_regions=[CHART, CONTACTS],
            ),
        },
        "fragments": {
            "schema_version": 2,
            "document": "Бонд_Бриф_14092026",
            "source_pdf": "data/bank_materials/raw/Бонд_Бриф_14092026.pdf",
            "needs_reverification": False,
            "fragments": [
                {
                    "id": "bond_cb_pause",
                    "kind": "exact_quote",
                    "content_type": "fact",
                    "source_document": "Бонд_Бриф_14092026",
                    "page": 1,
                    "regions": [{"bbox": None}],
                    "ocr_text": (
                        "В пятницу 11 сентября ЦБ ожидаемо сохранил ключевую ставку "
                        "на уровне 14,0%"
                    ),
                    "exact_quote": (
                        "В пятницу 11 сентября ЦБ ожидаемо сохранил ключевую ставку "
                        "на уровне 14,0%"
                    ),
                    "summary": None,
                    "verification_status": "verified",
                    "notes": (
                        "CBR decision as reported in this bank brief. "
                        "Source is this material, not an opened CBR primary link."
                    ),
                },
                {
                    "id": "bond_market_reaction",
                    "kind": "exact_quote",
                    "content_type": "interpretation",
                    "source_document": "Бонд_Бриф_14092026",
                    "page": 1,
                    "regions": [{"bbox": None, "note": "Headline"}],
                    "ocr_text": "Заседание ЦБ no ставке добавило долговому рынку негатива",
                    "exact_quote": "Заседание ЦБ по ставке добавило долговому рынку негатива",
                    "ocr_correction": {
                        "from": "no",
                        "to": "по",
                        "basis": "visual_check_of_page_image",
                    },
                    "summary": None,
                    "verification_status": "verified",
                },
            ],
        },
    },
}


def resolve_stem(key: str) -> Path:
    direct = OCR_ROOT / key
    if direct.is_dir():
        return direct
    matches = [p for p in OCR_ROOT.iterdir() if p.is_dir() and key in p.name]
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"OCR dir for {key!r} not found")


def apply_one(key: str) -> None:
    payload = QA[key]
    doc_dir = resolve_stem(key)
    set_identity(doc_dir, payload["identity"])
    checked: set[int] = set()
    for page, visual in (payload.get("pages") or {}).items():
        update_page_visual(doc_dir, int(page), visual)
        checked.add(int(page))
    fill_remaining_unverified(doc_dir, checked)
    if "fragments" in payload:
        set_fragments(doc_dir, payload["fragments"])
    print(f"applied QA: {doc_dir.name}", flush=True)


def main() -> int:
    keys = sys.argv[1:] or list(QA.keys())
    for key in keys:
        if key not in QA:
            print(f"no QA payload for {key}", file=sys.stderr)
            continue
        apply_one(key)

    from ocr_bank_materials_batch import write_corpus_manifest

    docs = []
    for man in sorted(OCR_ROOT.glob("*/manifest.json")):
        docs.append(load(man))
    write_corpus_manifest(OCR_ROOT, docs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
