"""Competition profile: organizers' LLM gateway only when COMPETITION_MODE is on.

Normal (non-competition) mode is unchanged. Root .env defaults keep competition off.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from app.core.errors import AppError

# Exact organizers' OpenAI-compatible base (no trailing slash).
COMPETITION_HACKATHON_BASE_URL = "https://changellenge.up.railway.app/v1"
COMPETITION_REQUIRED_SCHEME = "https"
COMPETITION_REQUIRED_HOST = "changellenge.up.railway.app"
COMPETITION_REQUIRED_PATH = "/v1"

# Exact hostnames that must never be used as HACKATHON_BASE_URL.
FORBIDDEN_LLM_HOSTS = frozenset(
    {
        "api.openai.com",
        "gigachat.devices.sberbank.ru",
        "ngw.devices.sberbank.ru",
    }
)


def competition_mode_enabled(settings=None) -> bool:
    from app.core.config import get_settings

    s = settings if settings is not None else get_settings()
    return bool(getattr(s, "competition_mode", False))


def _raise_misconfigured(
    reason: str,
    message: str,
    *,
    code: str = "COMPETITION_MISCONFIGURED",
) -> None:
    raise AppError(
        code,
        message,
        500,
        details=[{"reason": reason}],
    )


def validate_hackathon_base_url_structure(
    url: str,
    *,
    require_competition_exact: bool = False,
    allowed_egress_port: int | None = None,
) -> str:
    """Validate HACKATHON_BASE_URL via scheme/host/port/path (not substring search).

    When require_competition_exact is True (competition profile), only the
    organizers' https host + /v1 path is accepted: no userinfo, query, or fragment.

    Forbidden LLM hosts never get an HTTP call:
    - normal mode → PROVIDER_MISCONFIGURED
    - competition exact mode → COMPETITION_MISCONFIGURED
    """
    # Competition-exact validation uses COMPETITION_*; otherwise provider-level codes.
    err_code = (
        "COMPETITION_MISCONFIGURED"
        if require_competition_exact
        else "PROVIDER_MISCONFIGURED"
    )

    raw = (url or "").strip()
    if not raw:
        _raise_misconfigured("empty_base_url", "HACKATHON_BASE_URL пуст", code=err_code)

    parts = urlsplit(raw)
    if parts.username is not None or parts.password is not None:
        _raise_misconfigured(
            "base_url_userinfo",
            "HACKATHON_BASE_URL не должен содержать userinfo",
            code=err_code,
        )
    if "@" in (parts.netloc or ""):
        _raise_misconfigured(
            "base_url_userinfo",
            "HACKATHON_BASE_URL не должен содержать userinfo",
            code=err_code,
        )

    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    path = (parts.path or "").rstrip("/") or "/"
    if path != "/" and not path.startswith("/"):
        path = "/" + path

    if not scheme or not host:
        _raise_misconfigured(
            "base_url_unparseable",
            "HACKATHON_BASE_URL не удалось разобрать (нужны scheme и host)",
            code=err_code,
        )

    if host in FORBIDDEN_LLM_HOSTS:
        _raise_misconfigured(
            "forbidden_base_url",
            "HACKATHON_BASE_URL указывает на запрещённый хост",
            code=err_code,
        )

    if require_competition_exact:
        if scheme != COMPETITION_REQUIRED_SCHEME:
            _raise_misconfigured(
                "base_url_scheme",
                "В конкурсном режиме HACKATHON_BASE_URL должен использовать https",
            )
        if host != COMPETITION_REQUIRED_HOST:
            _raise_misconfigured(
                "base_url_host",
                "В конкурсном режиме HACKATHON_BASE_URL должен указывать на шлюз организаторов",
            )
        allowed_ports = {443}
        if allowed_egress_port is not None and int(allowed_egress_port) not in allowed_ports:
            allowed_ports.add(int(allowed_egress_port))
        effective_port = parts.port if parts.port is not None else 443
        if effective_port not in allowed_ports:
            _raise_misconfigured(
                "base_url_port",
                "В конкурсном режиме HACKATHON_BASE_URL не должен задавать нестандартный port",
            )
        if path != COMPETITION_REQUIRED_PATH:
            _raise_misconfigured(
                "base_url_path",
                "В конкурсном режиме HACKATHON_BASE_URL path должен быть /v1",
            )
        if parts.query:
            _raise_misconfigured(
                "base_url_query",
                "В конкурсном режиме HACKATHON_BASE_URL не должен содержать query",
            )
        if parts.fragment:
            _raise_misconfigured(
                "base_url_fragment",
                "В конкурсном режиме HACKATHON_BASE_URL не должен содержать fragment",
            )
        if allowed_egress_port is not None and effective_port == int(allowed_egress_port):
            return f"https://{COMPETITION_REQUIRED_HOST}:{effective_port}{COMPETITION_REQUIRED_PATH}"
        return COMPETITION_HACKATHON_BASE_URL

    return raw.rstrip("/")

def assert_competition_llm_config(settings=None) -> None:
    """When COMPETITION_MODE is on, require hackathon + allowed model + exact base URL.

    Raises AppError before any model HTTP. No-op when competition mode is off.
    Does not require API key (missing key fails later at provider construction).
    """
    from app.core.config import get_settings
    from app.services.assistant.hackathon import assert_hackathon_model

    s = settings if settings is not None else get_settings()
    if not competition_mode_enabled(s):
        return

    provider = s.normalized_assistant_provider()
    if provider != "hackathon":
        raise AppError(
            "COMPETITION_PROVIDER_FORBIDDEN",
            (
                "В конкурсном режиме разрешён только ASSISTANT_PROVIDER=hackathon "
                f"(сейчас: {provider}). Fallback на OpenAI/GigaChat/mock запрещён."
            ),
            503,
            details=[{"reason": "competition_provider", "provider": provider}],
        )

    validate_hackathon_base_url_structure(
        s.resolved_hackathon_base_url(),
        require_competition_exact=True,
        allowed_egress_port=getattr(s, "hackathon_egress_port", None),
    )
    assert_hackathon_model(s.resolved_hackathon_model())


def refuse_non_hackathon_llm(*, path: str) -> None:
    """Block OpenAI / GigaChat / mock / live-enrich entry points in competition mode."""
    if not competition_mode_enabled():
        return
    raise AppError(
        "COMPETITION_LLM_FORBIDDEN",
        (
            "В конкурсном режиме запрещены обращения к неконкурсным LLM "
            f"(путь: {path}). Разрешён только hackathon-шлюз организаторов."
        ),
        503,
        details=[{"reason": "competition_mode_blocks_path", "path": path}],
    )


def competition_settings_errors(settings) -> list[str]:
    """Return human-readable config errors for COMPETITION_MODE (for Settings validator)."""
    from app.services.assistant.hackathon import HACKATHON_ALLOWED_MODELS

    if not bool(getattr(settings, "competition_mode", False)):
        return []
    errors: list[str] = []
    provider = (settings.assistant_provider or "mock").lower()
    if provider == "live":
        provider = "openai"
    if provider != "hackathon":
        errors.append(
            "COMPETITION_MODE=true requires ASSISTANT_PROVIDER=hackathon "
            f"(got {provider!r})"
        )
    try:
        validate_hackathon_base_url_structure(
            settings.resolved_hackathon_base_url(),
            require_competition_exact=True,
            allowed_egress_port=getattr(settings, "hackathon_egress_port", None),
        )
    except AppError as exc:
        reason = None
        if exc.details and isinstance(exc.details[0], dict):
            reason = exc.details[0].get("reason")
        errors.append(f"COMPETITION_MODE HACKATHON_BASE_URL invalid ({reason})")
    model = settings.resolved_hackathon_model()
    if model not in HACKATHON_ALLOWED_MODELS:
        errors.append(
            f"COMPETITION_MODE HACKATHON_MODEL {model!r} is not in organizers' allow-list"
        )
    return errors
