import asyncio
import copy
import re
import time
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from pytradingbot import storage
from pytradingbot.constants import (
    DEFAULT_FILTERS,
    DEFAULT_SCHEDULE,
    LOGGER,
    LOGS_DIR,
    SCAN_COOLDOWN_SECONDS,
    ScanStatus,
)
from pytradingbot.main import builder


class ScanRequest(BaseModel):
    """Scan Request model."""

    filters: dict | None = None


class ScheduleRequest(BaseModel):
    """Schedule override payload."""

    enabled: bool = True
    windows: list[dict] = Field(default_factory=list)
    after_hours: dict = Field(default_factory=dict)


def _cooldown_remaining(request: Request) -> int:
    """Seconds left in the post-scan cooldown (0 means free to scan)."""
    last: datetime | None = getattr(request.app.state, "last_scan_completed", None)
    if last is None:
        LOGGER.debug("Cooldown check for request returned 0 because no scan has completed yet.")
        return 0
    elapsed = (datetime.now() - last).total_seconds()
    remaining = max(0, int(SCAN_COOLDOWN_SECONDS - elapsed))
    LOGGER.debug("Cooldown check for request returned %s seconds remaining.", remaining)
    return remaining


def _cooldown_remaining_app(app: FastAPI) -> int:
    """Cooldown remain in app state."""
    last: datetime | None = getattr(app.state, "last_scan_completed", None)
    if last is None:
        LOGGER.debug("App cooldown check returned 0 because no scan has completed yet.")
        return 0
    elapsed = (datetime.now() - last).total_seconds()
    remaining = max(0, int(SCAN_COOLDOWN_SECONDS - elapsed))
    LOGGER.debug("App cooldown check returned %s seconds remaining.", remaining)
    return remaining


