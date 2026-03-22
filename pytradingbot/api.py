import asyncio
import copy
import warnings
from contextlib import asynccontextmanager
from typing import List

import uiauth
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates

from pytradingbot import storage
from pytradingbot.constants import LOGGER, ScanStatus, config, env
from pytradingbot.routes import (
    dashboard,
    get_logs,
    get_schedule,
    get_versions,
    run_scan_job,
    scan_status,
    start_scan,
    update_schedule,
)
from pytradingbot.scheduler import ScanScheduler


@asynccontextmanager
async def lifespan(app_: FastAPI):
    """Initialize app state.

    Loads the latest historical snapshot from the SQLite DB so the dashboard
    shows data immediately on restart without requiring a fresh scan.
    """
    LOGGER.debug("Starting application lifespan initialization.")
    app_.state.templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
    LOGGER.debug("Templates initialized from %s", config.TEMPLATES_DIR)

    # Pre-populate from the last saved scan (if any)
    latest_ts, latest_data = storage.latest_version()
    app_.state.scan_data = latest_data
    app_.state.last_scan_ts = latest_ts
    app_.state.scan_status = ScanStatus.DONE if latest_data else ScanStatus.IDLE
    app_.state.scan_error = None
    app_.state.last_scan_completed = None  # no cooldown on cold start
    app_.state.current_filters = dict(config.DEFAULT_FILTERS)
    app_.state.scan_lock = asyncio.Lock()
    app_.state.scan_source = None
    app_.state.last_scheduler_minute = None
    app_.state.schedule_config = storage.load_schedule() or copy.deepcopy(config.DEFAULT_SCHEDULE)
    LOGGER.debug(
        "App state primed. last_scan_ts=%s scan_status=%s schedule_enabled=%s",
        latest_ts,
        app_.state.scan_status,
        app_.state.schedule_config.get("enabled", True),
    )

    app_.state.scheduler = ScanScheduler(app_, trigger_scan=run_scan_job)
    app_.state.scheduler.start()
    LOGGER.info("Scheduler initialized and started.")

    LOGGER.info("Loaded latest scan from %s with %d stocks.", latest_ts, len(latest_data))
    LOGGER.info("Server started.")

    yield  # Server is running

    LOGGER.debug("Application shutdown requested.")
    await app_.state.scheduler.stop()
    LOGGER.info("Server stopped.")


def get_routes() -> List[APIRoute]:
    """Return a list of all routes available.

    Returns:
        List[APIRoute]:
        A list of all routes available.
    """
    LOGGER.debug("Building API route table.")
    return [
        APIRoute(
            path="/",
            endpoint=dashboard,
            methods=["GET"],
            include_in_schema=False,
            response_class=HTMLResponse,
        ),
        APIRoute(
            path="/scan",
            endpoint=start_scan,
            methods=["POST"],
            include_in_schema=False,
            response_class=JSONResponse,
        ),
        APIRoute(
            path="/scan/status",
            endpoint=scan_status,
            methods=["GET"],
            include_in_schema=False,
            response_class=JSONResponse,
        ),
        APIRoute(
            path="/versions",
            endpoint=get_versions,
            methods=["GET"],
            include_in_schema=False,
            response_class=JSONResponse,
        ),
        APIRoute(
            path="/logs",
            endpoint=get_logs,
            methods=["GET"],
            include_in_schema=False,
            response_class=JSONResponse,
        ),
        APIRoute(
            path="/schedule",
            endpoint=get_schedule,
            methods=["GET"],
            include_in_schema=False,
            response_class=JSONResponse,
        ),
        APIRoute(
            path="/schedule",
            endpoint=update_schedule,
            methods=["POST"],
            include_in_schema=False,
            response_class=JSONResponse,
        ),
    ]


app = FastAPI(title="Trading Bot Dashboard", lifespan=lifespan)
app.__name__ = "app"
api_routes = get_routes()
if all((env.USERNAME, env.PASSWORD)):
    LOGGER.info("UI auth is enabled for protected routes.")
    uiauth.protect(
        app=app,
        username=env.USERNAME,
        password=env.PASSWORD,
        routes=api_routes,
    )
else:
    LOGGER.warning("USERNAME and PASSWORD are not set. API endpoints are unprotected.")
    warnings.warn(
        "USERNAME and PASSWORD are not set. API endpoints are unprotected.",
        UserWarning,
    )
    app.routes.extend(api_routes)
    LOGGER.debug("Routes attached directly to app without auth wrapper.")
app.routes.append(
    APIRoute(
        path="/health",
        endpoint=lambda: {"status": "ok"},
        methods=["GET"],
        include_in_schema=False,
    )
)

# TODO:
#   Extend Telegram support to score an individual ticker
#   Include multiple candlestick trackers using webull, Alpha Vantage etc
