"""Paper trading engine — isolated from the pytradingbot core scanner.

Reads signals from the pytradingbot SQLite database and performs simulated
trades based on a configurable risk level.  Runs as an asyncio background
task inside the FastAPI process.

Risk Levels
-----------
1  Conservative
   Entry:    TD_Signal = STRONG BUY · Score ≥ 70 · RSI 45–58 · EMA CROSS UP required
   Position: 5 % of available capital per trade
   Stop:     –5 % from entry   |  Target: +8 % from entry
   Max hold: 48 h   |  Disaster close: unrealised loss > 8 %

2  Moderate
   Entry:    TD_Signal in [STRONG BUY, BUY] · Score ≥ 60 · RSI 45–65
   Position: 10 % of available capital per trade
   Stop:     –8 % from entry   |  Target: +15 % from entry
   Max hold: 60 h   |  Disaster close: unrealised loss > 15 %

3  Aggressive
   Entry:    TD_Signal in [STRONG BUY, BUY, NEUTRAL] · Score ≥ 50 · RSI 45–70
   Position: 20 % of available capital per trade
   Stop:     –12 % from entry  |  Target: +25 % from entry
   Max hold: 72 h   |  Disaster close: unrealised loss > 25 %

Real-Time Checks Before Buying
--------------------------------
For each candidate the engine:
  1. Fetches the live price via yfinance.fast_info.
  2. Rejects if live price drifted > 3 % from the scan price (no chasing).
  3. Recalculates RSI from 30-day daily history and checks it is still in range.
  4. Runs a fresh 5-min candle signal and confirms TD_Signal is still BUY/STRONG BUY.
  5. Confirms sufficient cash for the position.
  6. Confirms the ticker is not already held.

72-Hour Rule
------------
Every position is force-closed at max_hold_hours regardless of P&L.
If the unrealised loss exceeds disaster_pct the position is closed immediately
(the "complete disaster" exception), well before the 72 h wall.
"""

import asyncio
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import yfinance as yf

from pytradingbot import paper_storage, storage
from pytradingbot.constants import LOGGER
from pytradingbot.main import get_candle_signal

# --------------------------------------------------------------------------- #
# Risk configuration
# --------------------------------------------------------------------------- #
RISK_CONFIG: Dict[int, Dict[str, Any]] = {
    1: {
        "name": "Conservative",
        "description": (
            "STRONG BUY only · Score ≥ 70 · RSI 45–58 · EMA cross required · "
            "5 % position · −5 % stop · +8 % target · 48 h max hold"
        ),
        "min_score": 70,
        "td_signals": ["STRONG BUY"],
        "rsi_min": 45,
        "rsi_max": 58,
        "require_ema_cross": True,
        "position_pct": 0.05,
        "stop_loss_pct": 0.05,
        "take_profit_pct": 0.08,
        "max_hold_hours": 48,
        "disaster_pct": 0.08,
    },
    2: {
        "name": "Moderate",
        "description": (
            "STRONG BUY or BUY · Score ≥ 60 · RSI 45–65 · " "10 % position · −8 % stop · +15 % target · 60 h max hold"
        ),
        "min_score": 60,
        "td_signals": ["STRONG BUY", "BUY"],
        "rsi_min": 45,
        "rsi_max": 65,
        "require_ema_cross": False,
        "position_pct": 0.10,
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.15,
        "max_hold_hours": 60,
        "disaster_pct": 0.15,
    },
    3: {
        "name": "Aggressive",
        "description": (
            "STRONG BUY, BUY or NEUTRAL · Score ≥ 50 · RSI 45–70 · "
            "20 % position · −12 % stop · +25 % target · 72 h max hold"
        ),
        "min_score": 50,
        "td_signals": ["STRONG BUY", "BUY", "NEUTRAL"],
        "rsi_min": 45,
        "rsi_max": 70,
        "require_ema_cross": False,
        "position_pct": 0.20,
        "stop_loss_pct": 0.12,
        "take_profit_pct": 0.25,
        "max_hold_hours": 72,
        "disaster_pct": 0.25,
    },
}

