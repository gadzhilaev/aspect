"""One-off verification import driver for real competition CSVs."""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VER = ROOT / "data" / "case" / "verification"


def _sample_peak_working_set() -> int | None:
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        return int(counters.PeakWorkingSetSize) if ok else None
    except Exception:
        return None


def main() -> int:
    url = (VER / "latest_db_url.txt").read_text(encoding="utf-8").strip()
    db_path = Path((VER / "latest_db_path.txt").read_text(encoding="utf-8").strip())
    report_dir = VER / "reports" / "import_hack_raw_v2"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_path = VER / "import_run.log"
    status_path = VER / "import_status.json"

    def log(msg: str) -> None:
        line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
        print(msg, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    from app.services.case_data.import_pipeline import redact_database_url, run_case_import

    log(f"start load db={redact_database_url(url)}")
    status_path.write_text(
        json.dumps(
            {"phase": "running", "started_at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    t0 = time.perf_counter()
    try:
        result = run_case_import(
            input_dir=(ROOT / "data" / "case" / "raw").resolve(),
            database_url=url,
            slot_key="competition_default",
            version_label="hack-raw-v2",
            report_dir=report_dir,
            batch_size=2000,
        )
        elapsed = time.perf_counter() - t0
        # Keep status JSON compact (avoid huge SQLite error SQL dumps).
        report = dict(result.report or {})
        if "error" in report and isinstance(report["error"], str) and len(report["error"]) > 800:
            report["error"] = report["error"][:800] + "…"
        out = {
            "phase": "finished",
            "status": result.status,
            "snapshot_id": result.snapshot_id,
            "import_run_id": result.import_run_id,
            "reason": result.reason,
            "manifest": result.manifest,
            "report": report,
            "elapsed_sec": round(elapsed, 3),
            "db_path": str(db_path),
            "db_size_bytes": db_path.stat().st_size if db_path.exists() else None,
            "peak_working_set_bytes": _sample_peak_working_set(),
            "peak_working_set_note": (
                "Windows GetProcessMemoryInfo PeakWorkingSetSize for this Python "
                "process at end of import; not tracemalloc; not full OS RSS accounting"
            ),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        status_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"done status={result.status} snapshot={result.snapshot_id} elapsed={elapsed:.1f}s")
        return 0 if result.status in {"ready", "identical_skip"} else 1
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        err = {
            "phase": "error",
            "error": str(exc)[:800],
            "traceback": traceback.format_exc()[-4000:],
            "elapsed_sec": round(elapsed, 3),
            "db_path": str(db_path),
            "db_size_bytes": db_path.stat().st_size if db_path.exists() else None,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        status_path.write_text(json.dumps(err, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"ERROR {exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
