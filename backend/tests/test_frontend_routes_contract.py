"""Static contract: impact CTA routes must resolve to real product pages."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from resolve_front_root import resolve_front_src  # noqa: E402

WEB_SRC = resolve_front_src()


def test_event_scenarios_redirects_to_scenarios_workspace():
    routes = (WEB_SRC / "routes" / "AppRoutes.tsx").read_text(encoding="utf-8")
    assert "EventScenariosRedirect" in routes
    assert "SoftPlaceholder" not in routes.split("events/:eventId/scenarios")[1].split("decisions")[0]
    assert "/scenarios?event=" in routes


def test_impact_panel_scenarios_cta_points_to_workspace():
    panel = (WEB_SRC / "components" / "personal" / "ImpactPanel.tsx").read_text(encoding="utf-8")
    assert "/scenarios?event=" in panel
    assert "/events/${eventId}/scenarios" not in panel


def test_monitoring_only_offers_setup_cta_not_fake_calc():
    panel = (WEB_SRC / "components" / "personal" / "ImpactPanel.tsx").read_text(encoding="utf-8")
    # monitoring branch must explain and offer company setup, not invent metrics
    assert "Только мониторинг" in panel
    assert "Уточнить контекст компании" in panel
    assert "Нужны финансовые параметры" in panel  # finance branch still present


def test_decision_page_cancelled_ui_contract():
    page = (WEB_SRC / "pages" / "DecisionPage.tsx").read_text(encoding="utf-8")
    assert "Отменить план" in page
    assert "Отменить план?" in page
    assert "План останется в истории, но больше не будет считаться активным." in page
    assert "План отменён" in page or "status_label" in page
    assert "Вернуться к сценариям" in page
    assert "Подобрать новый вариант с Аспектом" in page
    assert "deleted" not in page.lower()
    scenarios = (WEB_SRC / "pages" / "ScenariosPage.tsx").read_text(encoding="utf-8")
    assert "План отменён" in scenarios
    # Status enum → label mapping lives in the shared helper (not inline on the page).
    helper = (WEB_SRC / "lib" / "assistantWithoutImpact.ts").read_text(encoding="utf-8")
    assert "decision_cancelled" in helper
    assert "План отменён" in helper
