"""Lightweight scan-history persistence using Python's stdlib ``shelve``.

No external dependencies — shelve is backed by ``dbm`` which ships with every
CPython distribution.  On macOS / Linux this typically uses ``dbm.ndbm`` and
produces a single ``scan_history.db`` file inside ``<project_root>/data/``.

Schema
------
``__index__``   list[str]   — insertion-ordered list of all timestamp keys
``<timestamp>`` list[dict]  — the raw scan records for that snapshot
"""

import shelve
from typing import Dict, List, Optional

from trading_bot.constants import DB_DIR, DB_PATH, LOGGER


def save_scan(timestamp: str, data: list) -> None:
    """Persist *data* under *timestamp*.

    An ``__index__`` list is maintained so that insertion order is preserved
    regardless of the underlying dbm backend's key ordering.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with shelve.open(DB_PATH) as db:
        db[timestamp] = data
        index: list[str] = list(db.get("__index__", []))
        if timestamp not in index:
            index.append(timestamp)
        db["__index__"] = index


def list_versions() -> List[Dict[str, int]]:
    """Return all stored versions **newest-first** as ``[{timestamp, count}]``.

    Safe to call even if the DB does not exist yet (returns ``[]``).
    """
    try:
        with shelve.open(DB_PATH) as db:
            index: list[str] = list(db.get("__index__", []))
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
            index: list[str] = list(db.get("__index__", []))
            if not index:
                return None, []
            key = index[-1]  # last appended = most recent
            return key, list(db.get(key, []))
    except Exception as warning:
        LOGGER.warning("Latest version not found: %s", warning)
        return None, []
