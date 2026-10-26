"""Dev long-polling for Telegram updates (getUpdates).

Mutually exclusive with a configured webhook: refuses to start if
getWebhookInfo.url is non-empty (does not deleteWebhook).

Reuses ``handle_telegram_update`` — no duplicated pairing/command logic.
Opens no public ports. Never logs bot token, pairing payload, or message text.

Official Bot API: https://core.telegram.org/bots/api#getupdates
- offset confirms prior updates (pass last_update_id + 1)
- timeout enables long polling
- getUpdates will not work while a webhook is set
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.notifications import sanitize_telegram_error
from app.services.telegram_updates import handle_telegram_update

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 25
DEFAULT_LIMIT = 50
MAX_BACKOFF_S = 60.0
ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "callback_query",
    "my_chat_member",
]


class WebhookConflictError(RuntimeError):
    """Polling refused because a webhook URL is already configured."""


class PollingLockError(RuntimeError):
    """Another polling process holds the lock for this bot."""


def _api_base(token: str) -> str:
    return f"https://api.telegram.org/bot{token}"


def get_webhook_info(
    token: str, *, client: httpx.Client | None = None
) -> dict[str, Any]:
    """Call getWebhookInfo. Never log the token."""
    own = client is None
    http = client or httpx.Client(timeout=20.0, trust_env=False)
    try:
        resp = http.get(f"{_api_base(token)}/getWebhookInfo")
        resp.raise_for_status()
        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError("getWebhookInfo not ok")
        return body.get("result") or {}
    finally:
        if own:
            http.close()


def assert_polling_allowed(token: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
    """Raise WebhookConflictError if webhook URL is set. Does not delete webhook."""
    info = get_webhook_info(token, client=client)
    url = (info.get("url") or "").strip()
    if url:
        raise WebhookConflictError(
            "Telegram webhook is already configured; polling is mutually exclusive. "
            "Unset webhook manually if you intend to use local polling. "
            "This process will not call deleteWebhook."
        )
    return info


@dataclass
class OffsetStore:
    path: Path

    def load(self) -> int | None:
        if not self.path.is_file():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            off = data.get("offset")
            return int(off) if off is not None else None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def save(self, offset: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"offset": int(offset), "updated_at": time.time()}
        tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        tmp.replace(self.path)


@dataclass
class ProcessLock:
    """Single polling process per bot via PID file (no public ports)."""

    path: Path

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file():
            try:
                old = int(self.path.read_text(encoding="utf-8").strip().splitlines()[0])
            except (OSError, ValueError):
                old = None
            if old and _pid_alive(old):
                raise PollingLockError(f"polling already running pid={old}")
            try:
                self.path.unlink()
            except OSError:
                pass
        # Exclusive create
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(self.path), flags)
        except FileExistsError as exc:
            raise PollingLockError("polling lock busy") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()}\n")

    def release(self) -> None:
        try:
            if self.path.is_file():
                text = self.path.read_text(encoding="utf-8").strip()
                if text.splitlines()[0] == str(os.getpid()):
                    self.path.unlink()
        except OSError:
            pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            SYNCHRONIZE = 0x00100000
            handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _default_http_client() -> httpx.Client:
    return httpx.Client(timeout=40.0, trust_env=False)


@dataclass
class PollingRuntime:
    token: str
    offset_store: OffsetStore
    lock: ProcessLock
    session_factory: Callable[[], Session] = SessionLocal
    http_factory: Callable[[], httpx.Client] = _default_http_client
    long_poll_timeout: int = DEFAULT_TIMEOUT_S
    processed_ids: set[int] = field(default_factory=set)
    stop: bool = False

    def request_stop(self, *_args) -> None:
        self.stop = True
        logger.info("telegram_polling_stop_requested")

    def run_forever(self) -> int:
        self.lock.acquire()
        try:
            with self.http_factory() as client:
                assert_polling_allowed(self.token, client=client)
                offset = self.offset_store.load()
                logger.info(
                    "telegram_polling_started offset=%s long_poll_timeout=%s",
                    offset if offset is not None else "none",
                    self.long_poll_timeout,
                )
                backoff = 1.0
                while not self.stop:
                    try:
                        updates = self._get_updates(client, offset)
                        backoff = 1.0
                        for upd in updates:
                            uid = int(upd.get("update_id"))
                            next_offset = uid + 1
                            if uid in self.processed_ids:
                                # Redelivery of already-handled update_id — skip side effects
                                offset = next_offset
                                self.offset_store.save(offset)
                                logger.info(
                                    "telegram_polling_skip_duplicate update_id=%s", uid
                                )
                                continue
                            self._process_one(upd)
                            self.processed_ids.add(uid)
                            # Keep set bounded
                            if len(self.processed_ids) > 5000:
                                self.processed_ids = set(
                                    sorted(self.processed_ids)[-1000:]
                                )
                            offset = next_offset
                            self.offset_store.save(offset)
                    except WebhookConflictError:
                        raise
                    except httpx.HTTPError as exc:
                        logger.warning(
                            "telegram_polling_http_error err=%s backoff=%.1f",
                            sanitize_telegram_error(str(exc)),
                            backoff,
                        )
                        self._sleep(backoff)
                        backoff = min(MAX_BACKOFF_S, backoff * 2)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "telegram_polling_error err=%s backoff=%.1f",
                            sanitize_telegram_error(str(exc)),
                            backoff,
                        )
                        self._sleep(backoff)
                        backoff = min(MAX_BACKOFF_S, backoff * 2)
        finally:
            self.lock.release()
            logger.info("telegram_polling_stopped")
        return 0

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self.stop and time.monotonic() < end:
            time.sleep(min(0.25, end - time.monotonic()))

    def _get_updates(
        self, client: httpx.Client, offset: int | None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "timeout": self.long_poll_timeout,
            "limit": DEFAULT_LIMIT,
            "allowed_updates": json.dumps(ALLOWED_UPDATES),
        }
        if offset is not None:
            params["offset"] = offset
        # Long-poll timeout must fit client timeout
        resp = client.get(
            f"{_api_base(self.token)}/getUpdates",
            params=params,
            timeout=self.long_poll_timeout + 15.0,
        )
        if resp.status_code == 409:
            # Conflict usually means webhook is set
            raise WebhookConflictError(
                "getUpdates returned 409 — webhook likely configured; refusing polling"
            )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("ok"):
            desc = sanitize_telegram_error(str(body.get("description") or "not_ok"))
            raise RuntimeError(f"getUpdates failed: {desc}")
        result = body.get("result") or []
        return list(result)

    def _process_one(self, update: dict[str, Any]) -> None:
        uid = update.get("update_id")
        db = self.session_factory()
        try:
            result = handle_telegram_update(db, update)
            if result.get("method") == "sendMessage":
                self._send_message_result(result)
            logger.info("telegram_polling_handled update_id=%s", uid)
        finally:
            db.close()

    def _send_message_result(self, result: dict[str, Any]) -> None:
        token = self.token
        payload = {
            "chat_id": result["chat_id"],
            "text": result.get("text") or "",
        }
        for key in ("reply_markup", "parse_mode", "disable_web_page_preview"):
            if key in result:
                payload[key] = result[key]
        with self.http_factory() as client:
            resp = client.post(
                f"{_api_base(token)}/sendMessage",
                json=payload,
                timeout=20.0,
            )
            if resp.status_code >= 400:
                logger.warning(
                    "telegram_polling_send_failed status=%s err=%s",
                    resp.status_code,
                    sanitize_telegram_error(resp.text),
                )


def default_state_dir() -> Path:
    settings = get_settings()
    raw = (getattr(settings, "telegram_polling_state_dir", None) or "").strip()
    if raw:
        return Path(raw)
    # Prefer telegram live stand when present
    stand = Path("data/telegram_live")
    if stand.is_dir():
        return stand
    return Path("data/telegram_polling")


def build_runtime_from_env() -> PollingRuntime:
    settings = get_settings()
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required for polling")
    state = default_state_dir()
    return PollingRuntime(
        token=token,
        offset_store=OffsetStore(state / "polling_offset.json"),
        lock=ProcessLock(state / "polling.lock"),
        long_poll_timeout=int(
            getattr(settings, "telegram_polling_timeout_seconds", None)
            or DEFAULT_TIMEOUT_S
        ),
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # httpx INFO logs full request URLs (would include bot token) — keep warnings only.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        runtime = build_runtime_from_env()
    except Exception as exc:  # noqa: BLE001
        print(f"polling_init_failed err={sanitize_telegram_error(str(exc))}", file=sys.stderr)
        return 2

    def _stop(*_a):
        runtime.request_stop()

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    try:
        return runtime.run_forever()
    except WebhookConflictError as exc:
        print(f"webhook_conflict={exc}", file=sys.stderr)
        return 3
    except PollingLockError as exc:
        print(f"polling_lock={exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
