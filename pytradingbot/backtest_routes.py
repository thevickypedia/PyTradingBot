"""FastAPI route handlers for the backtest feature."""

import asyncio
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pytradingbot.constants import LOGGER


class BacktestRequest(BaseModel):
    """Request for running a backtest.

    >>> BacktestRequest

    """

    tickers: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


def _safe(v: Any) -> Any:
    """Convert a value to a JSON-safe type."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, float):
        return round(v, 4)
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return None
    if hasattr(v, "item"):
        return v.item()
    return v


def _run_backtest_sync(tickers: List[str], start_date: str, end_date: str) -> Dict[str, Any]:
    """Run backtest and return a serialisable result dict."""
    from pytradingbot.backtest import FORWARD_DAYS, run_backtest
    from pytradingbot.main import normalize_change

    df = run_backtest(tickers, start_date, end_date)
    if df.empty:
        return {
            "error": "No results found. Check tickers and date range.",
            "stats": {},
            "correlation": {},
            "bucket_perf": [],
            "signals": [],
        }

    total = len(df)
    wins, losses, still_open = 0, 0, 0
    for _, row in df.iterrows():
        entry = row.get("Entry") or row.get("Close", 0)
        stop = row.get("Stop_Loss")
        target = row.get("Take_Profit")
        fwd_5d = row.get("FWD_5D", 0)
        if stop is None or target is None or entry == 0:
            still_open += 1
            continue
        simulated_exit = float(entry) * (1 + float(fwd_5d) / 100)
        if simulated_exit >= float(target):
            wins += 1
        elif simulated_exit <= float(stop):
            losses += 1
        else:
            still_open += 1

    total_traded = wins + losses
    win_rate = (wins / total_traded * 100) if total_traded > 0 else 0.0
    wl_ratio = round(wins / losses, 2) if losses > 0 else None

    correlation = {}
    for d in FORWARD_DAYS:
        col = f"FWD_{d}D"
        if col in df.columns:
            corr = df["Score"].corr(df[col])
            correlation[f"{d}D"] = round(float(corr), 3) if not pd.isna(corr) else None

    bucket_perf = []
    try:
        df["ScoreBucket"] = pd.qcut(df["Score"], 5, duplicates="drop")
        for k, v in df.groupby("ScoreBucket", observed=True)["FWD_5D"].mean().items():
            label = f"{k.left:.1f} to {k.right:.1f}" if hasattr(k, "left") else str(k)
            bucket_perf.append({"bucket": label, "avg_5d_return": round(float(v), 3)})
    except Exception as error:
        LOGGER.warning(error)

    wanted_cols = [
        "Date",
        "Ticker",
        "Score",
        "TD_Signal",
        "TD_Trend",
        "YF_Signal",
        "EMA_Cross",
        "RSI",
        "Change",
        "ATR",
        "Volume",
        "Entry",
        "Stop_Loss",
        "Take_Profit",
        "Risk_Reward",
        "FWD_1D",
        "FWD_3D",
        "FWD_5D",
    ]
    available = [c for c in wanted_cols if c in df.columns]
    signals_list = []
    for _, row in df.sort_values("Score", ascending=False)[available].iterrows():
        d = {c: _safe(row[c]) for c in available}
        fwd5 = d.get("FWD_5D")
        d["Result"] = "WIN" if (fwd5 is not None and fwd5 > 0) else "LOSS"
        signals_list.append(d)

    mean_change_raw = df["Change"].apply(normalize_change).mean()

    return {
        "error": None,
        "stats": {
            "total_signals": total,
            "score_min": round(float(df["Score"].min()), 1),
            "score_max": round(float(df["Score"].max()), 1),
            "mean_score": round(float(df["Score"].mean()), 1),
            "mean_rsi": round(float(df["RSI"].mean()), 1),
            "mean_change": round(float(mean_change_raw), 2),
            "wins": wins,
            "losses": losses,
            "open": still_open,
            "win_rate": round(win_rate, 1),
            "wl_ratio": wl_ratio,
        },
        "correlation": correlation,
        "bucket_perf": bucket_perf,
        "signals": signals_list,
    }


async def backtest_run(request: Request, body: BacktestRequest) -> JSONResponse:
    """Start a backtest run in the background."""
    if getattr(request.app.state, "backtest_running", False):
        return JSONResponse({"status": "already_running"}, status_code=409)

    tickers = [t.strip().upper() for t in body.tickers.split() if t.strip()]
    if not tickers:
        return JSONResponse({"status": "error", "error": "No tickers provided."}, status_code=400)

    from pytradingbot.backtest import END_DATE, START_DATE

    start_date = body.start_date or START_DATE
    end_date = body.end_date or END_DATE

    request.app.state.backtest_running = True
    request.app.state.backtest_result = None
    request.app.state.backtest_error = None
    request.app.state.backtest_tickers = tickers
    request.app.state.backtest_finished_at = None

    async def _task() -> None:
        try:
            result = await asyncio.to_thread(_run_backtest_sync, tickers, start_date, end_date)
            request.app.state.backtest_result = result
            if result.get("error"):
                request.app.state.backtest_error = result["error"]
        except Exception as exc:
            LOGGER.error("Backtest failed: %s", exc)
            request.app.state.backtest_error = str(exc)
            request.app.state.backtest_result = None
        finally:
            request.app.state.backtest_running = False
            request.app.state.backtest_finished_at = datetime.now(timezone.utc).isoformat()

    asyncio.create_task(_task())
    LOGGER.info("Backtest started for tickers: %s", tickers)
    return JSONResponse({"status": "started", "tickers": tickers}, status_code=202)


async def backtest_status(request: Request) -> JSONResponse:
    """Get current backtest run status and result."""
    return JSONResponse(
        {
            "running": getattr(request.app.state, "backtest_running", False),
            "result": getattr(request.app.state, "backtest_result", None),
            "error": getattr(request.app.state, "backtest_error", None),
            "tickers": getattr(request.app.state, "backtest_tickers", []),
            "finished_at": getattr(request.app.state, "backtest_finished_at", None),
        }
    )