def _validate_time(value: str) -> str:
    """Validate time format."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError("Time must be in HH:MM 24-hour format.")
    hour, minute = value.split(":", maxsplit=1)
    h = int(hour)
    m = int(minute)
    if h < 0 or h > 23 or m < 0 or m > 59:
        raise ValueError("Time must be in HH:MM 24-hour format.")
    return f"{h:02d}:{m:02d}"


def _normalize_schedule(payload: ScheduleRequest) -> dict:
    """Normalize schedule payload."""
    LOGGER.debug("Normalizing schedule payload. enabled=%s windows=%d", payload.enabled, len(payload.windows))
    defaults = copy.deepcopy(DEFAULT_SCHEDULE)
    ordered_ids = [window["id"] for window in defaults["windows"]]
    windows_by_id = {window["id"]: window for window in defaults["windows"]}

    normalized_windows: list[dict] = []
    for window in payload.windows:
        window_id = str(window.get("id", "")).strip()
        if window_id not in windows_by_id:
            raise ValueError(f"Unknown schedule window: {window_id}")
        default_window = windows_by_id[window_id]

        start = _validate_time(str(window.get("start", default_window["start"])))
        end = _validate_time(str(window.get("end", default_window["end"])))
        interval_minutes = int(window.get("interval_minutes", default_window["interval_minutes"]))
        if interval_minutes <= 0 or interval_minutes > 240:
            LOGGER.warning("Rejected schedule interval %s for window %s.", interval_minutes, window_id)
            raise ValueError(f"Interval for {window_id} must be between 1 and 240 minutes.")
        if start == end:
            LOGGER.warning("Rejected schedule window %s because start and end were identical (%s).", window_id, start)
            raise ValueError(f"Start and end cannot be the same for {window_id}.")

        normalized_windows.append(
            {
                "id": window_id,
                "label": default_window["label"],
                "start": start,
                "end": end,
                "interval_minutes": interval_minutes,
                "enabled": bool(window.get("enabled", default_window.get("enabled", True))),
            }
        )

    found_ids = [row["id"] for row in normalized_windows]
    if set(found_ids) != set(ordered_ids) or len(found_ids) != len(set(found_ids)):
        LOGGER.warning("Rejected schedule payload because required windows were missing or duplicated: %s", found_ids)
        raise ValueError("All schedule windows are required in request payload.")

    normalized_windows.sort(key=lambda row: ordered_ids.index(row["id"]))

    after_hours_default = defaults["after_hours"]
    after_hours_payload = payload.after_hours or {}
    after_hours = {
        "enabled": bool(after_hours_payload.get("enabled", after_hours_default.get("enabled", True))),
        "run_time": _validate_time(str(after_hours_payload.get("run_time", after_hours_default["run_time"]))),
        "close": _validate_time(str(after_hours_payload.get("close", after_hours_default["close"]))),
    }
    if after_hours["run_time"] >= after_hours["close"]:
        LOGGER.warning(
            "Rejected after-hours schedule because run_time=%s was not before close=%s.",
            after_hours["run_time"],
            after_hours["close"],
        )
        raise ValueError("after_hours.run_time must be before after_hours.close")

    LOGGER.info("Schedule payload normalized successfully. enabled=%s", payload.enabled)

    return {
        "enabled": bool(payload.enabled),
        "windows": normalized_windows,
        "after_hours": after_hours,
    }


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
    LOGGER.debug("Rendering dashboard. viewing_version=%s version_ts=%s", viewing_version, version_ts)

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
            "scan_status": getattr(request.app.state, "scan_status", ScanStatus.IDLE),
            "scan_error": getattr(request.app.state, "scan_error", None),
            "filters": getattr(request.app.state, "current_filters", dict(DEFAULT_FILTERS)),
            "default_filters": dict(DEFAULT_FILTERS),
            "schedule": getattr(request.app.state, "schedule_config", copy.deepcopy(DEFAULT_SCHEDULE)),
            "default_schedule": copy.deepcopy(DEFAULT_SCHEDULE),
            "cooldown_remaining": _cooldown_remaining(request),
            "cooldown_seconds": SCAN_COOLDOWN_SECONDS,
            "current_version": current_version,
        },
    )


async def run_scan_job(app: FastAPI, filters: dict, source: str = "manual", bypass_cooldown: bool = False) -> bool:
    """Queue one background scan and update app state when it finishes."""
    lock: asyncio.Lock = app.state.scan_lock
    async with lock:
        if getattr(app.state, "scan_status", ScanStatus.IDLE) == ScanStatus.RUNNING:
            LOGGER.warning("Rejected %s scan request because a scan is already running.", source)
            return False
        if not bypass_cooldown and _cooldown_remaining_app(app) > 0:
            LOGGER.warning("Rejected %s scan request because cooldown is still active.", source)
            return False

        app.state.current_filters = filters
        app.state.scan_status = ScanStatus.RUNNING
        app.state.scan_error = None
        app.state.scan_source = source
        LOGGER.info("Accepted %s scan request with %d filters.", source, len(filters))
        LOGGER.debug("Scan filters for %s run: %s", source, filters)

    async def _run_scan() -> None:
        """Run background scan and update app state when it finishes."""
        try:
            LOGGER.debug("Background scan task started for source=%s.", source)
            data = await asyncio.to_thread(builder, to_dict=True, filters=filters)

            ts = datetime.now().strftime("%Y-%m-%d %I:%M %p ") + time.strftime("%Z")
            storage.save_scan(ts, data)

            app.state.scan_data = data
            app.state.last_scan_ts = ts
            app.state.last_scan_completed = datetime.now()
            app.state.scan_status = ScanStatus.DONE
            LOGGER.info("%s scan completed successfully at %s with %d records.", source, ts, len(data))
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Scan failed with filters %s (%s): %s", filters, source, exc)
            app.state.scan_status = ScanStatus.ERROR
            app.state.scan_error = str(exc)[:300]

    asyncio.create_task(_run_scan())
    return True


def dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard, optionally at a historical *?version=* snapshot."""
    version = request.query_params.get("version")
    LOGGER.debug("Dashboard requested. version=%s", version)
    if version:
        data = storage.load_version(version)
        if data is not None:
            LOGGER.info("Rendering requested historical version %s with %d records.", version, len(data))
            return _render(request, version_ts=version, version_data=data)
        LOGGER.warning("Requested dashboard version %s was not found; falling back to latest view.", version)
    return _render(request)


async def start_scan(request: Request, body: ScanRequest) -> JSONResponse:
    """Start a background scan.  Enforces a 60-second post-scan cooldown."""
    LOGGER.debug("Manual scan requested through API.")
    remaining = _cooldown_remaining(request)
    if remaining > 0:
        LOGGER.warning("Manual scan request blocked by cooldown. remaining_seconds=%s", remaining)
        return JSONResponse(
            {"status": "cooldown", "remaining_seconds": remaining},
            status_code=429,
        )

    filters = body.filters if body.filters else dict(request.app.state.current_filters)
    started = await run_scan_job(request.app, filters, "manual", False)
    if started:
        LOGGER.info("Manual scan request accepted.")
    else:
        LOGGER.warning("Manual scan request returned already_running.")
    return JSONResponse({"status": "started" if started else "already_running"}, status_code=202)


