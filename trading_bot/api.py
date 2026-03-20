from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from .main import DEFAULT_FILTERS

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize app state. The scan does NOT run automatically on startup."""
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.state.scan_data = []
    app.state.last_scanned = None
    app.state.scan_status = "idle"  # idle | running | done | error
    app.state.scan_error = None
    app.state.current_filters = dict(DEFAULT_FILTERS)
    yield  # Server is running


TradingBot = FastAPI(title="Trading Bot Dashboard", lifespan=lifespan)

# Import after `app` is defined to avoid circular imports
from .routes import router  # noqa: E402

TradingBot.include_router(router)
