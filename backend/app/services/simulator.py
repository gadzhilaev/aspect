"""Deterministic scenario simulator — same inputs always yield same outputs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import SolutionCandidate


def simulate(
    *,
    output_share_at_risk: float | None,
    inventory_days: int,
    delay_days: int,
    solution: SolutionCandidate | None,
) -> dict[str, Any]:
    settings = get_settings()
    missing: list[str] = []
    if output_share_at_risk is None:
        missing.append("output_share_at_risk")
    if inventory_days < 0:
        missing.append("inventory_days")
    if missing:
        raise AppError(
            "INSUFFICIENT_DATA",
            "Недостаточно данных для расчёта",
            422,
            details=[{"field": f, "reason": "required"} for f in missing],
        )

    assert output_share_at_risk is not None
    # Baseline: inventory covers delay partially
    uncovered = max(0, delay_days - inventory_days)
    baseline_stop_risk = round(
        min(100.0, output_share_at_risk * (0.35 + 0.65 * (uncovered / max(delay_days, 1)))),
        2,
    )
    baseline = {
        "label": "Без изменений",
        "stop_risk_percent": baseline_stop_risk,
        "cost_delta_percent": 0.0,
        "lead_time_days": delay_days,
        "assumptions": [
            "Запас расходуется линейно",
            "Доля выпуска, связанная с узлом, постоянна на горизонте расчёта",
            "stop_risk_percent — модельный индекс 0…100, не статистическая вероятность остановки",
            "Оценка, не финансовая гарантия",
        ],
        "stop_risk_kind": "model_index",
        "stop_risk_label": "Модельная оценка риска остановки",
    }

    if solution is None:
        alternative = None
        comparison = None
    else:
        alt_uncovered = max(0, solution.lead_time_days - inventory_days)
        alt_stop = round(
            min(
                100.0,
                output_share_at_risk
                * (0.15 + 0.55 * (alt_uncovered / max(solution.lead_time_days, 1)))
                * (solution.risk_percent / 100),
            ),
            2,
        )
        alternative = {
            "label": solution.name,
            "solution_id": solution.id,
            "country": solution.country,
            "stop_risk_percent": alt_stop,
            "cost_delta_percent": solution.cost_delta_percent,
            "lead_time_days": solution.lead_time_days,
            "compatibility": solution.compatibility,
            "risk_percent": solution.risk_percent,
            "assumptions": [
                "Альтернатива — демонстрационная оценка",
                "Совместимость и сроки не подтверждены поставщиком",
                "Оценка, не финансовая гарантия",
            ],
            "is_demo": solution.is_demo,
        }
        comparison = {
            "stop_risk_delta": round(alt_stop - baseline_stop_risk, 2),
            "cost_delta_percent": solution.cost_delta_percent,
            "lead_time_delta_days": solution.lead_time_days - delay_days,
            "tradeoff": _tradeoff(solution, baseline_stop_risk, alt_stop),
        }

    return {
        "model_version": settings.simulator_model_version,
        "computed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "is_estimate": True,
        "parameters": {
            "output_share_at_risk": output_share_at_risk,
            "inventory_days": inventory_days,
            "delay_days": delay_days,
            "solution_id": solution.id if solution else None,
        },
        "baseline": baseline,
        "alternative": alternative,
        "comparison": comparison,
    }


def _tradeoff(solution: SolutionCandidate, baseline_risk: float, alt_risk: float) -> str:
    parts: list[str] = []
    if alt_risk < baseline_risk:
        parts.append("меньше риск остановки")
    if solution.cost_delta_percent > 0:
        parts.append("выше себестоимость")
    elif solution.cost_delta_percent < 0:
        parts.append("ниже себестоимость")
    if solution.lead_time_days > 30:
        parts.append("длиннее срок поставки")
    return " — ".join(parts) if parts else "сопоставимо с базовым сценарием"


def rank_solutions(solutions: list[SolutionCandidate]) -> list[SolutionCandidate]:
    """Explainable sort: lower risk, shorter lead, moderate cost, higher compatibility."""
    for s in solutions:
        risk_score = 100 - s.risk_percent
        lead_score = max(0, 100 - s.lead_time_days)
        cost_score = max(0, 100 - abs(s.cost_delta_percent) * 4)
        compat_score = s.compatibility * 100
        total = 0.35 * risk_score + 0.25 * lead_score + 0.20 * cost_score + 0.20 * compat_score
        s.sort_score = round(total, 2)
        s.sort_breakdown_json = {
            "risk": {"value": risk_score, "weight": 0.35},
            "lead_time": {"value": lead_score, "weight": 0.25},
            "cost": {"value": cost_score, "weight": 0.20},
            "compatibility": {"value": compat_score, "weight": 0.20},
            "total": s.sort_score,
            "note": "Система не выбирает «лучшего» — показывает компромиссы",
        }
    return sorted(solutions, key=lambda x: -x.sort_score)
