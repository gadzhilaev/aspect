"""Public news API — no company-specific fields leaked."""

from fastapi.testclient import TestClient


FORBIDDEN_KEYS = {
    "impact_score",
    "confidence",
    "exposure",
    "company_id",
    "reason_summary",
    "score_breakdown",
    "claims",
}


def _assert_public_card(card: dict) -> None:
    for key in FORBIDDEN_KEYS:
        assert key not in card
    assert "title" in card and "summary" in card
    assert "category_label" in card
    assert "image_url" in card
    assert "is_demo" in card
    assert isinstance(card["is_demo"], bool)


def test_public_news_list(client: TestClient):
    r = client.get("/api/v1/public/news")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) >= 1
    for item in body["items"]:
        _assert_public_card(item)


def test_public_news_detail(client: TestClient):
    r = client.get("/api/v1/public/news/evt_china_export_001")
    assert r.status_code == 200
    body = r.json()
    _assert_public_card(body)
    assert "body" in body
    assert "sources" in body
    assert body["sources"], "seed event must expose sources"
    src = body["sources"][0]
    assert "publisher" in src
    assert "published_at" in src
    assert "url" in src
    assert body.get("primary_publisher")
    for key in FORBIDDEN_KEYS:
        assert key not in body


def test_public_categories(client: TestClient):
    r = client.get("/api/v1/public/categories")
    assert r.status_code == 200
    cats = r.json()
    assert isinstance(cats, list) and len(cats) >= 1
    assert "label" in cats[0] and "count" in cats[0]


def test_public_trending(client: TestClient):
    r = client.get("/api/v1/public/trending")
    assert r.status_code == 200
    body = r.json()
    assert body["featured"] is not None
    _assert_public_card(body["featured"])
    assert "risks" in body and "opportunities" in body
    for key in FORBIDDEN_KEYS:
        assert key not in body["featured"]


def test_public_no_auth_required(client: TestClient):
    assert client.get("/api/v1/public/trending").status_code == 200
    assert client.get("/api/v1/public/news").status_code == 200
