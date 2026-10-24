"""Single-flight locks for news scheduler (one active run per DB).

Primary mechanism: OS advisory lock on a file held open for the critical section.
Works across processes that share the same filesystem (single-host Docker Compose
named/bind volumes). PID liveness is NOT used for ownership — container PID
namespaces make cross-container PID checks meaningless.

Not a multi-host / networked-filesystem lock. Document single-host only.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import TextIO


class SchedulerLockError(RuntimeError):
    """Another scheduler process or run holds the lock."""


def db_fingerprint(database_url: str) -> str:
    """Stable short id for lock/status files — not a path leak to clients."""
    raw = (database_url or "").strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


class InterprocessFileLock:
    """Exclusive lock via fcntl (Unix) / msvcrt (Windows), held on open FD.

    Acquire keeps ``self._fh`` open until ``release()``. Kernel drops the lock
    when the process dies, so stale locks recover without PID heuristics.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh: TextIO | None = None

    def acquire(self) -> None:
        if self._fh is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Open for read/write; create if missing. Do not truncate under contention.
        fh = open(self.path, "a+b")  # noqa: SIM115
        try:
            self._lock_fd(fh)
        except SchedulerLockError:
            fh.close()
            raise
        try:
            fh.seek(0)
            fh.truncate()
            meta = (
                f"pid={os.getpid()}\n"
                f"host={os.environ.get('HOSTNAME') or os.environ.get('COMPUTERNAME') or ''}\n"
            ).encode("utf-8")
            fh.write(meta)
            fh.flush()
        except OSError:
            pass
        self._fh = fh

    def release(self) -> None:
        fh = self._fh
        self._fh = None
        if fh is None:
            return
        try:
            self._unlock_fd(fh)
        finally:
            try:
                fh.close()
            except OSError:
                pass

    def held_by_other(self) -> bool:
        """Try a non-blocking probe; True if another holder exists."""
        if self._fh is not None:
            return False
        probe = InterprocessFileLock(self.path)
        try:
            probe.acquire()
        except SchedulerLockError:
            return True
        probe.release()
        return False

    @staticmethod
    def _lock_fd(fh: TextIO) -> None:
        if sys.platform == "win32":
            import msvcrt

            try:
                fh.seek(0)
                if fh.read(1) == b"":
                    fh.write(b"\0")
                    fh.flush()
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise SchedulerLockError("lock busy") from exc
            return
        import fcntl

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SchedulerLockError("lock busy") from exc
        except OSError as exc:
            raise SchedulerLockError("lock busy") from exc

    @staticmethod
    def _unlock_fd(fh: TextIO) -> None:
        if sys.platform == "win32":
            import msvcrt

            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            return
        import fcntl

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


# Backward-compatible name used by scheduler_run / worker.
PidFileLock = InterprocessFileLock
