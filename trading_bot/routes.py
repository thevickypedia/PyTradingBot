import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from trading_bot.constants import DEFAULT_FILTERS, LOGGER
from trading_bot.main import builder


# ── Request schemas ──────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    filters: dict | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _render(request: Request) -> HTMLResponse:
    last_scanned: datetime | None = getattr(request.app.state, "last_scanned", None)
    return request.app.state.templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stocks": getattr(request.app.state, "scan_data", []),
            "timestamp": last_scanned.strftime("%b %d, %Y  %I:%M:%S %p") if last_scanned else None,
            "scan_status": getattr(request.app.state, "scan_status", "idle"),
            "scan_error": getattr(request.app.state, "scan_error", None),
            "filters": getattr(request.app.state, "current_filters", dict(DEFAULT_FILTERS)),
            "default_filters": dict(DEFAULT_FILTERS),
        },
    )


# ── Routes ────────────────────────────────────────────────────────────────────

def dashboard(request: Request) -> HTMLResponse:
    return _render(request)


async def start_scan(request: Request, body: ScanRequest) -> JSONResponse:
    """Start a background stock scan. Returns immediately with 202."""
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
                data = await loop.run_in_executor(
                    pool, lambda: builder(to_dict=True, filters=filters)
                )
            request.app.state.scan_data = data
            request.app.state.last_scanned = datetime.now()
            request.app.state.scan_status = "done"
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Scan failed with filters %s: %s", filters, exc)
            request.app.state.scan_status = "error"
            # Truncate to avoid flooding the UI with a multi-KB traceback
            request.app.state.scan_error = str(exc)[:300]

    asyncio.create_task(_run_scan())
    return JSONResponse({"status": "started"}, status_code=202)


def scan_status(request: Request) -> JSONResponse:
    last: datetime | None = getattr(request.app.state, "last_scanned", None)
    return JSONResponse({
        "status": getattr(request.app.state, "scan_status", "idle"),
        "error": getattr(request.app.state, "scan_error", None),
        "count": len(getattr(request.app.state, "scan_data", [])),
        "timestamp": last.strftime("%b %d, %Y  %I:%M:%S %p") if last else None,
    })


def get_logs() -> JSONResponse:
    log_dir = Path(__file__).parent.parent / "logs"
    files = sorted(log_dir.glob("trading_bot_*.log"), reverse=True) if log_dir.exists() else []
    if not files:
        return JSONResponse({"content": "No log files found.", "filename": None, "total_lines": 0})
    latest = files[0]
    try:
        lines = latest.read_text(errors="replace").splitlines()
        # Return last 500 lines to keep the response size manageable
        return JSONResponse({
            "content": "\n".join(lines[-500:]),
            "filename": latest.name,
            "total_lines": len(lines),
        })
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"content": f"Error reading log: {exc}", "filename": latest.name, "total_lines": 0})
