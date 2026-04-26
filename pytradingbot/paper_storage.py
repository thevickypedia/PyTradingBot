"""Paper trading persistence — two tables appended to the existing scan_history.db.

Schema
------
paper_sessions  — one row per paper trading session
paper_trades    — individual simulated buy/sell orders
"""

import sqlite3
from typing import Any, Dict, List, Optional

from pytradingbot.constants import LOGGER, config


def _ensure_schema() -> None:
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_sessions (
                id            TEXT PRIMARY KEY,
                risk_level    INTEGER NOT NULL,
                capital       REAL    NOT NULL,
                status        TEXT    NOT NULL,
                started_at    TEXT    NOT NULL,
                ended_at      TEXT,
                duration_days INTEGER NOT NULL,
                final_pnl     REAL,
                final_capital REAL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL,
                ticker      TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                price       REAL    NOT NULL,
                shares      REAL    NOT NULL,
                value       REAL    NOT NULL,
                scan_score  INTEGER,
                reason      TEXT,
                pnl         REAL,
                timestamp   TEXT    NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES paper_sessions(id)
            )
            """
        )
        conn.commit()
        conn.close()
        LOGGER.debug("Paper trading schema initialized.")
    except Exception as error:
        LOGGER.error("Failed to initialize paper trading schema: %s", error)
        raise


def save_session(session: Dict[str, Any]) -> None:
    """Save paper trading session data.

    Args:
        session: Session data.
    """
    _ensure_schema()
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO paper_sessions "
            "(id, risk_level, capital, status, started_at, ended_at, duration_days, final_pnl, final_capital) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session["id"],
                session["risk_level"],
                session["capital"],
                session["status"],
                session["started_at"],
                session.get("ended_at"),
                session["duration_days"],
                session.get("final_pnl"),
                session.get("final_capital"),
            ),
        )
        conn.commit()
        conn.close()
        LOGGER.debug("Saved paper session %s (status=%s).", session["id"], session["status"])
    except Exception as error:
        LOGGER.error("Failed to save paper session: %s", error)
        raise


def update_session_status(session_id: str, status: str, ended_at: str, final_pnl: float, final_capital: float) -> None:
    """Update paper trading session status.

    Args:
        session_id: Session id.
        status: Session status.
        ended_at: Session end time.
        final_pnl: Final pnl value.
        final_capital: Final capital value.
    """
    _ensure_schema()
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE paper_sessions SET status=?, ended_at=?, final_pnl=?, final_capital=? WHERE id=?",
            (status, ended_at, round(final_pnl, 2), round(final_capital, 2), session_id),
        )
        conn.commit()
        conn.close()
    except Exception as error:
        LOGGER.error("Failed to update paper session %s: %s", session_id, error)
        raise


def get_active_session() -> Optional[Dict[str, Any]]:
    """Get active paper trading session status.

    Returns:
        Dict[str, Any]:
        Dictionary with session status.
    """
    _ensure_schema()
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT id, risk_level, capital, status, started_at, ended_at, duration_days, final_pnl, final_capital "
            "FROM paper_sessions WHERE status = 'running' ORDER BY created_at DESC LIMIT 1"
        )
        row = c.fetchone()
        conn.close()
        if row is None:
            return None
        keys = [
            "id",
            "risk_level",
            "capital",
            "status",
            "started_at",
            "ended_at",
            "duration_days",
            "final_pnl",
            "final_capital",
        ]
        return dict(zip(keys, row))
    except Exception as error:
        LOGGER.error("Failed to get active paper session: %s", error)
        return None


def save_trade(trade: Dict[str, Any]) -> None:
    """Save paper trading session.

    Args:
        trade: Trade information.
    """
    _ensure_schema()
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO paper_trades "
            "(session_id, ticker, action, price, shares, value, scan_score, reason, pnl, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trade["session_id"],
                trade["ticker"],
                trade["action"],
                trade["price"],
                trade["shares"],
                trade["value"],
                trade.get("scan_score"),
                trade.get("reason"),
                trade.get("pnl"),
                trade["timestamp"],
            ),
        )
        conn.commit()
        conn.close()
    except Exception as error:
        LOGGER.error("Failed to save paper trade: %s", error)
        raise


def get_session_trades(session_id: str) -> List[Dict[str, Any]]:
    """Get paper trading session trades.

    Args:
        session_id: Session id.

    Returns:
        List[Dict[str, Any]]:
        Return list of paper trading session trades.
    """
    _ensure_schema()
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT id, session_id, ticker, action, price, shares, value, scan_score, reason, pnl, timestamp "
            "FROM paper_trades WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = c.fetchall()
        conn.close()
        keys = [
            "id",
            "session_id",
            "ticker",
            "action",
            "price",
            "shares",
            "value",
            "scan_score",
            "reason",
            "pnl",
            "timestamp",
        ]
        return [dict(zip(keys, r)) for r in rows]
    except Exception as error:
        LOGGER.error("Failed to get trades for session %s: %s", session_id, error)
        return []


def list_sessions() -> List[Dict[str, Any]]:
    """List paper trading sessions.

    Returns:
        List[Dict[str, Any]]:
        Return list of paper trading sessions.
    """
    _ensure_schema()
    try:
        conn = sqlite3.connect(config.DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT id, risk_level, capital, status, started_at, ended_at, duration_days, final_pnl, final_capital "
            "FROM paper_sessions ORDER BY created_at DESC"
        )
        rows = c.fetchall()
        conn.close()
        keys = [
            "id",
            "risk_level",
            "capital",
            "status",
            "started_at",
            "ended_at",
            "duration_days",
            "final_pnl",
            "final_capital",
        ]
        return [dict(zip(keys, r)) for r in rows]
    except Exception as error:
        LOGGER.error("Failed to list paper sessions: %s", error)
        return []
