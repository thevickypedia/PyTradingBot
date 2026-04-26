"""FastAPI route handlers for the paper trading feature."""

from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pytradingbot import paper_storage
from pytradingbot.constants import LOGGER


class StartPaperRequest(BaseModel):
    """Request for starting a paper trading session.

    >>> StartPaperRequest

    """

    risk_level: int = Field(..., ge=1, le=3, description="1=Conservative 2=Moderate 3=Aggressive")
    duration_days: int = Field(..., ge=1, le=7, description="Session duration in days (1–7)")
    starting_capital: float = Field(default=10_000.0, gt=0, description="Starting paper capital in USD")


def _hold_time_str(entry_time_iso: str) -> str:
    """Convert entry time to hold time."""
    try:
        entry_dt = datetime.fromisoformat(entry_time_iso)
        delta = datetime.now(timezone.utc) - entry_dt
        total = int(delta.total_seconds())
        h, rem = divmod(total, 3600)
        m = rem // 60
        return f"{h}h {m}m"
    except Exception as error:
        LOGGER.warning("Paper trading session rejected: %s", error)
        return "—"


async def paper_status(request: Request) -> JSONResponse:
    """Paper trading session status."""
    engine = getattr(request.app.state, "paper_engine", None)
    schedule_cfg = getattr(request.app.state, "schedule_config", {})
    schedule_enabled = bool(schedule_cfg.get("enabled", False))

    base = {
        "is_running": False,
        "schedule_enabled": schedule_enabled,
        "risk_level": None,
        "duration_days": None,
        "started_at": None,
        "starting_capital": None,
        "available_capital": 0,
        "current_value": 0,
        "unrealised_pnl": 0,
        "open_positions": [],
    }

    if engine is None:
        return JSONResponse(base)

    raw = engine.get_status()
    session = raw.get("session") or {}
    positions = raw.get("positions") or {}

    open_positions = [
        {
            "ticker": ticker,
            "entry_price": pos["entry_price"],
            "shares": pos["shares"],
            "entry_value": pos["entry_value"],
            "hold_time": _hold_time_str(pos.get("entry_time", "")),
            "status": "open",
        }
        for ticker, pos in positions.items()
    ]

    return JSONResponse(
        {
            "is_running": raw.get("is_running", False),
            "schedule_enabled": schedule_enabled,
            "risk_level": session.get("risk_level"),
            "duration_days": session.get("duration_days"),
            "started_at": session.get("started_at"),
            "starting_capital": session.get("capital"),
            "available_capital": raw.get("available_capital", 0),
            "current_value": raw.get("current_value", 0),
            "unrealised_pnl": raw.get("unrealised_pnl", 0),
            "open_positions": open_positions,
        }
    )


async def paper_start(request: Request, body: StartPaperRequest) -> JSONResponse:
    """Start a new paper trading session."""
    engine = getattr(request.app.state, "paper_engine", None)
    if engine is None:
        return JSONResponse({"status": "error", "error": "Paper trading engine not initialised."}, status_code=500)
    if engine.is_running:
        return JSONResponse(
            {"status": "already_running", "error": "A session is already in progress."}, status_code=409
        )

    schedule_cfg = getattr(request.app.state, "schedule_config", {})
    schedule_enabled = bool(schedule_cfg.get("enabled", False))

    try:
        session = await engine.start_session(
            risk_level=body.risk_level,
            duration_days=body.duration_days,
            capital=body.starting_capital,
            schedule_enabled=schedule_enabled,
        )
        LOGGER.info("Paper trading session started via API.")
        return JSONResponse({"status": "started", "session": session}, status_code=202)
    except ValueError as exc:
        LOGGER.warning("Paper trading start rejected: %s", exc)
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=400)


async def paper_stop(request: Request) -> JSONResponse:
    """Stop a paper trading session."""
    engine = getattr(request.app.state, "paper_engine", None)
    if engine is None or not engine.is_running:
        return JSONResponse({"status": "not_running", "error": "No active paper trading session."}, status_code=400)
    await engine.stop_session()
    LOGGER.info("Paper trading session stopped via API.")
    return JSONResponse({"status": "stopped"})


async def paper_history(request: Request) -> JSONResponse:
    """Get historical paper trading session history."""
    sessions = paper_storage.list_sessions()
    result = []
    for s in sessions:
        trades = paper_storage.get_session_trades(s["id"])
        result.append(
            {
                "session_id": s["id"],
                "risk_level": s["risk_level"],
                "duration_days": s["duration_days"],
                "starting_capital": s["capital"],
                "final_pnl": s.get("final_pnl"),
                "final_capital": s.get("final_capital"),
                "status": s["status"],
                "started_at": s["started_at"],
                "ended_at": s.get("ended_at"),
                "trades": [
                    {
                        "ticker": t["ticker"],
                        "action": t["action"],
                        "price": t["price"],
                        "shares": t["shares"],
                        "value": t["value"],
                        "pnl": t.get("pnl"),
                        "reason": t.get("reason"),
                        "time": t["timestamp"],
                    }
                    for t in trades
                ],
            }
        )
    return JSONResponse({"sessions": result})
