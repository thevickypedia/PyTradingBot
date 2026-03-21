"""Lightweight scan-history persistence using Python's stdlib ``shelve``.

No external dependencies — shelve is backed by ``dbm`` which ships with every
CPython distribution.  On macOS / Linux this typically uses ``dbm.ndbm`` and
produces a single ``scan_history.db`` file inside ``<project_root>/data/``.

Schema
------
``__index__``   list[str]   — insertion-ordered list of all timestamp keys
``<timestamp>`` list[dict]  — the raw scan records for that snapshot
"""

import copy
import shelve
from typing import Dict, List, Optional

from pytradingbot.constants import (
    DB_DIR,
    DB_INDEX_KEY,
    DB_PATH,
    DB_SCHEDULE_KEY,
    DEFAULT_SCHEDULE,
    LOGGER,
)


def save_scan(timestamp: str, data: list) -> None:
    """Persist *data* under *timestamp*.

    An ``__index__`` list is maintained so that insertion order is preserved
    regardless of the underlying dbm backend's key ordering.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with shelve.open(DB_PATH) as db:
        db[timestamp] = data
        index: list[str] = list(db.get(DB_INDEX_KEY, []))
        if timestamp not in index:
            index.append(timestamp)
        db[DB_INDEX_KEY] = index


def list_versions() -> List[Dict[str, int]]:
    """Return all stored versions **newest-first** as ``[{timestamp, count}]``.

    Safe to call even if the DB does not exist yet (returns ``[]``).
    """
    try:
        with shelve.open(DB_PATH) as db:
            index: list[str] = list(db.get(DB_INDEX_KEY, []))
            return [{"timestamp": ts, "count": len(db.get(ts, []))} for ts in reversed(index)]
    except Exception as error:
        LOGGER.error("Failed to list versions: %s", error)
        return []


def load_version(timestamp: str) -> Optional[list]:
    """Return scan data for *timestamp*, or ``None`` if not found."""
    try:
        with shelve.open(DB_PATH) as db:
            return db.get(timestamp)
    except Exception as error:
        LOGGER.error("Failed to load version %s: %s", timestamp, error)
        return None


def latest_version() -> tuple[Optional[str], list]:
    """Return ``(timestamp, data)`` for the newest snapshot, or ``(None, [])``.

    Used at server startup to pre-populate ``app.state`` from the last saved run.
    """
    try:
        with shelve.open(DB_PATH) as db:
            index: list[str] = list(db.get(DB_INDEX_KEY, []))
            if not index:
                return None, []
            key = index[-1]  # last appended = most recent
            return key, list(db.get(key, []))
    except Exception as warning:
        LOGGER.warning("Latest version not found: %s", warning)
        return None, []


def load_schedule() -> dict:
    """Return persisted scheduler config, or module defaults when unset/invalid."""
    try:
        with shelve.open(DB_PATH) as db:
            stored = db.get(DB_SCHEDULE_KEY)
            if isinstance(stored, dict):
                return stored
    except Exception as error:
        LOGGER.error("Failed to load schedule config: %s", error)
    return copy.deepcopy(DEFAULT_SCHEDULE)


def save_schedule(schedule: dict) -> None:
    """Persist scheduler config."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with shelve.open(DB_PATH) as db:
        db[DB_SCHEDULE_KEY] = schedule
