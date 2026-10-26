"""Support chat AI: FAQ first, then lightweight LLM; escalate when unsure."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_FAQ: list[tuple[tuple[str, ...], str]] = [
    (
        ("парол", "войти", "логин", "вход", "авториз", "login", "password"),
        "Если не получается войти: проверьте email и пароль, "
        "что API-стенд запущен, и что почта подтверждена кодом. "
        "Незавершённую регистрацию можно начать заново с тем же email.",
    ),
    (
        ("удал", "аккаунт", "account"),
        "Удаление аккаунта — в Настройках → «Удалить аккаунт». "
        "Потребуется текущий пароль. Действие необратимо.",
    ),
    (
        ("телеграм", "telegram", "уведомл", "push"),
        "Telegram и уведомления настраиваются в карточке компании и в Настройках. "
        "Связка с ботом подтверждается после перехода по deep link.",
    ),
    (
        ("лент", "новост", "событ", "feed", "news"),
        "Лента строится по профилю компании (продукты, бренды, рынки) и case-данным. "
        "Если пусто — заполните продукты/бренды и дождитесь совпадений в корпусе "
        "(появление новости не гарантировано).",
    ),
    (
        ("финанс", "курс", "валют", "ставк", "fx", "кредит"),
        "Финансы и сценарии — в разделе компании «Финансы». "
        "Без заполненных данных сумма эффекта не выдумывается. "
        "Сценарии запускаются по вашему запросу в разборе события.",
    ),
    (
        ("банк", "pdf", "материал", "аналитик"),
        "Материалы Альфа-Банка открываются из разбора события "
        "(«Показать материал банка»). "
        "Цитирование AI опирается на проверенные фрагменты; "
        "остальные PDF доступны как поиск/оригинал.",
    ),
    (
        ("компани", "инн", "онборд", "профиль", "продукт", "бренд"),
        "Профиль компании редактируется на вкладке «Компания» "
        "(продукты, бренды, рынки, закупки). "
        "Поиск по ИНН работает, если настроен реестр (DaData).",
    ),
    (
        ("оператор", "человек", "живой", "менеджер"),
        "Сейчас отвечаю я — AI поддержки. Если не смогу помочь, "
        "подключу живого оператора в Telegram.",
    ),
]

_SYSTEM = (
    "Ты AI-поддержка приложения Аспект (финтех/новости для компаний). "
    "Отвечай коротко по-русски только по функциям приложения: вход, профиль, "
    "лента, финансы, Telegram, материалы банка, сценарии. "
    "Не выдумывай факты, суммы и статусы. "
    "Если не уверен или вопрос вне темы — escalate=true. "
    "Ответ строго JSON без markdown: "
    '{"escalate": false, "reply": "текст"} или '
    '{"escalate": true, "reply": null}'
)

_JSON_RE = re.compile(r"\{[\s\S]*\}")


@dataclass(frozen=True)
class SupportAiDecision:
    reply: str | None
    escalate: bool
    source: str  # faq | llm | escalate_fallback


def match_faq(user_text: str) -> str | None:
    blob = (user_text or "").lower()
    for keys, answer in _FAQ:
        if any(k in blob for k in keys):
            return answer
    return None


def decide_support_reply(user_text: str) -> SupportAiDecision:
    """FAQ → LLM → escalate. Never raises; escalate on any LLM failure."""
    faq = match_faq(user_text)
    if faq:
        return SupportAiDecision(reply=faq, escalate=False, source="faq")

    llm = _try_llm(user_text)
    if llm is not None:
        return llm

    return SupportAiDecision(reply=None, escalate=True, source="escalate_fallback")


def _try_llm(user_text: str) -> SupportAiDecision | None:
    settings = get_settings()
    provider = (settings.assistant_provider or "mock").strip().lower()
    if provider == "mock":
        return None

    api_key = ""
    base_url = ""
    model = ""
    if provider == "hackathon":
        api_key = (settings.hackathon_api_key or "").strip()
        base_url = (settings.hackathon_base_url or "").rstrip("/")
        model = settings.hackathon_model or "deepseek/deepseek-v4.1-flash"
    elif provider == "openai":
        api_key = (settings.resolved_openai_api_key() or "").strip()
        base_url = (settings.assistant_base_url or "https://api.openai.com/v1").rstrip(
            "/"
        )
        model = settings.resolved_openai_model() or "gpt-4o-mini"
    else:
        # GigaChat / unknown — don't invent path; escalate.
        return None

    if not api_key or not base_url:
        logger.info("support_ai_skip reason=no_api_key provider=%s", provider)
        return None

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": (user_text or "")[:2000]},
    ]
    try:
        with httpx.Client(timeout=20.0, trust_env=False) as client:
            resp = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 400,
                },
            )
        if resp.status_code >= 400:
            logger.warning("support_ai_http status=%s", resp.status_code)
            return None
        body = resp.json()
        choices = body.get("choices") or []
        if not choices:
            return None
        raw = (((choices[0] or {}).get("message") or {}).get("content")) or ""
        return _parse_llm_json(str(raw))
    except Exception as exc:  # noqa: BLE001
        logger.warning("support_ai_error type=%s", type(exc).__name__)
        return None


def _parse_llm_json(raw: str) -> SupportAiDecision | None:
    text = (raw or "").strip()
    if not text:
        return None
    match = _JSON_RE.search(text)
    if not match:
        # Plain text fallback: treat as answer if not too hedgey.
        lower = text.lower()
        if any(
            x in lower
            for x in ("не знаю", "не уверен", "оператор", "не могу", "эскал")
        ):
            return SupportAiDecision(reply=None, escalate=True, source="llm")
        return SupportAiDecision(reply=text[:2000], escalate=False, source="llm")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    escalate = bool(data.get("escalate"))
    reply = data.get("reply")
    if reply is not None:
        reply = str(reply).strip() or None
    if escalate or not reply:
        return SupportAiDecision(reply=None, escalate=True, source="llm")
    return SupportAiDecision(reply=reply[:2000], escalate=False, source="llm")
