from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AssistantProviderName = Literal["mock", "openai", "gigachat", "hackathon"]

_ASSISTANT_PROVIDERS = frozenset({"mock", "openai", "gigachat", "hackathon"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Kontur API"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # SQLite by default for zero-deps local demo; switch to Postgres via DATABASE_URL
    database_url: str = "sqlite:///./kontur.db"

    secret_key: str = "kontur-hackathon-dev-secret-change-me"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    algorithm: str = "HS256"

    # Demo email verification codes (never enable silently in production)
    demo_email_code: str = "123456"
    allow_demo_seed_user: bool = True

    # Impact scoring weights (must sum ~1.0)
    impact_weight_severity: float = 0.40
    impact_weight_exposure: float = 0.30
    impact_weight_dependency: float = 0.20
    impact_weight_proximity: float = 0.10
    impact_model_version: str = "impact-v1.1"
    simulator_model_version: str = "sim-v1.0"

    telegram_bot_token: str | None = None
    telegram_bot_username: str = "KonturDemoBot"
    telegram_webhook_secret: str = "kontur-webhook-secret"
    telegram_link_token_ttl_minutes: int = 10
    # Cooldown between test-send enqueue per subscription (seconds)
    telegram_test_send_cooldown_seconds: int = 60
    # Comma-separated outbox kinds the worker may process.
    # Empty / unset = all kinds (default). TG-3 stand uses "test" only.
    telegram_outbox_kinds: str | None = None
    # TG-4: automatic risk+impact news → outbox. Default off (stands keep kinds=test).
    telegram_news_notifications_enabled: bool = False
    # TG-5 controlled one-shot: "subscription_id:event_id" — allows that demo fixture only
    # when auto-news is off / event is demo. Empty = no exception. Never a production open gate.
    telegram_news_controlled_pair: str | None = None
    # Dev long-polling (getUpdates). State dir holds offset + lock; no public ports.
    telegram_polling_state_dir: str | None = None
    telegram_polling_timeout_seconds: int = 25
    deep_link_base: str = "https://kontur.app/e"
    # Public https site origin for Telegram open buttons (never localhost)
    public_web_base_url: str | None = None

    cors_origins: str = "*"

    # Contextual assistant — keys never go to client or DB
    # Accepted env: mock | openai | gigachat | hackathon | live (deprecated alias → openai)
    assistant_provider: str = "mock"
    # Legacy OpenAI aliases (still accepted)
    assistant_api_key: str | None = None
    assistant_base_url: str = "https://api.openai.com/v1"
    assistant_model: str = "gpt-4o-mini"
    # Canonical OpenAI env
    openai_api_key: str | None = None
    openai_model: str | None = None

    # GigaChat (Sber) — server only
    gigachat_auth_key: str | None = None
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"
    gigachat_oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_api_base_url: str = "https://gigachat.devices.sberbank.ru/api/v1"
    # PEM bundle with Russian Trusted Root CA (never disable TLS verify)
    gigachat_ca_bundle: str | None = None

    # Hackathon organizers' OpenAI-compatible gateway (ASSISTANT_PROVIDER=hackathon)
    hackathon_api_key: str | None = None
    hackathon_base_url: str = "https://changellenge.up.railway.app/v1"
    hackathon_model: str = "deepseek/deepseek-v4.1-flash"

    # Competition profile (stage 6.2). Default off — does not rewrite root .env.
    # When true: only ASSISTANT_PROVIDER=hackathon, organizers' model allow-list,
    # exact HACKATHON_BASE_URL; OpenAI/GigaChat/mock fallback forbidden before HTTP.
    competition_mode: bool = False

    # Ingestion — cron/CLI only; internal run protected by token
    ingestion_run_token: str | None = None
    # Default whitelist for RssProvider. CBR news RSS is fetched by CbrProvider — omit here.
    # EC presscorner may carry dossier=trade in the URL; that does not mean a trade-only feed.
    ingestion_rss_feeds: str = (
        "https://www.interfax.ru/rss.asp|"
        "https://www.wto.org/library/rss/latest_news_e.xml|"
        "https://customs.gov.ru/press/federal/rss|"
        "https://ec.europa.eu/commission/presscorner/api/rss?dossier=trade&language=en|"
        "https://www.vedomosti.ru/rss/news"
    )
    ingestion_gdelt_queries: str = (
        "export control OR sanctions OR supply chain|"
        "ключевая ставка OR currency OR FX|"
        "semiconductor OR electronics shortage"
    )
    # Separate news scheduler process (not inside FastAPI). Default off-ish:
    # interval still used when process is started; stand keeps its own env file.
    news_scheduler_interval_seconds: int = 1200
    news_scheduler_state_dir: str | None = None
    news_scheduler_pending_limit: int = 100
    news_scheduler_http_timeout_seconds: float = 20.0
    news_scheduler_max_per_feed: int = 20
    news_scheduler_max_per_query: int = 15

    # Competition case context for GET /companies/{id}/context (server-chosen slot).
    # Empty / unset → case_context.status=integration_not_configured; no auto-pick.
    # Does not import, link, or activate snapshots.
    case_context_slot_key: str | None = None

    # Bank materials read-only API (stage 2.12).
    # Empty allowed OCR run IDs → integration not configured (no auto-open of corpus).
    # Client cannot expand scope via run/document/file IDs.
    # Comma- or pipe-separated OCR run UUIDs.
    bank_materials_allowed_ocr_run_ids: str = ""
    # Absolute or project-relative directory that confines storage_key resolution.
    bank_materials_storage_root: str | None = None

    # Multi-step assistant loop (stage 4.5+: wired into post_message when true + hackathon).
    # Default off: working post_message stays on legacy single-shot path.
    assistant_agent_loop: bool = False
    assistant_loop_max_model_http: int = 4
    assistant_loop_max_tool_calls: int = 3
    assistant_loop_max_repairs: int = 1
    assistant_loop_timeout_s: float = 90.0
    assistant_loop_max_result_chars: int = 4000
    assistant_loop_max_transcript_chars: int = 12_000
    assistant_loop_max_raw_action_chars: int = 24_000

    # External company registry lookup by INN (DaData findById/party).
    # Key is server-only (never VITE_*). Empty key → lookup returns not_configured
    # and the app still works with manual company creation.
    dadata_api_key: str | None = None
    company_registry_timeout_seconds: float = 6.0
    company_registry_max_candidates: int = 10
    company_registry_max_response_bytes: int = 1_000_000
    # Public requisites TTL cache (per process). 0 disables caching.
    company_registry_cache_ttl_seconds: int = 3600
    # Per-user fixed-window rate limit for lookups (per process). 0 disables.
    company_registry_user_rate_per_minute: int = 20
    # How long a lookup result stays confirmable (lookup_id TTL), seconds.
    company_registry_lookup_ttl_seconds: int = 900

    # Agent-loop demo stand only (stage 4.8). Default off — never enables
    # product feed hardcoding. When true, GET /agent-demo/entry resolves
    # synthetic fixture links for the stand UI panel.
    agent_demo_stand: bool = False
    # Optional explicit event id for the stand; otherwise title/attrs markers.
    agent_demo_event_id: str | None = None

    @field_validator("assistant_provider", mode="before")
    @classmethod
    def _coerce_provider(cls, value: object) -> str:
        raw = str(value or "mock").strip().lower()
        if raw == "live":
            # Deprecated alias for openai
            return "openai"
        if raw not in _ASSISTANT_PROVIDERS:
            return "mock"
        return raw

    @field_validator(
        "assistant_loop_max_model_http",
        "assistant_loop_max_tool_calls",
        "assistant_loop_max_repairs",
        "assistant_loop_max_result_chars",
        "assistant_loop_max_transcript_chars",
        "assistant_loop_max_raw_action_chars",
        mode="after",
    )
    @classmethod
    def _loop_int_limits(cls, value: int, info) -> int:  # noqa: ANN001
        name = info.field_name
        if name == "assistant_loop_max_model_http" and value < 1:
            raise ValueError("ASSISTANT_LOOP_MAX_MODEL_HTTP must be >= 1")
        if name in {
            "assistant_loop_max_tool_calls",
            "assistant_loop_max_repairs",
        } and value < 0:
            raise ValueError(f"{name} must be >= 0")
        if name in {
            "assistant_loop_max_result_chars",
            "assistant_loop_max_transcript_chars",
            "assistant_loop_max_raw_action_chars",
        } and value < 1:
            raise ValueError(f"{name} must be >= 1")
        return value

    @field_validator("assistant_loop_timeout_s", mode="after")
    @classmethod
    def _loop_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ASSISTANT_LOOP_TIMEOUT_S must be > 0")
        return value

    @model_validator(mode="after")
    def _prefer_openai_env(self) -> "Settings":
        # OPENAI_* wins when set; otherwise keep ASSISTANT_* for backward compat.
        # Hackathon keys stay isolated — never aliased from OPENAI_*.
        if self.openai_api_key:
            self.assistant_api_key = self.openai_api_key
        if self.openai_model:
            self.assistant_model = self.openai_model
        return self

    @model_validator(mode="after")
    def _competition_profile(self) -> "Settings":
        # Fail at settings construction when competition profile is misconfigured
        # (before any model HTTP). No-op when COMPETITION_MODE is off.
        from app.services.competition_profile import competition_settings_errors

        errs = competition_settings_errors(self)
        if errs:
            raise ValueError("; ".join(errs))
        # K10: in competition mode default to multi-step agent loop unless the
        # operator explicitly set ASSISTANT_AGENT_LOOP in the environment.
        if self.competition_mode and "assistant_agent_loop" not in self.model_fields_set:
            self.assistant_agent_loop = True
        return self

    def agent_loop_budget_config(self):
        """Build TurnBudgetConfig from settings (import deferred to avoid cycles)."""
        from app.services.assistant.agent_loop.budget import TurnBudgetConfig

        return TurnBudgetConfig(
            max_model_http=self.assistant_loop_max_model_http,
            max_tool_calls=self.assistant_loop_max_tool_calls,
            max_repairs=self.assistant_loop_max_repairs,
            timeout_s=self.assistant_loop_timeout_s,
            max_result_chars=self.assistant_loop_max_result_chars,
            max_transcript_chars=self.assistant_loop_max_transcript_chars,
            max_raw_action_chars=self.assistant_loop_max_raw_action_chars,
        )

    def normalized_assistant_provider(self) -> AssistantProviderName:
        mode = (self.assistant_provider or "mock").lower()
        if mode == "live":
            return "openai"
        if mode in _ASSISTANT_PROVIDERS:
            return mode  # type: ignore[return-value]
        return "mock"

    def resolved_openai_api_key(self) -> str | None:
        return self.openai_api_key or self.assistant_api_key

    def resolved_openai_model(self) -> str:
        return self.openai_model or self.assistant_model or "gpt-4o-mini"

    def resolved_gigachat_auth_key(self) -> str | None:
        key = (self.gigachat_auth_key or "").strip()
        return key or None

    def resolved_hackathon_api_key(self) -> str | None:
        key = (self.hackathon_api_key or "").strip()
        return key or None

    def resolved_hackathon_base_url(self) -> str:
        raw = (self.hackathon_base_url or "").strip().rstrip("/")
        return raw or "https://changellenge.up.railway.app/v1"

    def resolved_hackathon_model(self) -> str:
        raw = (self.hackathon_model or "").strip()
        return raw or "deepseek/deepseek-v4.1-flash"

    def resolved_dadata_api_key(self) -> str | None:
        key = (self.dadata_api_key or "").strip()
        return key or None

    def resolved_gigachat_ca_bundle(self) -> str | None:
        """Path to CA PEM for GigaChat TLS (Минцифры + system CAs)."""
        from pathlib import Path

        if self.gigachat_ca_bundle:
            p = Path(self.gigachat_ca_bundle)
            if p.is_file():
                return str(p.resolve())
        bundled = Path(__file__).resolve().parents[1] / "certs" / "gigachat_ca_bundle.pem"
        if bundled.is_file():
            return str(bundled.resolve())
        return None

    def rss_feed_list(self) -> list[str]:
        raw = (self.ingestion_rss_feeds or "").strip()
        if not raw:
            return []
        parts = [p.strip() for p in raw.replace("\n", "|").replace(",", "|").split("|")]
        return [p for p in parts if p.startswith("http")]

    def gdelt_query_list(self) -> list[str]:
        raw = (self.ingestion_gdelt_queries or "").strip()
        if not raw:
            return []
        return [p.strip() for p in raw.split("|") if p.strip()]

    def bank_materials_allowed_ocr_run_id_set(self) -> frozenset[str]:
        """Server-side OCR run scope. Empty → API integration not configured."""
        raw = (self.bank_materials_allowed_ocr_run_ids or "").strip()
        if not raw:
            return frozenset()
        parts = [
            p.strip()
            for p in raw.replace("\n", "|").replace(",", "|").split("|")
        ]
        return frozenset(p for p in parts if p)

    def resolved_bank_materials_storage_root(self):
        """Resolved storage root Path, or None if unset/blank."""
        from pathlib import Path

        raw = (self.bank_materials_storage_root or "").strip()
        if not raw:
            return None
        return Path(raw).expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
