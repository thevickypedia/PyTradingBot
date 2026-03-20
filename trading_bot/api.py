from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates

from trading_bot.main import DEFAULT_FILTERS
from trading_bot.routes import dashboard, get_logs, scan_status, start_scan

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app_: FastAPI):
    """Initialize app state. The scan does NOT run automatically on startup."""
    app_.routes.extend(get_routes())
    app_.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app_.state.scan_data = []
    app_.state.last_scanned = None
    app_.state.scan_status = "idle"  # idle | running | done | error
    app_.state.scan_error = None
    app_.state.current_filters = dict(DEFAULT_FILTERS)
    yield  # Server is running


def get_routes() -> List[APIRoute]:
    """Get all API routes."""
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
            path="/logs",
            endpoint=get_logs,
            methods=["GET"],
            include_in_schema=False,
            response_class=JSONResponse,
        ),
    ]


app = FastAPI(title="Trading Bot Dashboard", lifespan=lifespan)
app.__name__ = "app"
