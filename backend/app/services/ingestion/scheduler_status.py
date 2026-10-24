"""Persisted scheduler status — safe for public API (no DB paths / secrets)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

RunStatus = Literal["success", "partial", "failed", "running", "skipped_busy"]

_SAFE_ERR = re.compile(r"^[a-zA-Z0-9_.:-]{1,80}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_source_error(raw: str) -> str | None:
    """Keep provider:kind:code style; drop URLs, paths, tokens."""
    text = (raw or "").strip()
    if not text:
        return None
    # Strip anything that looks like a URL or absolute path / secret
    if "://" in text or ":\\" in text or text.startswith("/") or "token" in text.lower():
        return "source_error"
    if len(text) > 120:
        text = text[:120]
    if not _SAFE_ERR.match(text.replace("/", ".")):
        safe_parts = []
        for part in text.split(":"):
            p = re.sub(r"[^a-zA-Z0-9_.-]", "", part)[:40]
            if p:
                safe_parts.append(p)
        return ":".join(safe_parts)[:80] or "source_error"
    return text


def classify_outcome(*, errors: list[str], crashed: bool = False) -> RunStatus:
    if crashed:
        return "failed"
    if errors:
        return "partial"
    return "success"


class SchedulerStatusStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def mark_running(self, *, started_at: datetime | None = None) -> dict[str, Any]:
        data = self.load()
        started = started_at or _utc_now()
        data["status"] = "running"
        data["last_attempt_started_at"] = _iso(started)
        data["last_attempt_finished_at"] = None
        data.pop("last_attempt_outcome", None)
        self.save(data)
        return data

    def mark_finished(
        self,
        *,
        outcome: RunStatus,
        started_at: datetime,
        finished_at: datetime | None = None,
        fetched: int = 0,
        inserted: int = 0,
        duplicates: int = 0,
        published: int = 0,
        source_errors: list[str] | None = None,
        interval_seconds: int = 1200,
        skipped: bool = False,
    ) -> dict[str, Any]:
        data = self.load()
        end = finished_at or _utc_now()
        errs = [e for e in (sanitize_source_error(x) for x in (source_errors or [])) if e]
        data["status"] = outcome
        data["last_attempt_started_at"] = _iso(started_at)
        data["last_attempt_finished_at"] = _iso(end)
        data["last_attempt_outcome"] = outcome
        data["last_attempt_skipped"] = bool(skipped)
        data["counts"] = {
            "fetched": int(fetched),
            "inserted": int(inserted),
            "duplicates": int(duplicates),
            "published": int(published),
        }
        data["source_errors"] = errs
        # Only fully successful runs update "last successful refresh"
        if outcome == "success" and not skipped:
            data["last_success_at"] = _iso(end)
            data["last_success_counts"] = dict(data["counts"])
        data["next_run_at"] = _iso(end + timedelta(seconds=max(1, int(interval_seconds))))
        data["interval_seconds"] = int(interval_seconds)
        self.save(data)
        return data

    def public_view(self) -> dict[str, Any]:
        """Client-safe snapshot (no paths, no internal stacks)."""
        data = self.load()
        status = data.get("status")
        if status not in {"success", "partial", "failed", "running", "skipped_busy"}:
            status = None
        counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
        return {
            "status": status,
            "last_attempt_started_at": data.get("last_attempt_started_at"),
            "last_attempt_finished_at": data.get("last_attempt_finished_at"),
            "last_success_at": data.get("last_success_at"),
            "next_run_at": data.get("next_run_at"),
            "interval_seconds": data.get("interval_seconds"),
            "counts": {
                "fetched": int(counts.get("fetched") or 0),
                "inserted": int(counts.get("inserted") or 0),
                "duplicates": int(counts.get("duplicates") or 0),
                "published": int(counts.get("published") or 0),
            },
            "source_errors": list(data.get("source_errors") or [])[:20],
            # Feed-friendly: when sources were last checked (attempt end, any outcome)
            "sources_checked_at": data.get("last_attempt_finished_at")
            or data.get("last_attempt_started_at"),
            "sources_check_ok": status == "success",
        }


def resolve_status_path(state_dir: Path, database_url: str) -> Path:
    from app.services.ingestion.scheduler_lock import db_fingerprint

    return state_dir / f"status_{db_fingerprint(database_url)}.json"
