"""Merge impact-based personal feed with case-profile matches (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Company, CompanyProfileSettings, Event, EventImpact, EventSource, User
from app.schemas.event import (
    EventCardOut,
    ExposureOut,
    PersonalFeedEmptyOut,
    ProfileRelevanceMatchOut,
    ProfileRelevanceOut,
    ProfileRelevanceProvenanceOut,
)
from app.services.assessment_explain import metric_labels, score_kind_label
from app.services.case_profile_relevance import (
    CaseProductSnapshot,
    ProfileRelevanceResult,
    evaluate_events_profile_relevance,
    product_snapshot_from_case_context,
)
from app.services.company_context import build_case_context_block

# Feed groups — lower sorts first. Do not compare scores across groups.
FEED_KIND_GROUP: dict[str, int] = {
    "company_calculated": 0,
    "event_severity_signal": 1,
    "case_profile_match": 2,
    "unavailable": 3,
}
FEED_GROUP_NAME: dict[int, str] = {v: k for k, v in FEED_KIND_GROUP.items()}

FEED_SORT_RULE = (
    "Groups: company_calculated, then event_severity_signal, then case_profile_match; "
    "within impact groups impact_score DESC; within case_profile_match occurred_at DESC; "
    "tie-break event_id ASC. Mixed bases are not compared by one number. "
    "Cursor format: '{group}:{sort_key}:{event_id}' "
    "(legacy '{group}:{sort_key}' or bare score = end of that sort_key bucket). "
    "One event appears once; profile explanations attach when matched."
)

INCLUSION_CALCULATED = "calculated_impact"
INCLUSION_SEVERITY = "event_severity_signal"
INCLUSION_PROFILE = "case_profile"


@dataclass
class FeedEntry:
    event_id: str
    score_kind: str
    sort_key: float  # DESC within group
    card: EventCardOut


@dataclass(frozen=True)
class FeedCursor:
    group: int
    sort_key: float
    event_id: str | None  # None ⇒ legacy: skip entire equal sort_key bucket


def feed_group(kind: str) -> int:
    return FEED_KIND_GROUP.get(kind, 9)


def parse_feed_cursor(cursor: str | None) -> FeedCursor | None:
    """Parse cursor; raise AppError 422 on malformed values."""
    if not cursor:
        return None
    parts = cursor.split(":")
    try:
        if len(parts) == 1:
            return FeedCursor(group=0, sort_key=float(parts[0]), event_id=None)
        if len(parts) == 2:
            return FeedCursor(
                group=int(parts[0]), sort_key=float(parts[1]), event_id=None
            )
        if len(parts) == 3:
            event_id = parts[2]
            if not event_id:
                raise ValueError("empty event_id")
            return FeedCursor(
                group=int(parts[0]), sort_key=float(parts[1]), event_id=event_id
            )
    except ValueError as exc:
        raise AppError("VALIDATION_ERROR", "Некорректный cursor ленты", 422) from exc
    raise AppError("VALIDATION_ERROR", "Некорректный cursor ленты", 422)


def feed_cursor_of(kind: str, sort_key: float, event_id: str) -> str:
    return f"{feed_group(kind)}:{sort_key}:{event_id}"


def _priority(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _occurred_sort_key(event: Event) -> float:
    oc = event.occurred_at
    if oc is None:
        return 0.0
    if oc.tzinfo is None:
        oc = oc.replace(tzinfo=timezone.utc)
    return oc.timestamp()


def _profile_out(
    result: ProfileRelevanceResult,
    products: CaseProductSnapshot,
) -> ProfileRelevanceOut | None:
    if not result.matched:
        return None
    prov = None
    if products.provenance or products.snapshot_id:
        p = products.provenance or {}
        prov = ProfileRelevanceProvenanceOut(
            snapshot_id=products.snapshot_id or p.get("snapshot_id"),
            version_label=products.version_label or p.get("version_label"),
            version_seq=products.version_seq
            if products.version_seq is not None
            else p.get("version_seq"),
            source_file=p.get("source_file"),
            source_row_numbers=list(p.get("source_row_numbers") or []),
            external_uid=products.external_uid,
        )
    return ProfileRelevanceOut(
        matched=True,
        label="По профилю компании",
        summary=result.summary,
        matches=[
            ProfileRelevanceMatchOut(
                rule_id=m.rule_id,
                theme=m.theme,
                product_code=m.product_code,
                product_label=m.product_label,
                product_status=m.product_status,
                explanation=m.explanation,
                event_theme_signals=list(m.event_theme_signals),
                limitations=list(m.limitations),
            )
            for m in result.matches
        ],
        limitations=list(result.limitations),
        provenance=prov,
    )


def load_product_snapshot(
    db: Session, *, company: Company, user: User
) -> CaseProductSnapshot:
    """Single case_context read for the request — never per event."""
    case_block = build_case_context_block(db, company=company, user=user)
    return product_snapshot_from_case_context(case_block)


def card_from_impact(
    event: Event,
    impact: EventImpact,
    source_count: int,
    *,
    assessment_state: str,
    score_kind: str,
    profile: ProfileRelevanceResult | None = None,
    products: CaseProductSnapshot | None = None,
) -> EventCardOut:
    exposure = None
    if impact.exposure_value is not None:
        exposure = ExposureOut(
            label=impact.exposure_label or "Доля выпуска, связанная с затронутым узлом",
            value=float(impact.exposure_value),
            unit=impact.exposure_unit or "percent",
        )
    state = assessment_state or "monitoring_only"
    labels = metric_labels(
        has_exposure=exposure is not None,
        assessment_state=state,
        score_kind=score_kind,
    )
    bases: list[str] = []
    if score_kind == "company_calculated":
        bases.append(INCLUSION_CALCULATED)
    elif score_kind == "event_severity_signal":
        bases.append(INCLUSION_SEVERITY)
    elif score_kind == "unavailable":
        bases.append("unavailable")
    else:
        bases.append(INCLUSION_CALCULATED)

    profile_out = None
    if profile is not None and profile.matched and products is not None:
        profile_out = _profile_out(profile, products)
        if INCLUSION_PROFILE not in bases:
            bases.append(INCLUSION_PROFILE)

    score = float(impact.impact_score)
    return EventCardOut(
        id=event.id,
        title=event.title,
        category=event.category,
        priority=_priority(score),
        impact_score=score,
        impact_score_available=True,
        urgency=impact.urgency,
        confidence=float(impact.confidence),
        reason_summary=impact.reason_summary,
        exposure=exposure,
        claims=impact.claims_json or {},
        source_count=source_count,
        updated_at=impact.computed_at,
        status=impact.status,
        is_demo=event.is_demo,
        assessment_state=state,
        metric_labels=labels,
        score_kind=score_kind,
        score_kind_label=labels.get("impact_score") or score_kind_label(score_kind),
        inclusion_bases=bases,
        profile_relevance=profile_out,
    )


def card_from_profile(
    event: Event,
    source_count: int,
    *,
    profile: ProfileRelevanceResult,
    products: CaseProductSnapshot,
) -> EventCardOut:
    """Profile-only card — no assessment value; impact_score is null."""
    profile_out = _profile_out(profile, products)
    assert profile_out is not None
    kind = "case_profile_match"
    labels = {
        "impact_score": "По профилю компании",
        "confidence": "Не оценка качества расчёта",
    }
    return EventCardOut(
        id=event.id,
        title=event.title,
        category=event.category,
        priority="medium",
        impact_score=None,
        impact_score_available=False,
        urgency="watch",
        confidence=0.0,
        reason_summary=profile.summary,
        exposure=None,
        claims={},
        source_count=source_count,
        updated_at=event.occurred_at or datetime.now(timezone.utc),
        status="profile_match",
        is_demo=event.is_demo,
        assessment_state="calculation_unavailable",
        metric_labels=labels,
        score_kind=kind,
        score_kind_label="По профилю компании",
        inclusion_bases=[INCLUSION_PROFILE],
        profile_relevance=profile_out,
    )


def build_merged_feed_entries(
    db: Session,
    *,
    company_id: str,
    impact_rows: list[tuple[EventImpact, str, str]],
    products: CaseProductSnapshot,
    score_kind_of: Callable[[EventImpact, str], str],
) -> list[FeedEntry]:
    """Merge active impacts with profile-only matches; one card per event_id."""
    impact_by_event = {row[0].event_id: row for row in impact_rows}
    active_events = db.query(Event).filter(Event.status == "active").all()
    profile_by_event = evaluate_events_profile_relevance(active_events, products)

    event_ids = [e.id for e in active_events]
    src_counts: dict[str, int] = {eid: 0 for eid in event_ids}
    if event_ids:
        rows = (
            db.query(EventSource.event_id, EventSource.id)
            .filter(EventSource.event_id.in_(event_ids))
            .all()
        )
        for eid, _sid in rows:
            src_counts[eid] = src_counts.get(eid, 0) + 1

    events_by_id = {e.id: e for e in active_events}
    entries: list[FeedEntry] = []
    seen: set[str] = set()

    for impact, state, kind in impact_rows:
        event = events_by_id.get(impact.event_id) or db.get(Event, impact.event_id)
        if event is None:
            continue
        kind = kind or score_kind_of(impact, state)
        pref = profile_by_event.get(event.id)
        card = card_from_impact(
            event,
            impact,
            src_counts.get(event.id, 0),
            assessment_state=state,
            score_kind=kind,
            profile=pref if pref and pref.matched else None,
            products=products if pref and pref.matched else None,
        )
        entries.append(
            FeedEntry(
                event_id=event.id,
                score_kind=kind,
                sort_key=float(impact.impact_score),
                card=card,
            )
        )
        seen.add(event.id)

    for event in active_events:
        if event.id in seen:
            continue
        pref = profile_by_event.get(event.id)
        if pref is None or not pref.matched:
            continue
        if event.id in impact_by_event:
            continue
        card = card_from_profile(
            event,
            src_counts.get(event.id, 0),
            profile=pref,
            products=products,
        )
        entries.append(
            FeedEntry(
                event_id=event.id,
                score_kind="case_profile_match",
                sort_key=_occurred_sort_key(event),
                card=card,
            )
        )
        seen.add(event.id)

    # ORDER BY group ASC, sort_key DESC, event_id ASC
    entries.sort(
        key=lambda e: (
            feed_group(e.score_kind),
            -e.sort_key,
            e.event_id,
        )
    )
    return entries


def entry_after_cursor(entry: FeedEntry, cur: FeedCursor) -> bool:
    """True if entry strictly follows the cursor position in feed order."""
    g = feed_group(entry.score_kind)
    if g > cur.group:
        return True
    if g < cur.group:
        return False
    # same group — sort_key DESC
    if entry.sort_key < cur.sort_key:
        return True
    if entry.sort_key > cur.sort_key:
        return False
    # same sort_key
    if cur.event_id is None:
        # Legacy cursor: end of this sort_key bucket (may skip unseen equals).
        return False
    return entry.event_id > cur.event_id


def apply_feed_cursor(
    entries: list[FeedEntry], cursor: str | None
) -> list[FeedEntry]:
    cur = parse_feed_cursor(cursor)
    if cur is None:
        return entries
    return [e for e in entries if entry_after_cursor(e, cur)]


def _has_finance_or_purchase_ccy(db: Session, company_id: str) -> bool:
    settings = (
        db.query(CompanyProfileSettings)
        .filter(CompanyProfileSettings.company_id == company_id)
        .one_or_none()
    )
    if settings is None:
        return False
    ccy = [str(c).strip() for c in (settings.purchase_currencies_json or []) if str(c).strip()]
    if ccy:
        return True
    fin = settings.optional_finance_json
    if not isinstance(fin, dict) or not fin:
        return False
    rate_ok = fin.get("debt_amount") not in (None, "") and fin.get(
        "floating_rate_share_percent"
    ) not in (None, "")
    fx_ok = all(
        fin.get(k) not in (None, "")
        for k in (
            "fx_exposure_amount",
            "fx_exposure_currency",
            "fx_exposure_direction",
            "fx_quote_currency",
        )
    )
    return bool(rate_ok or fx_ok)


def describe_personal_feed_empty(
    db: Session,
    *,
    company: Company,
    node_count: int,
    feed_card_count: int,
) -> PersonalFeedEmptyOut | None:
    """Explain an empty personal feed without writing or inventing cards."""
    if feed_card_count > 0:
        return None

    twin = (company.digital_twin_status or "not_built").strip().lower()
    profile = (company.profile_status or "draft").strip().lower()

    if profile != "ready" or node_count == 0:
        return PersonalFeedEmptyOut(
            reason="profile_incomplete",
            title="Не хватает данных компании",
            detail=(
                "Персональная лента строится по вашей цепочке и (для макро) "
                "по финансовому профилю. Завершите настройку компании — "
                "вход в аккаунт сам по себе расчёт влияния не добавляет."
            ),
            primary_href="/company/setup",
            primary_label="Настроить компанию",
            secondary_href="/news",
            secondary_label="Все новости",
        )

    if twin in {"not_built", ""}:
        return PersonalFeedEmptyOut(
            reason="twin_not_built",
            title="Нужен явный пересчёт модели",
            detail=(
                "Профиль заполнен, но модель влияния ещё не собрана. "
                "Пересчёт запускается при завершении настройки (сборка Digital Twin), "
                "а не при каждом входе в аккаунт."
            ),
            primary_href="/company/setup",
            primary_label="Завершить настройку",
            secondary_href="/news",
            secondary_label="Все новости",
        )

    has_fin = _has_finance_or_purchase_ccy(db, company.id)
    finance_hint = ""
    if not has_fin:
        finance_hint = (
            " Для новостей о ключевой ставке или валюте дополнительно нужны "
            "параметры финансового профиля или валюты закупок — без этого "
            "макро-события в «Для вас» не появятся."
        )

    return PersonalFeedEmptyOut(
        reason="no_matching_published_news",
        title="Пока нет персональных совпадений",
        detail=(
            "Модель компании собрана, среди опубликованных новостей нет "
            "пересечения с вашей цепочкой поставок."
            + finance_hint
            + " Общая лента доступна без персонального расчёта."
        ),
        primary_href="/news",
        primary_label="Все новости",
        secondary_href="/company/setup?step=finance" if not has_fin else "/company",
        secondary_label="Финансовый профиль" if not has_fin else "Профиль компании",
    )
