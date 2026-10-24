# -*- coding: utf-8 -*-
"""Single-container orchestrator for Telegram Compose smoke (mocked Bot API).

Order: alembic→010 prepare → uvicorn → scheduler once → smoke checks → stop.
No live Telegram / LLM. Does not touch main-stand processes.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _wait_health(url: str, timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"health timeout {url}: {last}")


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    print("=== prepare (alembic → 010) ===", flush=True)
    prep = subprocess.run(
        [sys.executable, "scripts/prepare_telegram_compose_smoke_stand.py"],
        check=False,
    )
    if prep.returncode != 0:
        return prep.returncode

    # Entrypoint gates (same binaries as competition image)
    print("=== entrypoint gates ===", flush=True)
    env_base = os.environ.copy()
    w = subprocess.run(
        ["/entrypoint-telegram-worker.sh"],
        env={**env_base, "TELEGRAM_BOT_TOKEN": ""},
        check=False,
    )
    p = subprocess.run(
        ["/entrypoint-telegram-polling.sh"],
        env={
            **env_base,
            "TELEGRAM_BOT_TOKEN": "fake",
            "TELEGRAM_INGRESS_MODE": "webhook",
        },
        check=False,
    )
    print(f"worker_rc={w.returncode} polling_rc={p.returncode}", flush=True)
    if w.returncode != 2 or p.returncode != 3:
        print("entrypoint gates failed", file=sys.stderr)
        return 1

    print("=== api (uvicorn) ===", flush=True)
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=str(ROOT),
        env=os.environ.copy(),
    )
    try:
        _wait_health("http://127.0.0.1:8000/health")
        print("=== scheduler --once --fixtures ===", flush=True)
        sched = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.workers.news_scheduler",
                "--once",
                "--fixtures",
            ],
            check=False,
            env={**os.environ, "NEWS_SCHEDULER_USE_FIXTURES": "1"},
        )
        if sched.returncode != 0:
            print(f"scheduler_once rc={sched.returncode}", file=sys.stderr)
            return sched.returncode or 1

        print("=== smoke_telegram_compose ===", flush=True)
        os.environ["SMOKE_API_BASE"] = "http://127.0.0.1:8000"
        smoke = subprocess.run(
            [sys.executable, "scripts/smoke_telegram_compose.py"],
            check=False,
        )
        return smoke.returncode
    finally:
        api.send_signal(signal.SIGTERM)
        try:
            api.wait(timeout=10)
        except subprocess.TimeoutExpired:
            api.kill()


if __name__ == "__main__":
    raise SystemExit(main())
