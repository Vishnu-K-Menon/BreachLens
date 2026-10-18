"""Scale test (PLAN M5, ADR-051/066): time each stage on the 50k-row claims file.

The real stages run on `data/raw/scale/large_claims.csv`: sheet_track (read, layout,
column mapping incl. ML, repair), normalize, validate, address (offline: cache only,
no 50k Census call), privacy, resolve and notify. OCR is not part of it (ADR-026).
`scale_report.json` (rows/sec and process peak memory per stage) goes through the
guarded writer to `data/output/<run_id>/`.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from breachlens.context import Context

logger = logging.getLogger(__name__)


def peak_memory_mb() -> float | None:
    """Peak resident memory of this process so far, in MB."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class PMC(ctypes.Structure):
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

        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return round(pmc.PeakWorkingSetSize / 2**20, 1)
        return None
    import resource

    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(kb / (2**20 if sys.platform == "darwin" else 2**10), 1)


def run_scale(ctx: Context) -> dict[str, Any]:
    import pandas as pd

    from breachlens.pipeline import enabled_stages

    ctx.offline = True  # never send 50k addresses to Census
    stages = [(n, f) for n, f in enabled_stages(ctx.config) if n != "pdf_track"]
    df = pd.DataFrame()
    rows: list[dict[str, Any]] = []
    t_all = time.perf_counter()
    for name, fn in stages:
        n_in = len(df)
        t0 = time.perf_counter()
        df = fn(df, ctx)
        secs = time.perf_counter() - t0
        n = max(n_in, len(df))
        rows.append(
            {
                "stage": name,
                "seconds": round(secs, 2),
                "rows_in": n_in,
                "rows_out": len(df),
                "rows_per_sec": round(n / secs, 1) if secs > 0 else None,
                "peak_mb": peak_memory_mb(),
            }
        )
        logger.info("scale %s: %.1fs, %d rows", name, secs, len(df))
    total = time.perf_counter() - t_all
    res = ctx.tables.get("resolve_summary", {})
    return {
        "run_id": ctx.run_id,
        "input": str(
            ctx.paths.input_dir.relative_to(ctx.paths.root)
            if ctx.paths.input_dir.is_relative_to(ctx.paths.root)
            else ctx.paths.input_dir
        ),
        "rows": len(df),
        "stages": rows,
        "total_seconds": round(total, 2),
        "rows_per_sec_end_to_end": round(len(df) / total, 1) if total else None,
        "peak_mb": peak_memory_mb(),
        "candidate_pairs": res.get("candidate_pairs"),
        "ssn_guarded_pairs_unscored": res.get("ssn_guarded_unscored"),
        "people": res.get("people"),
        "census": "offline (cache only); addresses not in the cache are NOT_CHECKED",
        "excluded": "OCR (ADR-026); the PDF track has no input here",
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
    }


def main(config: Path, input_file: Path) -> tuple[dict[str, Any], Path]:
    from breachlens.pipeline import load_context
    from breachlens.privacy.leak_guard import LeakGuard
    from breachlens.privacy.writer import GuardedWriter

    ctx = load_context(config, input_dir=input_file.parent.resolve())
    report = run_scale(ctx)
    w = GuardedWriter(LeakGuard(ctx.config.privacy.leak_guard), ctx.paths.run_dir)
    return report, w.write_json(report, "scale_report.json")


__all__ = ["Path", "main", "peak_memory_mb", "run_scale"]
