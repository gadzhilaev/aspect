"""One-shot live smoke for HackathonProvider. No DB writes. No retries.

Does not print secrets, Authorization, or full context.
Run from repo root: python -m scripts._hackathon_live_smoke
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.assistant.hackathon import HackathonProvider
from app.services.assistant.provider import get_provider


class CountingTransport(httpx.HTTPTransport):
    """Real network transport that counts attempts (no retry logic)."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0
        self.last_status: int | None = None
        self.last_host: str | None = None
        self.last_path: str | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        self.last_host = request.url.host
        self.last_path = request.url.path
        # Never log Authorization
        resp = super().handle_request(request)
        self.last_status = resp.status_code
        return resp


def _safe_err(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, AppError):
        return {
            "ok": False,
            "error_code": exc.code,
            "error_message": exc.message,
            "http_status": exc.status_code,
            "details_reasons": [
                d.get("reason") for d in (exc.details or []) if isinstance(d, dict)
            ],
        }
    return {
        "ok": False,
        "error_code": type(exc).__name__,
        "error_message": "non-AppError failure",
        "http_status": None,
        "details_reasons": [],
    }


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    provider_name = settings.normalized_assistant_provider()
    model = settings.resolved_hackathon_model()
    base = settings.resolved_hackathon_base_url()
    key_configured = bool(settings.resolved_hackathon_api_key())

    report: dict[str, Any] = {
        "config": {
            "provider": provider_name,
            "model": model,
            "base_url": base,
            "key_configured": key_configured,
        },
        "http_attempts": 0,
        "response_nonempty": False,
        "contract_ok": False,
        "usage_returned": False,
        "usage": None,
        "content_preview_len": 0,
        "db_writes": False,
    }

    if provider_name != "hackathon":
        report["ok"] = False
        report["fail_reason"] = "provider_not_hackathon"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    if model != "deepseek/deepseek-v4.1-flash":
        report["ok"] = False
        report["fail_reason"] = "unexpected_model"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    if base.rstrip("/") != "https://changellenge.up.railway.app/v1":
        report["ok"] = False
        report["fail_reason"] = "unexpected_base_url"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    if not key_configured:
        report["ok"] = False
        report["fail_reason"] = "key_not_configured"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    factory = get_provider()
    if not isinstance(factory, HackathonProvider):
        report["ok"] = False
        report["fail_reason"] = f"get_provider_type={type(factory).__name__}"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    report["provider_class"] = type(factory).__name__
    report["provider_model_attr"] = factory.model
    report["provider_base_attr"] = factory.base_url

    transport = CountingTransport()
    client = httpx.Client(transport=transport, timeout=60.0)
    # Same class + settings as production wiring; injected client only for attempt count.
    provider = HackathonProvider(
        api_key=settings.resolved_hackathon_api_key() or "",
        model=model,
        base_url=base,
        http_client=client,
        timeout=60.0,
    )

    minimal_context = {
        "event": {"title": "Smoke-событие", "category": "macro"},
        "company": {"name": "Smoke Co"},
        "impact": {"impact_score": 40, "confidence": 0.5, "reason_summary": "smoke"},
        "bank_evidence": {"available": False, "status": "no_matching_evidence", "fragments": []},
    }
    user_text = "Кратко объясни разницу между фактом события и прогнозом"

    try:
        result = provider.generate(
            context=minimal_context,
            history=[],
            user_text=user_text,
        )
    except Exception as exc:  # noqa: BLE001
        report.update(_safe_err(exc))
        report["http_attempts"] = transport.attempts
        report["last_http_status"] = transport.last_status
        report["last_host"] = transport.last_host
        report["last_path"] = transport.last_path
        print(json.dumps(report, ensure_ascii=False, indent=2))
        client.close()
        return 1
    finally:
        # ensure close if success path too
        pass

    report["http_attempts"] = transport.attempts
    report["last_http_status"] = transport.last_status
    report["last_host"] = transport.last_host
    report["last_path"] = transport.last_path

    content = (result.content or "").strip()
    report["response_nonempty"] = bool(content)
    report["content_preview_len"] = len(content)
    # Contract: ProviderResult with content str; tool_calls list; citations list
    report["contract_ok"] = (
        isinstance(result.content, str)
        and isinstance(result.tool_calls, list)
        and isinstance(result.bank_evidence_citations, list)
        and bool(content)
    )
    if result.usage is not None:
        report["usage_returned"] = True
        report["usage"] = result.usage
    else:
        report["usage_returned"] = False
        report["usage"] = None

    report["ok"] = bool(report["contract_ok"] and transport.attempts == 1)
    report["fallback_used"] = False
    client.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
