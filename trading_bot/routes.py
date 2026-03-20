import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from trading_bot import storage
from trading_bot.constants import DEFAULT_FILTERS, LOGGER, SCAN_COOLDOWN_SECONDS
from trading_bot.main import builder


class ScanRequest(BaseModel):
    """Scan Request model."""

    filters: dict | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _cooldown_remaining(request: Request) -> int:
    """Seconds left in the post-scan cooldown (0 means free to scan)."""
    last: datetime | None = getattr(request.app.state, "last_scan_completed", None)
    if last is None:
        return 0
    elapsed = (datetime.now() - last).total_seconds()
    return max(0, int(SCAN_COOLDOWN_SECONDS - elapsed))


def _render(
    request: Request,
    *,
    version_ts: str | None = None,
    version_data: list | None = None,
) -> HTMLResponse:
    """Render the dashboard template.

    When *version_ts* / *version_data* are supplied the template shows that
    historical snapshot.  The live scan-status badge always reflects the real
    current state from ``app.state``.
    """
    viewing_version = version_ts is not None and version_data is not None

    if viewing_version:
        displayed_stocks = version_data
        displayed_timestamp = version_ts
        current_version = version_ts
    else:
        displayed_stocks = getattr(request.app.state, "scan_data", [])
        displayed_timestamp = getattr(request.app.state, "last_scan_ts", None)
        current_version = getattr(request.app.state, "last_scan_ts", None)

    return request.app.state.templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stocks": displayed_stocks,
            "timestamp": displayed_timestamp,
            "scan_status": getattr(request.app.state, "scan_status", "idle"),
            "scan_error": getattr(request.app.state, "scan_error", None),
            "filters": getattr(request.app.state, "current_filters", dict(DEFAULT_FILTERS)),
            "default_filters": dict(DEFAULT_FILTERS),
            "cooldown_remaining": _cooldown_remaining(request),
            "cooldown_seconds": SCAN_COOLDOWN_SECONDS,
            "current_version": current_version,
        },
    )


# ── Route handlers ────────────────────────────────────────────────────────────


def dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard, optionally at a historical *?version=* snapshot."""
    version = request.query_params.get("version")
    if version:
        data = storage.load_version(version)
        if data is not None:
            return _render(request, version_ts=version, version_data=data)
    return _render(request)


async def start_scan(request: Request, body: ScanRequest) -> JSONResponse:
    """Start a background scan.  Enforces a 60-second post-scan cooldown."""
    # ── Cooldown gate ──────────────────────────────────────────────────────
    remaining = _cooldown_remaining(request)
    if remaining > 0:
        return JSONResponse(
            {"status": "cooldown", "remaining_seconds": remaining},
            status_code=429,
        )

    if getattr(request.app.state, "scan_status", "idle") == "running":
        return JSONResponse({"status": "already_running"}, status_code=202)

    filters = body.filters if body.filters else dict(request.app.state.current_filters)
    request.app.state.current_filters = filters
    request.app.state.scan_status = "running"
    request.app.state.scan_error = None

    async def _run_scan() -> None:
        try:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                data = await loop.run_in_executor(pool, lambda: builder(to_dict=True, filters=filters))

            # Canonical display timestamp — also used as the shelve key
            ts = datetime.now().strftime("%Y-%m-%d %I:%M %p ") + time.strftime("%Z")
            storage.save_scan(ts, data)

            request.app.state.scan_data = data
            request.app.state.last_scan_ts = ts
            request.app.state.last_scan_completed = datetime.now()
            request.app.state.scan_status = "done"
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Scan failed with filters %s: %s", filters, exc)
            request.app.state.scan_status = "error"
            request.app.state.scan_error = str(exc)[:300]

    asyncio.create_task(_run_scan())
    return JSONResponse({"status": "started"}, status_code=202)


def scan_status(request: Request) -> JSONResponse:
    """Poll endpoint: returns current status, result count, timestamp, and cooldown."""
    return JSONResponse(
        {
            "status": getattr(request.app.state, "scan_status", "idle"),
            "error": getattr(request.app.state, "scan_error", None),
            "count": len(getattr(request.app.state, "scan_data", [])),
            "timestamp": getattr(request.app.state, "last_scan_ts", None),
            "cooldown_remaining": _cooldown_remaining(request),
        }
    )


def get_versions() -> JSONResponse:
    """Return all stored scan snapshots newest-first as ``[{timestamp, count}]``."""
    return JSONResponse(storage.list_versions())


def get_logs() -> JSONResponse:
    """Stream the latest log file (last 500 lines)."""
    log_dir = Path(__file__).parent.parent / "logs"
    files = sorted(log_dir.glob("trading_bot_*.log"), reverse=True) if log_dir.exists() else []
    if not files:
        return JSONResponse({"content": "No log files found.", "filename": None, "total_lines": 0})
    latest = files[0]
    try:
        lines = latest.read_text(errors="replace").splitlines()
        return JSONResponse(
            {
                "content": "\n".join(lines[-500:]),
                "filename": latest.name,
                "total_lines": len(lines),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"content": f"Error reading log: {exc}", "filename": latest.name, "total_lines": 0})
