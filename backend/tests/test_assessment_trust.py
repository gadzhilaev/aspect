"""Regression: assessment semantics, missing vs zero, provenance, ACL."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Company, CompanyNode, Event, EventImpact
from app.services.assessment_explain import (
    EVENT_SEVERITY_SIGNAL_LABEL,
    EXPOSURE_LABEL,
    IMPACT_SCORE_LABEL,
    IMPACT_SCORE_MEANING,
    SCORE_KIND_COMPANY,
    SCORE_KIND_SEVERITY,
    explanation_from_impact,
)
from app.services.impact import (
    compute_confidence,
    compute_confidence_detail,
    compute_impact_score,
    recompute_company_impact,
)
from app.services.assistant.context_builder import build_conversation_context, slim_live_context
from app.services.assistant.provider import MockAssistantProvider
from app.services.simulator import simulate

COMPANY_ID = "cmp_severprom"
EVENT_CHINA = "evt_china_export_001"
EVENT_RATE = "evt_rate_hike_001"


def test_confidence_stays_0_1_not_percent():
    sources = []
    conf = compute_confidence(sources, [0.9, 0.8])
    assert 0.0 <= conf <= 1.0
    assert conf < 2.0  # never "already percent"


def test_confidence_defaults_are_explicit_in_detail():
    value, detail = compute_confidence_detail([], [])
    assert detail["is_heuristic"] is True
    assert detail["source_quality_defaulted"] is True
    assert detail["edge_confidence_defaulted"] is True
    assert detail["default_source_quality_if_no_sources"] == 0.4
    assert detail["default_edge_confidence_if_no_edges"] == 0.5
    assert "0.55" in detail["formula"]
    # 0.55*0.4 + 0.45*0.5 = 0.22 + 0.225 = 0.445
    assert value == 0.445


def test_impact_score_formula_uses_config_weights():
    score, breakdown = compute_impact_score(
        severity=100, exposure=100, dependency_criticality=100, propagation_proximity=100
    )
    assert score == 100
    assert "0.40×severity" in breakdown["formula"] or "×severity" in breakdown["formula"]
    assert "×exposure" in breakdown["formula"]
    assert "exposure_norm" not in breakdown["formula"]
    assert breakdown["exposure"].get("note")


def test_exposure_label_is_share_not_loss(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_CHINA)
    assert company and event
    impact = recompute_company_impact(db, event, company)
    db.commit()
    assert impact.exposure_value is not None
    assert impact.exposure_label == EXPOSURE_LABEL
    assert "потер" not in (impact.exposure_label or "").lower()
    basis = (impact.score_breakdown_json or {}).get("assessment_basis") or {}
    assert basis.get("basis_available") is True
    text = " ".join(str(x) for x in (basis.get("limitations") or []))
    assert "не" in text.lower() and ("потер" in text.lower() or "прогноз" in text.lower())


def test_china_demo_uses_unified_formula_no_hidden_override(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_CHINA)
    assert company and event
    impact = recompute_company_impact(db, event, company)
    db.commit()
    breakdown = impact.score_breakdown_json or {}
    override = breakdown.get("demo_score_override") or {}
    assert override.get("applied") is False
    basis = breakdown.get("assessment_basis") or {}
    assert (basis.get("demo_score_override") or {}).get("applied") is False
    # No hidden ×3.5 / soft 100/24 — score matches raw share in formula inputs
    expected, _ = compute_impact_score(
        severity=event.severity,
        exposure=min(100.0, float(impact.exposure_value)),
        dependency_criticality=breakdown["dependency_criticality"]["value"],
        propagation_proximity=breakdown["propagation_proximity"]["value"],
    )
    assert impact.impact_score == expected
    assert breakdown.get("score_kind") == SCORE_KIND_COMPANY
    assert basis.get("score_kind") == SCORE_KIND_COMPANY


def test_demo_override_not_applied_to_real_events(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_CHINA)
    assert company and event
    # Clone-like: recompute after flipping is_demo off (same graph match)
    was_demo = event.is_demo
    event.is_demo = False
    db.flush()
    try:
        impact = recompute_company_impact(db, event, company)
        db.commit()
        override = (impact.score_breakdown_json or {}).get("demo_score_override") or {}
        assert override.get("applied") is False
        assert "3.5" not in str(impact.score_breakdown_json)
    finally:
        event.is_demo = was_demo
        db.commit()


def test_finance_placeholder_is_severity_signal_not_company_calc(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_RATE)
    assert company and event
    impact = recompute_company_impact(db, event, company)
    db.commit()
    state = (impact.score_breakdown_json or {}).get("assessment_state")
    assert state in {"finance_data_required", "finance_ready", "monitoring_only"}
    kind = (impact.score_breakdown_json or {}).get("score_kind")
    assert kind == SCORE_KIND_SEVERITY
    basis = (impact.score_breakdown_json or {}).get("assessment_basis") or {}
    assert basis.get("score_kind") == SCORE_KIND_SEVERITY
    assert basis.get("score_kind_label") == EVENT_SEVERITY_SIGNAL_LABEL
    calc = (basis.get("calculation") or "").lower()
    assert "персональн" in calc or "placeholder" in calc or "severity" in calc
    # Metric label must not pretend to be company impact index
    impact_metric = next(m for m in basis["metrics"] if m["key"] == "impact_score")
    assert impact_metric["label"] == EVENT_SEVERITY_SIGNAL_LABEL
    assert IMPACT_SCORE_LABEL not in impact_metric["label"] or kind == SCORE_KIND_COMPANY


def test_zero_exposure_distinct_from_null(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_CHINA)
    assert company and event
    line = (
        db.query(CompanyNode)
        .filter(
            CompanyNode.company_id == COMPANY_ID,
            CompanyNode.name == "Линия №2",
        )
        .one()
    )
    original = line.output_share_percent
    line.output_share_percent = 0.0
    db.flush()
    try:
        impact = recompute_company_impact(db, event, company)
        db.commit()
        assert impact.exposure_value == 0.0
        assert impact.exposure_label == EXPOSURE_LABEL
        state = (impact.score_breakdown_json or {}).get("assessment_state")
        assert state == "supply_chain_ready"
        assert (impact.score_breakdown_json or {}).get("score_kind") == SCORE_KIND_COMPANY
    finally:
        line.output_share_percent = original
        db.commit()


def test_macro_exposure_is_null_not_zero(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_RATE)
    assert company and event
    impact = recompute_company_impact(db, event, company)
    db.commit()
    assert impact.exposure_value is None
    assert impact.exposure_label is None


def test_finance_event_has_no_supply_chain_paths(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_RATE)
    assert company and event
    impact = recompute_company_impact(db, event, company)
    db.commit()
    state = (impact.score_breakdown_json or {}).get("assessment_state")
    assert state in {"finance_data_required", "finance_ready", "monitoring_only"}
    if state != "supply_chain_ready":
        assert impact.exposure_value is None


def test_confidence_defaults_reflected_in_explanation(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_RATE)
    assert company and event
    impact = recompute_company_impact(db, event, company)
    db.commit()
    basis = (impact.score_breakdown_json or {}).get("assessment_basis") or {}
    detail = basis.get("confidence_detail") or {}
    # Finance/monitoring wipe paths → edge default applies
    assert detail.get("edge_confidence_defaulted") is True
    conf_metric = next(m for m in basis["metrics"] if m["key"] == "confidence")
    meaning = conf_metric["meaning"].lower()
    assert "эвристич" in meaning or "0.55" in meaning
    assert "вероятност" not in meaning or "не вероятност" in meaning
    assert "default" in meaning


def test_stop_risk_is_model_index_not_probability():
    result = simulate(output_share_at_risk=24.0, inventory_days=14, delay_days=45, solution=None)
    assert "stop_risk_percent" in result["baseline"]
    assert result["baseline"].get("stop_risk_kind") == "model_index"
    assumptions = " ".join(result["baseline"].get("assumptions") or [])
    assert "модел" in assumptions.lower() or "не статистическ" in assumptions.lower()


def test_legacy_impact_without_basis_is_honest(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_CHINA)
    assert company and event
    impact = (
        db.query(EventImpact)
        .filter(EventImpact.event_id == EVENT_CHINA, EventImpact.company_id == COMPANY_ID)
        .first()
    )
    assert impact
    # Simulate legacy row
    impact.score_breakdown_json = {"assessment_state": "supply_chain_ready"}
    db.commit()
    expl = explanation_from_impact(impact, event)
    assert expl["basis_available"] is False
    assert "не зафиксировано" in expl["summary"].lower() or "недоступ" in expl["summary"].lower()
    assert any(m["key"] == "impact_score" for m in expl["metrics"])
    meaning = next(m["meaning"] for m in expl["metrics"] if m["key"] == "impact_score")
    assert "не процент потерь" in meaning.lower() or IMPACT_SCORE_MEANING[:20] in meaning


def test_impact_api_returns_score_kind_and_acl(
    client: TestClient, auth_headers: dict, db: Session
):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_CHINA)
    assert company and event
    recompute_company_impact(db, event, company)
    db.commit()

    ok = client.get(
        f"/api/v1/events/{EVENT_CHINA}/impact",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert ok.status_code == 200
    body = ok.json()
    assert "assessment_explanation" in body
    expl = body["assessment_explanation"]
    assert expl["basis_available"] is True
    assert body["score_kind"] == SCORE_KIND_COMPANY
    assert body["score_kind_label"] == IMPACT_SCORE_LABEL
    assert body["metric_labels"]["impact_score"] == IMPACT_SCORE_LABEL
    assert body["metric_labels"]["confidence"]
    assert body["assessment_explanation"]["score_kind"] == SCORE_KIND_COMPANY
    if body.get("exposure"):
        assert "связан" in body["exposure"]["label"].lower() or "доля" in body["exposure"]["label"].lower()
        assert "потер" not in body["exposure"]["label"].lower()

    rate = db.get(Event, EVENT_RATE)
    assert rate
    recompute_company_impact(db, rate, company)
    db.commit()
    finance = client.get(
        f"/api/v1/events/{EVENT_RATE}/impact",
        params={"company_id": COMPANY_ID},
        headers=auth_headers,
    )
    assert finance.status_code == 200
    fbody = finance.json()
    assert fbody["score_kind"] == SCORE_KIND_SEVERITY
    assert fbody["metric_labels"]["impact_score"] == EVENT_SEVERITY_SIGNAL_LABEL
    assert fbody["exposure"] is None

    denied = client.get(
        f"/api/v1/events/{EVENT_CHINA}/impact",
        params={"company_id": "cmp_someone_else"},
        headers=auth_headers,
    )
    assert denied.status_code in {403, 404}


def test_assistant_context_carries_score_kind_and_semantics(db: Session):
    company = db.get(Company, COMPANY_ID)
    event = db.get(Event, EVENT_CHINA)
    assert company and event
    recompute_company_impact(db, event, company)
    db.commit()
    full = build_conversation_context(db, event_id=EVENT_CHINA, company_id=COMPANY_ID)
    assert full["impact"]["score_kind"] == SCORE_KIND_COMPANY
    assert "score_kind" in full["metric_semantics"]
    assert full["impact"]["assessment_explanation"]["basis_available"] is True
    slim = slim_live_context(full)
    assert "score_kind" in slim["instruction"]
    assert slim["impact_results"].get("score_kind") == SCORE_KIND_COMPANY
    assert slim["impact_results"].get("assessment_explanation")

    recompute_company_impact(db, db.get(Event, EVENT_RATE), company)
    db.commit()
    finance_ctx = build_conversation_context(db, event_id=EVENT_RATE, company_id=COMPANY_ID)
    assert finance_ctx["impact"]["score_kind"] == SCORE_KIND_SEVERITY
    assert "event_severity" in finance_ctx["metric_semantics"]["impact_score"]


def test_mock_provider_does_not_claim_chain_without_paths():
    provider = MockAssistantProvider()
    context = {
        "company": {"name": "СеверПром"},
        "event": {"title": "Тест", "is_demo": True, "labels": ["demo"]},
        "impact": {
            "impact_score": 40,
            "confidence": 0.7,
            "reason_summary": "Мониторинг",
            "exposure_value": None,
            "assessment_state": "monitoring_only",
            "score_kind": SCORE_KIND_SEVERITY,
            "score_kind_label": EVENT_SEVERITY_SIGNAL_LABEL,
            "claims": {},
        },
        "paths": [],
        "assessment_state": "monitoring_only",
        "sources": [],
        "solutions": [],
    }
    result = provider.generate(
        context=context,
        history=[],
        user_text="Почему это касается компании?",
    )
    lower = result.content.lower()
    assert "по найденной цепочке" not in lower
    assert "цепочки зависимостей сейчас нет" in lower or "цепочки влияния нет" in lower
    assert "сигнал события" in lower
    assert "персональн" in lower
    assert "качеств" in lower
