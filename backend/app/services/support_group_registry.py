"""Persist Telegram support group chat_ids (runtime file, not git)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _registry_path() -> Path:
    settings = get_settings()
    raw = (getattr(settings, "telegram_polling_state_dir", None) or "").strip()
    base = Path(raw) if raw else Path("data/telegram_polling")
    base.mkdir(parents=True, exist_ok=True)
    return base / "support_operator_chats.json"


def load_registered_chat_ids() -> list[str]:
    path = _registry_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = data.get("chat_ids") if isinstance(data, dict) else data
        if not isinstance(ids, list):
            return []
        return [str(x).strip() for x in ids if str(x).strip()]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []


def register_chat_id(chat_id: str | int) -> list[str]:
    cid = str(chat_id).strip()
    ids = load_registered_chat_ids()
    if cid not in ids:
        ids.append(cid)
        path = _registry_path()
        path.write_text(
            json.dumps({"chat_ids": ids}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("support_group_registered chat_id=%s", cid)
    return ids


def unregister_chat_id(chat_id: str | int) -> list[str]:
    cid = str(chat_id).strip()
    ids = [x for x in load_registered_chat_ids() if x != cid]
    path = _registry_path()
    path.write_text(
        json.dumps({"chat_ids": ids}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return ids


def _alerts_path() -> Path:
    return _registry_path().with_name("support_user_alerts.json")


def load_email_alert_chats() -> dict[str, str]:
    """email(lower) → telegram chat_id for support reply DMs."""
    path = _alerts_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("by_email") if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(k).strip().lower(): str(v).strip()
            for k, v in raw.items()
            if str(k).strip() and str(v).strip()
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def register_email_alert(email: str, chat_id: str | int) -> None:
    key = (email or "").strip().lower()
    cid = str(chat_id).strip()
    if not key or "@" not in key or not cid:
        raise ValueError("bad email or chat_id")
    data = load_email_alert_chats()
    data[key] = cid
    path = _alerts_path()
    path.write_text(
        json.dumps({"by_email": data}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("support_alert_registered email=%s", key)
