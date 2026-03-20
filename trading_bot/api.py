import warnings
from contextlib import asynccontextmanager
from typing import List

import uiauth
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates

from trading_bot import storage
from trading_bot.constants import (
    DEFAULT_FILTERS,
    LOGGER,
    PASSWORD,
    TEMPLATES_DIR,
    USERNAME,
    ScanStatus,
)
from trading_bot.routes import (
    dashboard,
    get_logs,
    get_versions,
    scan_status,
    start_scan,
)


@asynccontextmanager
async def lifespan(app_: FastAPI):
    """Initialize app state.

    Loads the latest historical snapshot from the shelve DB so the dashboard
    shows data immediately on restart without requiring a fresh scan.
    """
    app_.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Pre-populate from the last saved scan (if any)
    latest_ts, latest_data = storage.latest_version()
    app_.state.scan_data = latest_data
    app_.state.last_scan_ts = latest_ts
    app_.state.scan_status = ScanStatus.DONE if latest_data else ScanStatus.IDLE
    app_.state.scan_error = None
    app_.state.last_scan_completed = None  # no cooldown on cold start
    app_.state.current_filters = dict(DEFAULT_FILTERS)

    LOGGER.info("Loaded latest scan from %s with %d stocks.", latest_ts, len(latest_data))
    LOGGER.info("Server started.")

    yield  # Server is running

    LOGGER.info("Server stopped.")


def get_routes() -> List[APIRoute]:
    """Return all API routes."""
    return [
        APIRoute(
            path="/health",
            endpoint=lambda: {"status": "ok"},
            methods=["GET"],
            include_in_schema=False,
        ),
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
    ]


app = FastAPI(title="Trading Bot Dashboard", lifespan=lifespan)
app.__name__ = "app"
api_routes = get_routes()
if all((USERNAME, PASSWORD)):
    uiauth.protect(
        app=app,
        username=USERNAME,
        password=PASSWORD,
        routes=api_routes,
    )
else:
    warnings.warn(
        "USERNAME and PASSWORD are not set. API endpoints are unprotected.",
        UserWarning,
    )
    app.routes.extend(get_routes())

# TODO:
#   Include favicon.ico
#   Support scheduled runs
#   Add CORS protection
#   Add notifications through Telegram and Gmail
#   Extend Telegram support to score an individual ticker
#   Consider replacing Twelve Data with an open-source alternative
#   Include multiple candlestick trackers
