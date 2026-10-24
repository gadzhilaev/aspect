"""Heuristic enrichment classification — offline fixtures (not live LLM quality)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.ingestion.enrich import heuristic_enrich
from app.services.public_news import event_type_label, severity_label


def _item(title: str, excerpt: str = "", *, publisher: str = "Test") -> SimpleNamespace:
    return SimpleNamespace(
        id="raw-1",
        title=title,
        excerpt=excerpt,
        publisher=publisher,
        published_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
        canonical_url="https://example.test/x",
        provider="rss",
    )


def test_cultural_official_agency_not_risk_macro():
    """выставки must not false-trigger «ставк» → key rate."""
    title = "История и искусство: в ФТС России открылись тематические экспозиции"
    excerpt = (
        "Праздничная программа и музейная экспозиция; выставки «Из истории таможенной Москвы»; "
        "художественная выставка «Россия — Родина моя»."
    )
    out = heuristic_enrich([_item(title, excerpt, publisher="Федеральная таможенная служба")])
    assert out.category == "other"
    assert out.event_type == "neutral"
    assert out.severity is None
    assert "cultural_or_ceremonial_notice" in out.classification_meta["matched_rules"]
    assert "RUB" not in out.currencies


def test_customs_word_alone_not_risk():
    out = heuristic_enrich(
        [_item("Пресс-служба таможни обновила контакты", "Справочная информация.")]
    )
    assert out.event_type == "neutral"
    assert out.severity is None


def test_enacted_export_restriction_is_risk():
    out = heuristic_enrich(
        [
            _item(
                "Введен запрет на экспорт отдельных категорий оборудования",
                "Санкции и export ban вступили в силу.",
            )
        ]
    )
    assert out.category == "geopolitics"
    assert out.event_type == "risk"
    assert out.severity == 75.0


def test_investigation_without_measure_not_high_risk():
    out = heuristic_enrich(
        [
            _item(
                "The Philippines launches safeguard investigation on pork",
                "WTO notice: investigation opened; no definitive measure yet.",
            )
        ]
    )
    assert out.event_type == "neutral"
    assert out.severity is None
    assert "investigation_without_measure" in out.classification_meta["matched_rules"]


def test_key_rate_not_confused_with_exhibition():
    out = heuristic_enrich(
        [
            _item(
                "ЦБ РФ сохранил ключевую ставку",
                "Банк России оставил ключевую ставку без изменения.",
            )
        ]
    )
    assert out.category == "macro"
    assert out.severity == 60.0
    assert out.event_type in {"market", "neutral", "opportunity"}


def test_neutral_statistics():
    out = heuristic_enrich(
        [_item("Росстат опубликовал статистику занятости", "Статистический бюллетень без мер.")]
    )
    assert out.category == "other"
    assert out.event_type == "neutral"
    assert out.severity is None


def test_severity_label_unknown_not_zero():
    assert severity_label(None) == "Важность не определена"
    assert event_type_label("neutral") == "Нейтрально"


def test_unknown_severity_not_coerced_in_public_card_contract():
    # Contract: label path accepts None; no fictitious numeric default here.
    assert severity_label(0.0) == "Обзор"  # known zero ≠ unknown
    assert severity_label(None) != severity_label(0.0)
