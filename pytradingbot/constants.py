import logging
import os
import pathlib
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo


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


LOGS_DIR = pathlib.Path("logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Environment variables with defaults
_approved_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
LOG_LEVEL = (os.getenv("LOG_LEVEL") or os.getenv("log_level") or "DEBUG").upper()
assert LOG_LEVEL in _approved_log_levels, f"Invalid LOG_LEVEL value, must be one of {', '.join(_approved_log_levels)}"

# API Starter pack
HOST = os.getenv("HOST") or os.getenv("host") or "0.0.0.0"
PORT = int(os.getenv("PORT") or os.getenv("port") or "8080")

# Users may not trigger a new scan within this window after the last one completed.
SCAN_COOLDOWN_SECONDS: int = int(os.getenv("SCAN_COOLDOWN_SECONDS") or os.getenv("scan_cooldown_seconds") or 60)

# Credentials
USERNAME = os.getenv("USERNAME") or os.getenv("username") or os.getenv("USER") or os.getenv("user")
PASSWORD = os.getenv("PASSWORD") or os.getenv("password") or os.getenv("PASS") or os.getenv("pass")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("telegram_bot_token")
TELEGRAM_CHAT_IDS = [
    int(chat_id.strip())
    for chat_id in (os.getenv("TELEGRAM_CHAT_IDS") or os.getenv("telegram_chat_ids") or "").split(",")
    if chat_id.strip().isdigit()
]

LOGGER = logging.getLogger("pytradingbot")
LOGGER.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
handler = logging.FileHandler(
    filename=str(LOGS_DIR / f"pytradingbot_{datetime.now().strftime('%Y-%m-%d')}.log"),
    mode="a",
)
handler.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
handler.setFormatter(
    fmt=logging.Formatter(
        datefmt="%b-%d-%Y %I:%M:%S %p",
        fmt="%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
    )
)
if not LOGGER.handlers:
    LOGGER.addHandler(hdlr=handler)
LOGGER.propagate = False

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

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"

# Datastore
DB_DIR = pathlib.Path("data")
DB_PATH = str(DB_DIR / "scan_history")
DB_INDEX_KEY = "__index__"
DB_SCHEDULE_KEY = "__schedule__"

# Scheduler defaults (all times are interpreted in America/New_York)
MARKET_TIMEZONE = ZoneInfo("America/New_York")
DEFAULT_SCHEDULE = {
    "enabled": True,
    "windows": [
        {
            "id": "pre_market",
            "label": "Pre-Market",
            "start": "04:00",
            "end": "09:30",
            "interval_minutes": 15,
            "enabled": True,
        },
        {
            "id": "market_open",
            "label": "Market Open",
            "start": "09:30",
            "end": "10:30",
            "interval_minutes": 5,
            "enabled": True,
        },
        {
            "id": "mid_day",
            "label": "Mid Day",
            "start": "10:30",
            "end": "14:00",
            "interval_minutes": 30,
            "enabled": True,
        },
        {
            "id": "power_hour",
            "label": "Power Hour",
            "start": "14:00",
            "end": "16:00",
            "interval_minutes": 5,
            "enabled": True,
        },
    ],
    "after_hours": {"enabled": True, "run_time": "16:15", "close": "20:00"},
}
