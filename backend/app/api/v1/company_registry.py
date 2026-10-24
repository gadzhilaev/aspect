"""External company registry lookup by INN + server-trusted confirmation.

- Lookup requires auth, takes only an INN, calls one fixed upstream, and creates
  no business entities (no Company, membership, case-link, Impact, Scenario, Decision).
- Confirmation lets the user create THEIR OWN working profile from public requisites.
  Knowing an INN never grants access to another user's existing Company.
- No LLM is involved anywhere in this module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models import (
    Company,
    CompanyMembership,
    CompanyProfileSettings,
    CompanyRegistryLookup,
    User,
)
from app.schemas.company import CompanySummaryOut
from app.schemas.company_registry import (
    CompanyRegistryConfirmIn,
    CompanyRegistryConfirmOut,
    CompanyRegistryLookupIn,
    CompanyRegistryLookupOut,
    RegistryCandidateOut,
    RegistrySourceOut,
)
from app.services.company_registry import provider, store
from app.services.company_registry.inn import InnValidationError, normalize_inn
from app.services.company_registry.provenance import (
    REGISTRY_PROVENANCE_KEY,
    build_provenance,
    company_fields_from_candidate,
)

router = APIRouter(prefix="/company-registry", tags=["company-registry"])

# Upstream outcome.kind → (error code, http status). ok/not_found/not_configured
# are returned as normal 200 states and are not in this map.
_FAILURE_MAP = {
    "timeout": ("REGISTRY_TIMEOUT", 504),
    "unavailable": ("REGISTRY_UNAVAILABLE", 503),
    # Never surface upstream 401/403 as our 401 — it must not log the user out.
    "auth_error": ("REGISTRY_AUTH_ERROR", 503),
    "rate_limited": ("REGISTRY_UPSTREAM_RATE_LIMITED", 503),
    "bad_response": ("REGISTRY_BAD_RESPONSE", 502),
}

_FAILURE_MESSAGES = {
    "timeout": "Справочник не ответил вовремя. Попробуйте позже или заполните вручную.",
    "unavailable": "Справочник временно недоступен. Попробуйте позже или заполните вручную.",
    "auth_error": "Доступ к справочнику не настроен корректно. Можно заполнить вручную.",
    "rate_limited": "Справочник ограничил частоту запросов. Попробуйте позже.",
    "bad_response": "Справочник вернул некорректный ответ. Можно заполнить вручную.",
}


def _summary(company: Company, role: str | None = None) -> CompanySummaryOut:
    return CompanySummaryOut(
        id=company.id,
        name=company.name,
        legal_name=company.legal_name,
        tax_id=company.tax_id,
        industry=company.industry,
        size_band=company.size_band,
        hq_region=company.hq_region,
        profile_status=company.profile_status,
        digital_twin_status=company.digital_twin_status,
        digital_twin_coverage=company.digital_twin_coverage,
        is_demo=company.is_demo,
        role=role,
    )


@router.post("/lookup", response_model=CompanyRegistryLookupOut)
def lookup_company(
    body: CompanyRegistryLookupIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompanyRegistryLookupOut:
    try:
        normalized = normalize_inn(body.inn)
    except InnValidationError as exc:
        raise AppError(
            "INVALID_INN", exc.message, 400, details=[{"reason": exc.reason, "field": "inn"}]
        ) from exc

    if not provider.check_user_rate(user.id):
        raise AppError(
            "RATE_LIMITED",
            "Слишком много запросов к справочнику. Подождите немного.",
            429,
            details=[{"reason": "user_rate_limited"}],
        )

    outcome = provider.lookup_inn(normalized.inn)

    if outcome.kind in _FAILURE_MAP:
        code, status = _FAILURE_MAP[outcome.kind]
        raise AppError(code, _FAILURE_MESSAGES[outcome.kind], status, details=[{"reason": outcome.kind}])

    source = RegistrySourceOut(**provider.SOURCE_INFO)

    if outcome.kind == "not_configured":
        return CompanyRegistryLookupOut(
            status="not_configured",
            query_inn=normalized.inn,
            note="Справочник не подключён. Заполните данные компании вручную.",
        )

    if outcome.kind == "not_found":
        return CompanyRegistryLookupOut(
            status="not_found",
            query_inn=normalized.inn,
            source=source,
            retrieved_at=(
                datetime.fromtimestamp(outcome.retrieved_at, tz=timezone.utc).isoformat()
                if outcome.retrieved_at
                else None
            ),
            source_actuality_date=outcome.source_actuality_date,
            note="По этому ИНН организация не найдена в справочнике.",
        )

    # ok
    row = store.create_lookup(db, user_id=user.id, inn=normalized.inn, outcome=outcome)
    db.commit()
    candidates = [RegistryCandidateOut(**c.to_public_dict()) for c in outcome.candidates]
    return CompanyRegistryLookupOut(
        status="ok",
        query_inn=normalized.inn,
        lookup_id=row.id,
        expires_at=row.expires_at.astimezone(timezone.utc).isoformat(),
        source=source,
        retrieved_at=(
            datetime.fromtimestamp(outcome.retrieved_at, tz=timezone.utc).isoformat()
            if outcome.retrieved_at
            else None
        ),
        source_actuality_date=outcome.source_actuality_date,
        candidate_count=len(candidates),
        candidates=candidates,
    )


@router.post("/confirm", response_model=CompanyRegistryConfirmOut)
def confirm_company(
    body: CompanyRegistryConfirmIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompanyRegistryConfirmOut:
    candidate, reason = store.get_candidate(
        db, user_id=user.id, lookup_id=body.lookup_id, candidate_id=body.candidate_id
    )
    if reason == "lookup_not_found":
        raise AppError("LOOKUP_NOT_FOUND", "Результат поиска не найден. Выполните поиск заново.", 404)
    if reason == "lookup_expired":
        raise AppError("LOOKUP_EXPIRED", "Результат поиска устарел. Выполните поиск заново.", 410)
    if reason == "candidate_not_found" or candidate is None:
        raise AppError("CANDIDATE_NOT_FOUND", "Выбранная организация не найдена в результате поиска.", 404)

    applied = company_fields_from_candidate(candidate)
    tax_id = applied.get("tax_id")

    # Dedupe ONLY within the user's own companies — never reveal others'.
    if tax_id:
        own = (
            db.query(Company)
            .join(CompanyMembership, CompanyMembership.company_id == Company.id)
            .filter(CompanyMembership.user_id == user.id, Company.tax_id == tax_id)
            .first()
        )
        if own is not None:
            membership = (
                db.query(CompanyMembership)
                .filter(
                    CompanyMembership.user_id == user.id,
                    CompanyMembership.company_id == own.id,
                )
                .first()
            )
            return CompanyRegistryConfirmOut(
                company=_summary(own, role=membership.role if membership else None),
                created=False,
                opened_existing=True,
                applied_fields=[],
                suggested_industry=candidate.get("suggested_industry"),
                source=RegistrySourceOut(**provider.SOURCE_INFO),
                note=(
                    "У вас уже есть профиль с этим ИНН — открыт существующий, "
                    "дубликат не создан."
                ),
            )

    # Create the user's own working profile from public requisites.
    company = Company(
        id=str(uuid4()),
        name=applied.get("name") or (tax_id or "Компания"),
        legal_name=applied.get("legal_name"),
        tax_id=tax_id,
        hq_region=applied.get("hq_region"),
        created_by=user.id,
        profile_status="draft",
    )
    db.add(company)
    db.add(
        CompanyMembership(
            id=str(uuid4()), user_id=user.id, company_id=company.id, role="owner"
        )
    )
    retrieved_iso = datetime.now(timezone.utc).isoformat()
    lookup_actuality = None
    lookup_row = db.get(CompanyRegistryLookup, body.lookup_id)
    if lookup_row is not None:
        lookup_actuality = lookup_row.source_actuality_date
        if lookup_row.retrieved_at is not None:
            retrieved_iso = lookup_row.retrieved_at.astimezone(timezone.utc).isoformat()
    provenance = build_provenance(
        candidate,
        source=provider.SOURCE_INFO,
        retrieved_at_iso=retrieved_iso,
        actuality=lookup_actuality,
        applied_fields=applied,
    )
    db.add(
        CompanyProfileSettings(
            id=str(uuid4()),
            company_id=company.id,
            purchase_currencies_json=[],
            optional_finance_json={},
            preferences_json={REGISTRY_PROVENANCE_KEY: provenance},
            warnings_json=[],
        )
    )
    db.commit()
    db.refresh(company)
    return CompanyRegistryConfirmOut(
        company=_summary(company, role="owner"),
        created=True,
        opened_existing=False,
        applied_fields=sorted(applied.keys()),
        suggested_industry=candidate.get("suggested_industry"),
        source=RegistrySourceOut(**provider.SOURCE_INFO),
        note=(
            "Создан ваш рабочий профиль по публичным реквизитам. Это не подтверждение "
            "владения компанией. Остальные поля заполните в мастере настройки."
        ),
    )
