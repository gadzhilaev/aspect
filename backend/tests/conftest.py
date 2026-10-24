import os

# Isolate test DB / secrets before app imports (do not load rotated local .env secrets)
os.environ["DATABASE_URL"] = "sqlite:///./kontur_test.db"
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "kontur-webhook-secret"
os.environ["ASSISTANT_PROVIDER"] = "mock"
os.environ["OPENAI_API_KEY"] = ""
os.environ["GIGACHAT_AUTH_KEY"] = ""
os.environ["INGESTION_RUN_TOKEN"] = "test-ingestion-token"
# Parent shells / clean-env scripts may export COMPETITION_MODE; default tests use mock.
os.environ.pop("COMPETITION_MODE", None)
os.environ.pop("HACKATHON_API_KEY", None)
# Parent TG stands may export TELEGRAM_OUTBOX_KINDS=test — tests need all kinds.
os.environ.pop("TELEGRAM_OUTBOX_KINDS", None)
os.environ.pop("TELEGRAM_NEWS_NOTIFICATIONS_ENABLED", None)
os.environ.pop("TELEGRAM_NEWS_CONTROLLED_PAIR", None)
# Stand overlays must not leak into default unit tests.
os.environ.pop("AGENT_DEMO_STAND", None)
os.environ.pop("AGENT_DEMO_EVENT_ID", None)
os.environ.pop("CASE_CONTEXT_SLOT_KEY", None)
os.environ.pop("BANK_MATERIALS_ALLOWED_OCR_RUN_IDS", None)
os.environ.pop("BANK_MATERIALS_STORAGE_ROOT", None)
os.environ.pop("NEWS_SCHEDULER_STATE_DIR", None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import create_app
from scripts.seed_demo import main as seed_main


def _drop_all():
    """Drop metadata tables; disable SQLite FKs to allow circular case_* teardown."""
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=OFF"))
        Base.metadata.drop_all(bind=conn)


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    get_settings.cache_clear()
    _drop_all()
    Base.metadata.create_all(bind=engine)
    seed_main()
    yield
    _drop_all()
    if os.path.exists("kontur_test.db"):
        try:
            os.remove("kontur_test.db")
        except OSError:
            pass


@pytest.fixture
def client():
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@kontur.app", "password": "DemoKontur1!"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
