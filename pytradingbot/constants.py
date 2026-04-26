import json
import logging
import os
import pathlib
from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List
from zoneinfo import ZoneInfo


class ScanStatus(StrEnum):
    """Lifecycle states for a stock scan.

    >>> ScanStatus

    """

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


def getenv(*args, default: str = None) -> str | None:
    """Get an environment variable.

    Args:
        *args: One or more possible environment variable names to check (case-insensitive).
        default: Default value to return if environment variable is not set.

    Returns:
        str:
        Environment variable or default value if environment variable is not set.
    """
    keys = [key.upper() for key in args] + [k.lower() for k in args]
    for key in keys:
        if val := os.getenv(key):
            return val
    return default


# Environment variables with defaults
_approved_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Env:
    """Environment variables for pytradingbot.

    >>> Env

    """

    # API Starter pack
    HOST: str = getenv("host", default="0.0.0.0")
    PORT: int = int(getenv("port", default="8080"))
    LOG_LEVEL: str = getenv("log_level", default="INFO").upper()
    assert (
        LOG_LEVEL in _approved_log_levels
    ), f"Invalid LOG_LEVEL value, must be one of {', '.join(_approved_log_levels)}"
    LOGS_DIR: pathlib.Path = pathlib.Path(getenv("logs_dir", default="logs"))
    DB_DIR: pathlib.Path = pathlib.Path(getenv("db_dir", "data_dir", default="data"))

    # Users may not trigger a new scan within this window after the last one completed.
    SCAN_COOLDOWN_SECONDS: int = int(getenv("scan_cooldown_seconds", default="60"))

    # Credentials
    USERNAME: str = getenv("username", "user")
    PASSWORD: str = getenv("password", "pass")

    TELEGRAM_BOT_TOKEN: str = getenv("telegram_bot_token", "telegram_token", "bot_token")
    TELEGRAM_CHAT_IDS: List[int] = [
        int(chat_id.strip())
        for chat_id in (
            getenv("telegram_chat_ids", "chat_ids", "telegram_chat_id", "chat_id", "bot_chat_ids", "bot_chat_id") or ""
        ).split(",")
        if chat_id.strip().isdigit()
    ]


env = Env()

env.DB_DIR.mkdir(parents=True, exist_ok=True)
env.LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGER = logging.getLogger("pytradingbot")
LOGGER.setLevel(getattr(logging, env.LOG_LEVEL, logging.DEBUG))
handler = logging.FileHandler(
    filename=str(env.LOGS_DIR / f"pytradingbot_{datetime.now().strftime('%Y-%m-%d')}.log"),
    mode="a",
)
handler.setLevel(getattr(logging, env.LOG_LEVEL, logging.DEBUG))
handler.setFormatter(
    fmt=logging.Formatter(
        datefmt="%b-%d-%Y %I:%M:%S %p",
        fmt="%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
    )
)
if not LOGGER.handlers:
    LOGGER.addHandler(hdlr=handler)
LOGGER.propagate = False


class Config:
    """Configuration class for pytradingbot.

    >>> Config

    """

    DEFAULT_FILTERS: Dict[str, str] = {
        "Exchange": "NASDAQ",
        "Country": "USA",
        "Average Volume": "Over 500K",
        "Price": "Under $50",
        "Relative Volume": "Over 2",
        "Gap": "Up",
        "Change": "Up 5%",
        "RSI (14)": "Not Overbought (<60)",
    }

    TEMPLATES_DIR: pathlib.Path = pathlib.Path(__file__).parent / "templates"
    FILTER_OPTIONS: Dict[str, List[str]] = json.loads((TEMPLATES_DIR / "filters.json").read_text())

    # Datastore — SQLite3 for cross-platform compatibility
    DB_PATH: str = str(env.DB_DIR / "scan_history.db")

    TICKERS_PATH: str = str(env.DB_DIR / "tickers.json")

    # Scheduler defaults (all times are interpreted in America/New_York)
    MARKET_TIMEZONE: ZoneInfo = ZoneInfo("America/New_York")
    DEFAULT_SCHEDULE: Dict[str, Any] = {
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


config = Config()
