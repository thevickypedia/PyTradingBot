import json
import logging
import os
import pathlib
import socket
from datetime import datetime, tzinfo
from enum import StrEnum
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from pydantic import (
    DirectoryPath,
    Field,
    NewPath,
    PositiveInt,
)
from pydantic_settings import BaseSettings


class ScanStatus(StrEnum):
    """Lifecycle states for a stock scan.

    >>> ScanStatus

    """

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


# Environment variables with defaults
class LogLevel(StrEnum):
    """Log levels for pytradingbot.

    >>> LogLevel

    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EnvConfig(BaseSettings):
    """Environment variables for pytradingbot.

    >>> EnvConfig

    """

    # API Starter pack
    host: str = socket.gethostbyname("localhost")
    port: PositiveInt = 8080
    tz: ZoneInfo | tzinfo = datetime.now().astimezone().tzinfo or ZoneInfo("UTC")
    log_level: LogLevel = LogLevel(LogLevel.INFO)

    data_dir: NewPath | DirectoryPath = pathlib.Path("data")
    logs_dir: NewPath | DirectoryPath = pathlib.Path("logs")

    # Users may not trigger a new scan within this window after the last one completed.
    scan_cooldown_seconds: int = Field(60, ge=30, le=3600, description="Cooldown period in seconds between scans")

    # Credentials
    username: str
    password: str
    timeout: int = 3600

    telegram_bot_token: str | None = None
    telegram_chat_ids: List[int] | None = None

    class Config:
        """Environment variables configuration."""

        env_file = os.getenv("ENV_FILE") or os.getenv("env_file") or ".env"
        extra = "ignore"


# noinspection argument-list
env = EnvConfig()

env.data_dir.mkdir(parents=True, exist_ok=True)
env.logs_dir.mkdir(parents=True, exist_ok=True)

LOGGER = logging.getLogger("pytradingbot")
LOGGER.setLevel(env.log_level)
handler = logging.FileHandler(
    filename=str(env.logs_dir / f"pytradingbot_{datetime.now(env.tz).strftime('%Y-%m-%d')}.log"),
    mode="a",
)
handler.setLevel(env.log_level)
handler.setFormatter(
    fmt=logging.Formatter(
        datefmt="%b-%d-%Y %I:%M:%S %p",
        fmt="%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
    )
)
handler.formatter.converter = lambda ts: datetime.fromtimestamp(ts, env.tz).timetuple()
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
    DB_PATH: str = str(env.data_dir / "scan_history.db")

    TICKERS_PATH: str = str(env.data_dir / "tickers.json")

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
