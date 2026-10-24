"""Path confinement for bank materials manifests (no tool binaries executed)."""

from __future__ import annotations

from pathlib import Path


class PathEscapeError(ValueError):
    """Raised when a declared path resolves outside an allowed root."""


def resolve_under(root: Path, relative: str | Path, *, field: str) -> Path:
    """Resolve ``relative`` under ``root``; reject absolute / ``..`` escapes."""
    root_r = root.resolve()
    raw = Path(relative)
    if raw.is_absolute():
        raise PathEscapeError(f"{field}: absolute path not allowed: {relative!r}")
    candidate = (root_r / raw).resolve()
    try:
        candidate.relative_to(root_r)
    except ValueError as exc:
        raise PathEscapeError(
            f"{field}: path escapes allowed root {root_r}: {relative!r}"
        ) from exc
    return candidate


def ensure_dir_allowed(path: Path, *roots: Path, field: str) -> Path:
    """Ensure ``path`` resolves inside one of ``roots``."""
    resolved = path.resolve()
    for root in roots:
        root_r = root.resolve()
        try:
            resolved.relative_to(root_r)
            return resolved
        except ValueError:
            continue
    raise PathEscapeError(
        f"{field}: {resolved} is outside allowed roots {[str(r.resolve()) for r in roots]}"
    )
