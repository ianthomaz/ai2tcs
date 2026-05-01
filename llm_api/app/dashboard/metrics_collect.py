"""Host-side metrics for the dashboard Usage page (psutil + Ollama HTTP).

RAM/CPU reflect the Python process view (often the Docker cgroup), not necessarily
the full physical machine. Ollama /api/ps reports model memory as declared by Ollama.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def psutil_host_snapshot() -> dict[str, Any]:
    """CPU and RAM for the current environment (container or host)."""
    try:
        import psutil as ps

        vm = ps.virtual_memory()
        cpu = ps.cpu_percent(interval=0.12)
        return {
            "ok": True,
            "cpu_percent": round(float(cpu), 1),
            "ram_percent": round(float(vm.percent), 1),
            "ram_used_bytes": int(vm.used),
            "ram_total_bytes": int(vm.total),
            "ram_available_bytes": int(vm.available),
        }
    except Exception as e:
        logger.warning("psutil snapshot failed: %s", e)
        return {"ok": False, "error": str(e)}


async def fetch_ollama_ps_payload() -> dict[str, Any]:
    url = f"{settings.ollama_host.rstrip('/')}/api/ps"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return {"ok": False, "error": f"HTTP {r.status_code}", "models": []}
            data = r.json()
            raw = data.get("models")
            models = raw if isinstance(raw, list) else []
            return {"ok": True, "models": models, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e), "models": []}


def _fmt_gib(n: int) -> str:
    if n <= 0:
        return "0"
    return f"{n / (1024**3):.1f}"


def build_ollama_memory_gauges(
    ps_payload: dict[str, Any],
    *,
    reference_gib: float,
) -> dict[str, Any]:
    """
    Per-model and total memory bars vs a reference GiB (e.g. unified 32 GB machine).
    Uses max(size_vram, size) per model when counting 'footprint' for the bar.
    """
    ref_bytes = max(1.0, float(reference_gib)) * (1024**3)
    models_out: list[dict[str, Any]] = []
    total_footprint = 0
    if not ps_payload.get("ok"):
        return {
            "ok": False,
            "error": ps_payload.get("error"),
            "models": [],
            "total_footprint_bytes": 0,
            "total_footprint_gib": "0",
            "total_vs_ref_percent": 0.0,
            "total_dash_offset_fraction": 1.0,
            "reference_gib": reference_gib,
        }

    for m in ps_payload.get("models") or []:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name") or m.get("model") or "?")
        try:
            vram = int(m.get("size_vram") or 0)
        except (TypeError, ValueError):
            vram = 0
        try:
            resident = int(m.get("size") or 0)
        except (TypeError, ValueError):
            resident = 0
        footprint = max(vram, resident)
        total_footprint += footprint
        pct = min(100.0, 100.0 * footprint / ref_bytes) if ref_bytes else 0.0
        models_out.append(
            {
                "name": name,
                "vram_bytes": vram,
                "resident_bytes": resident,
                "footprint_bytes": footprint,
                "footprint_gib": _fmt_gib(footprint),
                "bar_percent": round(pct, 1),
                "dash_offset_fraction": max(0.0, min(1.0, 1.0 - pct / 100.0)),
            }
        )

    total_pct = min(100.0, 100.0 * total_footprint / ref_bytes) if ref_bytes else 0.0
    return {
        "ok": True,
        "error": None,
        "models": models_out,
        "total_footprint_bytes": total_footprint,
        "total_footprint_gib": _fmt_gib(total_footprint),
        "total_vs_ref_percent": round(total_pct, 1),
        "total_dash_offset_fraction": max(0.0, min(1.0, 1.0 - total_pct / 100.0)),
        "reference_gib": reference_gib,
    }


def ram_gauge_arc(host: dict[str, Any]) -> dict[str, Any]:
    """SVG semicircle: stroke-dashoffset = arc_len * dash_offset_fraction hides unfilled part."""
    if not host.get("ok"):
        return {"dash_offset_fraction": 1.0, "label_pct": 0.0}
    p = float(host.get("ram_percent") or 0)
    p = max(0.0, min(100.0, p))
    return {"dash_offset_fraction": 1.0 - p / 100.0, "label_pct": round(p, 1)}


def cpu_gauge_arc(host: dict[str, Any]) -> dict[str, Any]:
    if not host.get("ok"):
        return {"dash_offset_fraction": 1.0, "label_pct": 0.0}
    p = float(host.get("cpu_percent") or 0)
    p = max(0.0, min(100.0, p))
    return {"dash_offset_fraction": 1.0 - p / 100.0, "label_pct": round(p, 1)}