def scan_status(request: Request) -> JSONResponse:
    """Poll endpoint: returns current status, result count, timestamp, and cooldown."""
    LOGGER.debug(
        "Scan status requested. status=%s source=%s timestamp=%s",
        getattr(request.app.state, "scan_status", ScanStatus.IDLE),
        getattr(request.app.state, "scan_source", None),
        getattr(request.app.state, "last_scan_ts", None),
    )
    return JSONResponse(
        {
            "status": getattr(request.app.state, "scan_status", ScanStatus.IDLE),
            "error": getattr(request.app.state, "scan_error", None),
            "count": len(getattr(request.app.state, "scan_data", [])),
            "timestamp": getattr(request.app.state, "last_scan_ts", None),
            "source": getattr(request.app.state, "scan_source", "manual"),
            "cooldown_remaining": _cooldown_remaining(request),
        }
    )


def get_schedule(request: Request) -> JSONResponse:
    """Return current and default scheduler configuration."""
    LOGGER.debug("Schedule configuration requested.")
    return JSONResponse(
        {
            "schedule": getattr(request.app.state, "schedule_config", copy.deepcopy(DEFAULT_SCHEDULE)),
            "defaults": copy.deepcopy(DEFAULT_SCHEDULE),
        }
    )


def update_schedule(request: Request, body: ScheduleRequest) -> JSONResponse:
    """Persist scheduler configuration override."""
    LOGGER.debug("Schedule update requested.")
    try:
        normalized = _normalize_schedule(body)
    except ValueError as exc:
        LOGGER.warning("Schedule update rejected: %s", exc)
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=400)

    storage.save_schedule(normalized)
    request.app.state.schedule_config = normalized
    LOGGER.info("Schedule configuration saved successfully.")
    return JSONResponse({"status": "saved", "schedule": normalized})


def get_versions() -> JSONResponse:
    """Return all stored scan snapshots newest-first as ``[{timestamp, count}]``."""
    versions = storage.list_versions()
    LOGGER.debug("Returning %d stored scan versions.", len(versions))
    if not versions:
        LOGGER.warning("Versions requested but no stored scan snapshots were found.")
    return JSONResponse(versions)


def get_logs(request: Request) -> JSONResponse:
    """Return logs for a selected file, with optional file-list metadata."""
    include_all = request.query_params.get("all", "").lower() in {"1", "true", "yes"}
    requested_name = request.query_params.get("filename")

    LOGGER.debug("Log viewer requested logs. include_all=%s filename=%s", include_all, requested_name)
    files = sorted(LOGS_DIR.glob("pytradingbot_*.log"), reverse=True) if LOGS_DIR.exists() else []
    file_names = [file.name for file in files]

    if not files:
        LOGGER.warning("Log viewer requested logs but no log files were found.")
        return JSONResponse(
            {
                "content": "No log files found.",
                "filename": None,
                "selected_filename": None,
                "latest_filename": None,
                "total_lines": 0,
                "files": [],
                "is_current": False,
            }
        )

    latest = files[0]
    selected = latest
    if requested_name:
        selected_match = next((file for file in files if file.name == requested_name), None)
        if selected_match is None:
            LOGGER.warning("Requested log file %s was not found.", requested_name)
            return JSONResponse(
                {
                    "content": "",
                    "filename": None,
                    "selected_filename": None,
                    "latest_filename": latest.name,
                    "total_lines": 0,
                    "files": file_names if include_all else [],
                    "is_current": False,
                    "error": f"Requested log file not found: {requested_name}",
                },
                status_code=404,
            )
        selected = selected_match

    if include_all and not requested_name:
        LOGGER.debug("Returning metadata for %d log files without file content.", len(file_names))
        return JSONResponse(
            {
                "files": file_names,
                "latest_filename": latest.name,
            }
        )

    try:
        lines = selected.read_text(errors="replace").splitlines()
        is_current = selected.name == latest.name
        LOGGER.info("Returning log file %s with %d total lines (is_current=%s).", selected.name, len(lines), is_current)
        return JSONResponse(
            {
                "content": "\n".join(lines[-500:]),
                "filename": selected.name,
                "selected_filename": selected.name,
                "latest_filename": latest.name,
                "total_lines": len(lines),
                "files": file_names if include_all else [],
                "is_current": is_current,
            }
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to read log file %s: %s", selected, exc)
        return JSONResponse(
            {
                "content": f"Error reading log: {exc}",
                "filename": selected.name,
                "selected_filename": selected.name,
                "latest_filename": latest.name,
                "total_lines": 0,
                "files": file_names if include_all else [],
                "is_current": selected.name == latest.name,
            }
        )
