"""Lightweight scan-history persistence using SQLite3.

SQLite3 is platform-independent and works identically across macOS, Linux,
Docker, and all other systems. Replaces shelve which had incompatible dbm
backends causing cross-platform issues.

Produces a ``scan_history.db`` file inside ``<project_root>/data/``.

Schema
------
scans       table  — stores individual scan snapshots with metadata
schedule    table  — stores scheduler configuration
"""

import copy
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from pytradingbot.constants import LOGGER, config


def _ensure_schema() -> None:
    """Create database schema if it doesn't exist."""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()

        # Create scans table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT UNIQUE NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create schedule table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                config TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        conn.commit()
        conn.close()
        LOGGER.debug("Database schema initialized.")
    except Exception as error:
        LOGGER.error("Failed to initialize database schema: %s", error)
        raise


def save_scan(timestamp: str, data: List[Dict[str, Any]]) -> None:
    """Persist *data* under *timestamp*.

    Args:
        timestamp: Timestamp to save scan data for.
        data: List of scan data for *timestamp*, or ``[]`` if not found.
    """
    _ensure_schema()
    LOGGER.debug("Saving scan snapshot for %s with %d records.", timestamp, len(data))
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()

        # Convert data to JSON for storage
        json_data = json.dumps(data)

        # Insert or replace the scan data
        cursor.execute(
            "INSERT OR REPLACE INTO scans (timestamp, data) VALUES (?, ?)",
            (timestamp, json_data),
        )

        conn.commit()
        conn.close()
        LOGGER.info("Saved scan snapshot for %s.", timestamp)
    except Exception as error:
        LOGGER.error("Failed to save scan for %s: %s", timestamp, error)
        raise


def list_versions() -> List[Dict[str, int]]:
    """Return all stored versions **newest-first** as ``[{timestamp, count}]``.

    Safe to call even if the DB does not exist yet (returns ``[]``).

    Returns:
        List[Dict[str, int]]:
        List of versions with timestamp and stock count, newest first.
    """
    try:
        _ensure_schema()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()

        # Get all scans ordered by timestamp descending (newest first)
        cursor.execute("SELECT timestamp, data FROM scans ORDER BY timestamp DESC")
        results = cursor.fetchall()
        conn.close()

        versions = []
        for timestamp, json_data in results:
            try:
                data = json.loads(json_data)
                versions.append({"timestamp": timestamp, "count": len(data)})
            except json.JSONDecodeError:
                LOGGER.warning("Failed to decode JSON for timestamp %s", timestamp)

        return versions
    except Exception as error:
        LOGGER.error("Failed to list versions: %s", error)
        return []


def load_version(timestamp: str) -> Optional[List[Dict[str, Any]]]:
    """Return scan data for *timestamp*, or ``None`` if not found.

    Args:
        timestamp: Timestamp to load scan data for.

    Returns:
        Optional[List[Dict[str, Any]]]:
        List of scan data for *timestamp*, or ``None`` if not found.
    """
    try:
        _ensure_schema()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT data FROM scans WHERE timestamp = ?", (timestamp,))
        result = cursor.fetchone()
        conn.close()

        if result is None:
            LOGGER.warning("Requested scan version %s was not found in storage.", timestamp)
            return None

        data = json.loads(result[0])
        LOGGER.debug("Loaded scan version %s with %d records.", timestamp, len(data))
        return data
    except Exception as error:
        LOGGER.error("Failed to load version %s: %s", timestamp, error)
        return None


def latest_version() -> Tuple[Optional[str], list]:
    """Return ``(timestamp, data)`` for the newest snapshot, or ``(None, [])``.

    Used at server startup to pre-populate ``app.state`` from the last saved run.

    Returns:
        Tuple[Optional[str], list]
        Result ``(timestamp, data)`` or ``(None, [])`` if not found.
    """
    try:
        _ensure_schema()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()

        # Get the most recent scan by timestamp
        cursor.execute("SELECT timestamp, data FROM scans ORDER BY timestamp DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()

        if result is None:
            return None, []

        timestamp, json_data = result
        data = json.loads(json_data)
        return timestamp, data
    except Exception as error:
        LOGGER.warning("Latest version not found: %s", error)
        return None, []


def load_schedule() -> Dict[str, Any]:
    """Return persisted scheduler config, or module defaults when unset/invalid.

    Returns:
        Dict[str, Any]:
        Persisted scheduler config, or module defaults when unset/invalid.
    """
    try:
        _ensure_schema()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT config FROM schedule WHERE id = 1")
        result = cursor.fetchone()
        conn.close()

        if result is None:
            LOGGER.warning("No persisted schedule configuration found; using defaults.")
            return copy.deepcopy(config.DEFAULT_SCHEDULE)

        stored = json.loads(result[0])
        if isinstance(stored, dict):
            LOGGER.info("Loaded persisted schedule configuration from storage.")
            return stored

        LOGGER.warning("Invalid schedule configuration format; using defaults.")
    except Exception as error:
        LOGGER.error("Failed to load schedule config: %s", error)

    return copy.deepcopy(config.DEFAULT_SCHEDULE)


def save_schedule(schedule: Dict[str, Any]) -> None:
    """Persist scheduler config.

    Args:
        schedule: Scheduler config.
    """
    _ensure_schema()
    LOGGER.debug("Saving schedule configuration. enabled=%s", schedule.get("enabled", True))
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()

        # Convert schedule to JSON
        json_config = json.dumps(schedule)

        # Insert or replace the schedule (only one row with id=1)
        cursor.execute(
            "INSERT OR REPLACE INTO schedule (id, config) VALUES (1, ?)",
            (json_config,),
        )

        conn.commit()
        conn.close()
        LOGGER.info("Saved schedule configuration to storage.")
    except Exception as error:
        LOGGER.error("Failed to save schedule config: %s", error)
        raise
