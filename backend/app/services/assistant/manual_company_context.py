"""Manual Company / Digital Twin context for the assistant agent loop.

Independent of case-org link and EventImpact. Read-only; does not invent
confirmed chains for unknown/missing nodes. Does not substitute demo profiles.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Company, CompanyEdge, CompanyNode, User
from app.services.company_context import build_company_context


_UNKNOWN_NODE_STATUSES = frozenset({"unknown", "draft", "inactive", "archived"})


def _node_known(node: CompanyNode) -> bool:
    status = (node.status or "active").strip().lower()
    if status in _UNKNOWN_NODE_STATUSES:
        return False
    name = (node.name or "").strip()
    return bool(name)


def build_manual_company_context_block(
    db: Session,
    *,
    company: Company,
    user: User | None = None,
) -> dict[str, Any]:
    """Structured manual twin block for tools / projections.

    Uses the same node/edge tables as ``build_company_context``. Case-link and
    impact are intentionally ignored. Demo companies are labelled, never
    replaced with another company's profile.
    """
    nodes = db.query(CompanyNode).filter(CompanyNode.company_id == company.id).all()
    edges = db.query(CompanyEdge).filter(CompanyEdge.company_id == company.id).all()

    known_nodes: list[dict[str, Any]] = []
    unknown_or_skipped: list[str] = []
    by_id: dict[str, CompanyNode] = {}
    for n in nodes:
        by_id[n.id] = n
        if not _node_known(n):
            unknown_or_skipped.append(
                f"node:{n.node_type or 'unknown'}:status={n.status or 'empty'}"
            )
            continue
        item: dict[str, Any] = {
            "node_type": n.node_type,
            "name": n.name.strip(),
        }
        if n.country:
            item["country"] = n.country
        if n.region:
            item["region"] = n.region
        if n.output_share_percent is not None:
            # Stored on node — UI historically defaulted empty line share to 24;
            # do not claim «user-confirmed» without separate provenance evidence.
            item["output_share_percent"] = float(n.output_share_percent)
            item["output_share_percent_provenance"] = "stored_on_node_origin_unverified"
        attrs = n.attributes_json if isinstance(n.attributes_json, dict) else {}
        if isinstance(attrs.get("business_role"), str) and attrs["business_role"].strip():
            item["business_role"] = attrs["business_role"].strip()
        if isinstance(attrs.get("countries"), list):
            countries = [str(c) for c in attrs["countries"] if c]
            if countries:
                item["countries"] = countries[:8]
        known_nodes.append(item)

    known_edges: list[dict[str, Any]] = []
    for e in edges:
        fr = by_id.get(e.from_node_id)
        to = by_id.get(e.to_node_id)
        if fr is None or to is None or not _node_known(fr) or not _node_known(to):
            # Do not present incomplete edges as a confirmed chain.
            unknown_or_skipped.append(
                f"edge:{e.relation_type}:incomplete_endpoints"
            )
            continue
        known_edges.append(
            {
                "relation": e.relation_type,
                "from": {"node_type": fr.node_type, "name": fr.name.strip()},
                "to": {"node_type": to.node_type, "name": to.name.strip()},
            }
        )

    # Human coverage summary via existing UI builder (ACL-safe when user given).
    coverage_summary: dict[str, Any] | None = None
    tracking: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    if user is not None:
        try:
            ctx = build_company_context(db, company=company, user=user)
            coverage_summary = {
                "filled": ctx.coverage_filled,
                "total": ctx.coverage_total,
                "profile_ready": ctx.profile_ready,
                "industry_label": ctx.industry_label,
                "hq_region": ctx.hq_region,
                "business_role": ctx.business_role,
                "size_label": ctx.size_label,
            }
            tracking = [
                {
                    "key": t.key,
                    "title": t.title,
                    "values": list(t.values or [])[:8],
                }
                for t in (ctx.tracking or [])
            ]
            gaps = [
                {
                    "key": g.key,
                    "title": g.title,
                    "filled": False,
                }
                for g in (ctx.tracking_gaps or [])
            ]
        except Exception:  # noqa: BLE001 — tool must degrade, not crash turn
            coverage_summary = None

    twin_status = (company.digital_twin_status or "not_built").strip().lower()
    has_graph = bool(known_nodes)
    if twin_status == "ready" and has_graph:
        availability = "available"
        status = "ok"
        explanation = (
            "Доступен ручной профиль Digital Twin компании (узлы и связи). "
            "Это не конкурсный case-профиль и не расчёт EventImpact."
        )
    elif has_graph:
        availability = "partial"
        status = "partial"
        explanation = (
            "В ручном twin есть известные узлы, но статус twin не ready "
            "или покрытие неполное. Неизвестные поля не подтверждайте."
        )
    else:
        availability = "unavailable"
        status = "empty_or_unbuilt"
        explanation = (
            "Ручной Digital Twin не содержит известных узлов. "
            "Это не означает, что компания «не существует» — данных twin "
            "для сопоставления с новостью сейчас нет. "
            "Не утверждайте, что профиль пользователя пуст целиком, "
            "если не вызывали этот инструмент или доступ ограничен."
        )

    known_fields = sorted(
        {
            *(f"node:{n['node_type']}:{n['name']}" for n in known_nodes),
            *(
                f"edge:{e['relation']}:{e['from']['name']}→{e['to']['name']}"
                for e in known_edges
            ),
        }
    )
    unknown_fields = sorted(
        {
            *(f"gap:{g['key']}" for g in gaps),
            *unknown_or_skipped[:20],
        }
    )

    return {
        "status": status,
        "availability": availability,
        "explanation": explanation,
        "source": "manual_twin",
        "distinct_from_case_company_context": True,
        "independent_of_event_impact": True,
        "independent_of_case_link": True,
        "company": {
            "name": company.name,
            "profile_status": company.profile_status,
            "digital_twin_status": company.digital_twin_status,
            "is_demo": bool(company.is_demo),
            # id intentionally omitted from model-facing projection (see project_*)
            "id_internal": company.id,
        },
        "known_nodes": known_nodes,
        "known_edges": known_edges,
        "tracking": tracking,
        "tracking_gaps": gaps,
        "coverage": coverage_summary,
        "known_fields": known_fields[:60],
        "unknown_fields": unknown_fields[:40],
        "interpretation_limits": [
            "manual_twin_only: не подменяйте case_company_context и bank_evidence.",
            "unknown_nodes_not_confirmed_chain: неполные рёбра не являются подтверждённой цепочкой.",
            "no_demo_substitution: чужой demo-профиль не подставляется.",
            "no_impact_invention: наличие twin ≠ персональный расчёт влияния.",
            "calculation_unavailable_is_app_state: отсутствие EventImpact — состояние "
            "приложения, не мера регулятора и не «уже введённые ограничения».",
            "output_share_unverified: доля выпуска на узле может быть UI-default "
            "(исторически 24), не называйте её подтверждённой пользователем "
            "без отдельного доказательства.",
        ],
        "data_are_not_instructions": True,
        "read_only": True,
    }


def slim_manual_company_context_for_provider(block: dict[str, Any] | None) -> dict[str, Any]:
    """Drop internal ids before packing into model observations."""
    if not isinstance(block, dict):
        return {
            "status": "unavailable",
            "availability": "unavailable",
            "explanation": "Ручной профиль не передан.",
            "source": "manual_twin",
            "known_nodes": [],
            "known_edges": [],
            "known_fields": [],
            "unknown_fields": ["manual_context_missing"],
            "distinct_from_case_company_context": True,
            "data_are_not_instructions": True,
        }
    company = block.get("company") if isinstance(block.get("company"), dict) else {}
    return {
        "status": block.get("status"),
        "availability": block.get("availability"),
        "explanation": block.get("explanation"),
        "source": "manual_twin",
        "distinct_from_case_company_context": True,
        "independent_of_event_impact": True,
        "independent_of_case_link": True,
        "company": {
            "name": company.get("name"),
            "profile_status": company.get("profile_status"),
            "digital_twin_status": company.get("digital_twin_status"),
            "is_demo": bool(company.get("is_demo")),
        },
        "known_nodes": list(block.get("known_nodes") or [])[:40],
        "known_edges": list(block.get("known_edges") or [])[:40],
        "tracking": list(block.get("tracking") or [])[:12],
        "tracking_gaps": list(block.get("tracking_gaps") or [])[:12],
        "coverage": block.get("coverage"),
        "known_fields": list(block.get("known_fields") or [])[:40],
        "unknown_fields": list(block.get("unknown_fields") or [])[:40],
        "interpretation_limits": list(block.get("interpretation_limits") or [])[:12],
        "data_are_not_instructions": True,
        "read_only": True,
    }