_TICK_SECONDS = 300  # evaluate every 5 minutes


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S UTC")


class PaperTradingEngine:
    """Async background engine that simulates trades from pytradingbot scan signals.

    Lifecycle: start_session() → asyncio.Task(_run_loop) → stop_session()
    """

    def __init__(self) -> None:
        self._stop_event: asyncio.Event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[Dict[str, Any]] = None
        self._cfg: Optional[Dict[str, Any]] = None
        # ticker → {entry_price, shares, entry_value, entry_time, scan_score}
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._available_capital: float = 0.0

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    @property
    def is_running(self) -> bool:
        """Return True if paper trading session is running."""
        return self._task is not None and not self._task.done()

    async def start_session(
        self,
        risk_level: int,
        duration_days: int,
        capital: float,
        schedule_enabled: bool,
    ) -> Dict[str, Any]:
        """Start paper trading session.

        Args:
            risk_level: Risk level.
            duration_days: Number of days to simulate.
            capital: Capital value.
            schedule_enabled: Boolean flag to indicate if schedule is enabled.

        Returns:
            Dict[str, Any]:
            Returns session details including session ID, risk level, capital, status, start time, and configuration.
        """
        if not schedule_enabled:
            raise ValueError("Paper trading requires the scanner schedule to be enabled.")
        if self.is_running:
            raise ValueError("A paper trading session is already in progress.")
        if risk_level not in RISK_CONFIG:
            raise ValueError(f"Invalid risk level {risk_level}. Must be 1, 2, or 3.")
        if not (1 <= duration_days <= 7):
            raise ValueError("Duration must be between 1 and 7 days.")
        if capital <= 0:
            raise ValueError("Capital must be a positive number.")

        session_id = str(uuid.uuid4())
        self._session = {
            "id": session_id,
            "risk_level": risk_level,
            "capital": capital,
            "status": "running",
            "started_at": _ts(),
            "ended_at": None,
            "duration_days": duration_days,
            "final_pnl": None,
            "final_capital": None,
        }
        self._cfg = RISK_CONFIG[risk_level]
        self._available_capital = capital
        self._positions = {}
        self._stop_event.clear()

        paper_storage.save_session(self._session)
        LOGGER.info(
            "Paper session %s started. risk=%d duration=%dd capital=%.2f",
            session_id,
            risk_level,
            duration_days,
            capital,
        )
        self._task = asyncio.create_task(self._run_loop())
        return self._session

    async def stop_session(self) -> None:
        """Stop paper trading session."""
        if not self.is_running:
            return
        self._stop_event.set()
        await self._close_all_positions("manual_stop")
        if self._task:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._finish_session("stopped")

    def get_status(self) -> Dict[str, Any]:
        """Return paper trading session status."""
        if self._session is None:
            self._session = paper_storage.get_active_session()
        initial = self._session["capital"] if self._session else 0
        unrealised = sum(p["entry_value"] for p in self._positions.values())
        current_value = self._available_capital + unrealised
        return {
            "session": self._session,
            "positions": self._positions,
            "available_capital": round(self._available_capital, 2),
            "current_value": round(current_value, 2),
            "unrealised_pnl": round(current_value - initial, 2),
            "is_running": self.is_running,
            "risk_config": RISK_CONFIG,
        }

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #

    async def _run_loop(self) -> None:
        assert self._session is not None
        end_time = _now() + timedelta(days=self._session["duration_days"])
        LOGGER.info("Paper loop running until %s.", end_time.isoformat())

        while not self._stop_event.is_set():
            try:
                if _now() >= end_time:
                    LOGGER.info("Paper session duration reached — closing all positions.")
                    await self._close_all_positions("session_end")
                    break
                await self._manage_positions()
                await self._evaluate_new_signals()
            except Exception as exc:
                LOGGER.error("Paper loop error: %s", exc)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=_TICK_SECONDS)
            except asyncio.TimeoutError:
                pass

        self._finish_session("completed")
        LOGGER.info("Paper loop ended for session %s.", self._session["id"])

    # ------------------------------------------------------------------ #
    # Position management
    # ------------------------------------------------------------------ #

    async def _manage_positions(self) -> None:
        if not self._positions or self._cfg is None:
            return
        cfg = self._cfg
        for ticker, pos in list(self._positions.items()):
            try:
                live_price = await asyncio.to_thread(self._get_live_price, ticker)
                if live_price <= 0:
                    continue

                pnl_pct = (live_price - pos["entry_price"]) / pos["entry_price"]
                entry_dt = datetime.fromisoformat(pos["entry_time"])
                hours_held = (_now() - entry_dt).total_seconds() / 3600

                reason = None
                if pnl_pct >= cfg["take_profit_pct"]:
                    reason = "take_profit"
                elif pnl_pct <= -cfg["disaster_pct"]:
                    reason = "disaster_stop"
                elif pnl_pct <= -cfg["stop_loss_pct"]:
                    reason = "stop_loss"
                elif hours_held >= cfg["max_hold_hours"]:
                    reason = "max_hold_72h"

                if reason:
                    self._execute_sell(ticker, live_price, reason)
            except Exception as exc:
                LOGGER.error("Error managing position %s: %s", ticker, exc)

    async def _close_all_positions(self, reason: str) -> None:
        for ticker in list(self._positions.keys()):
            try:
                price = await asyncio.to_thread(self._get_live_price, ticker)
                if price <= 0:
                    price = self._positions[ticker]["entry_price"]
                self._execute_sell(ticker, price, reason)
            except Exception as exc:
                LOGGER.error("Error closing %s: %s", ticker, exc)

    # ------------------------------------------------------------------ #
    # Signal evaluation
    # ------------------------------------------------------------------ #

    async def _evaluate_new_signals(self) -> None:
        if self._cfg is None or self._session is None:
            return
        cfg = self._cfg
        _, latest_data = await asyncio.to_thread(storage.latest_version)
        if not latest_data:
            LOGGER.debug("Paper trading: no scan data available.")
            return

        for stock in latest_data:
            ticker = stock.get("Ticker")
            if not ticker or ticker in self._positions:
                continue

            td_signal = str(stock.get("TD_Signal", ""))
            rsi = float(stock.get("RSI") or 0)
            score = int(stock.get("Score") or 0)
            ema_cross = str(stock.get("EMA_Cross", ""))
            scan_price = float(stock.get("Price") or 0)

            if score < cfg["min_score"]:
                continue
            if td_signal not in cfg["td_signals"]:
                continue
            if not (cfg["rsi_min"] <= rsi <= cfg["rsi_max"]):
                continue
            if cfg["require_ema_cross"] and ema_cross != "CROSS UP":
                continue

            # ── Real-time checks ──
            try:
                live_price = await asyncio.to_thread(self._get_live_price, ticker)
                if live_price <= 0:
                    continue

                if scan_price > 0 and abs(live_price - scan_price) / scan_price > 0.03:
                    LOGGER.info("Paper: %s skipped — price drifted > 3%% from scan.", ticker)
                    continue

                fresh_rsi = await asyncio.to_thread(self._get_live_rsi, ticker)
                if fresh_rsi is not None and not (cfg["rsi_min"] <= fresh_rsi <= cfg["rsi_max"] + 5):
                    LOGGER.info("Paper: %s skipped — live RSI %.1f out of range.", ticker, fresh_rsi)
                    continue

                fresh_signal = await asyncio.to_thread(get_candle_signal, ticker)
                if str(fresh_signal.get("TD_Signal", "")) not in ["STRONG BUY", "BUY"]:
                    LOGGER.info("Paper: %s skipped — fresh candle is %s.", ticker, fresh_signal.get("TD_Signal"))
                    continue

            except Exception as exc:
                LOGGER.error("Paper: real-time check failed for %s: %s", ticker, exc)
                continue

            position_value = self._available_capital * cfg["position_pct"]
            if position_value < 1.0:
                continue
            shares = position_value / live_price
            self._execute_buy(ticker, live_price, shares, score, f"score={score} td={td_signal}")

    # ------------------------------------------------------------------ #
    # Trade execution
    # ------------------------------------------------------------------ #

    def _execute_buy(self, ticker: str, price: float, shares: float, score: int, reason: str) -> None:
        value = price * shares
        self._available_capital -= value
        self._positions[ticker] = {
            "entry_price": round(price, 4),
            "shares": round(shares, 4),
            "entry_value": round(value, 2),
            "entry_time": _now().isoformat(),
            "scan_score": score,
        }
        paper_storage.save_trade(
            {
                "session_id": self._session["id"],
                "ticker": ticker,
                "action": "BUY",
                "price": round(price, 4),
                "shares": round(shares, 4),
                "value": round(value, 2),
                "scan_score": score,
                "reason": reason,
                "pnl": None,
                "timestamp": _ts(),
            }
        )
        LOGGER.info("Paper BUY  %s @ %.4f × %.4f = $%.2f (%s)", ticker, price, shares, value, reason)

    def _execute_sell(self, ticker: str, price: float, reason: str) -> None:
        pos = self._positions.pop(ticker, None)
        if pos is None:
            return
        value = price * pos["shares"]
        pnl = value - pos["entry_value"]
        self._available_capital += value
        paper_storage.save_trade(
            {
                "session_id": self._session["id"],
                "ticker": ticker,
                "action": "SELL",
                "price": round(price, 4),
                "shares": round(pos["shares"], 4),
                "value": round(value, 2),
                "scan_score": pos.get("scan_score"),
                "reason": reason,
                "pnl": round(pnl, 2),
                "timestamp": _ts(),
            }
        )
        LOGGER.info(
            "Paper SELL %s @ %.4f × %.4f = $%.2f  P&L: %+.2f (%s)", ticker, price, pos["shares"], value, pnl, reason
        )

    # ------------------------------------------------------------------ #
    # Market data helpers (run in thread)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_live_price(ticker: str) -> float:
        try:
            info = yf.Ticker(ticker).fast_info
            price = float(getattr(info, "last_price", 0) or 0)
            return price if price > 0 else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _get_live_rsi(ticker: str, period: int = 14) -> Optional[float]:
        try:
            hist = yf.Ticker(ticker).history(period="30d", interval="1d")
            if hist.empty or len(hist) < period + 1:
                return None
            delta = hist["Close"].diff()
            gain = delta.clip(lower=0).rolling(period).mean()
            loss = -delta.clip(upper=0).rolling(period).mean()
            rs = gain / loss
            val = float((100 - (100 / (1 + rs))).iloc[-1])
            return val if not math.isnan(val) else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Session finalisation
    # ------------------------------------------------------------------ #

    def _finish_session(self, status: str) -> None:
        if self._session is None:
            return
        initial = self._session["capital"]
        current_value = self._available_capital + sum(p["entry_value"] for p in self._positions.values())
        final_pnl = round(current_value - initial, 2)
        final_capital = round(current_value, 2)
        paper_storage.update_session_status(
            session_id=self._session["id"],
            status=status,
            ended_at=_ts(),
            final_pnl=final_pnl,
            final_capital=final_capital,
        )
        self._session.update(status=status, ended_at=_ts(), final_pnl=final_pnl, final_capital=final_capital)
        LOGGER.info("Paper session %s → %s  final_pnl=%+.2f", self._session["id"], status, final_pnl)
