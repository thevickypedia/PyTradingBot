import logging
import os
import pathlib
import socket
from datetime import datetime
from enum import StrEnum


class ScanStatus(StrEnum):
    """Lifecycle states for a stock scan.

    Inherits from ``str`` so values compare equal to plain string literals —
    Jinja2 ``{% if scan_status == 'done' %}`` and JS ``=== 'done'`` both work
    without any template changes.
    """

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


os.makedirs("logs", exist_ok=True)

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
handler = logging.FileHandler(
    filename=os.path.join("logs", f"trading_bot_{datetime.now().strftime('%Y-%m-%d')}.log"),
    mode="a",
)
handler.setFormatter(
    fmt=logging.Formatter(
        datefmt="%b-%d-%Y %I:%M:%S %p",
        fmt="%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
    )
)
LOGGER.addHandler(hdlr=handler)

DEFAULT_FILTERS = {
    "Exchange": "NASDAQ",
    "Country": "USA",
    "Average Volume": "Over 500K",
    "Price": "Under $50",
    "Relative Volume": "Over 2",
    "Gap": "Up",
    "Change": "Up 5%",
    "RSI (14)": "Not Overbought (<60)",
}

TWELVEDATA_API_KEY = (
    os.getenv("TWELVEDATA_API_KEY")
    or os.getenv("TWELVEDATA_APIKEY")
    or os.getenv("twelvedata_api_key")
    or os.getenv("twelvedata_apikey")
    or "demo"
)

# API Starter pack
HOST = os.getenv("HOST") or os.getenv("host") or socket.gethostbyname("localhost") or "0.0.0.0"
PORT = int(os.getenv("PORT") or os.getenv("port") or "8080")

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"

# Users may not trigger a new scan within this window after the last one completed.
SCAN_COOLDOWN_SECONDS: int = int(os.getenv("SCAN_COOLDOWN_SECONDS") or os.getenv("scan_cooldown_seconds") or 60)

# Datastore
DB_DIR = pathlib.Path(__file__).parent.parent / "data"
DB_PATH = str(DB_DIR / "scan_history")
