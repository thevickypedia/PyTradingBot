import asyncio
from datetime import datetime
from typing import Awaitable, Callable

from fastapi import FastAPI

from pytradingbot.constants import LOGGER, MARKET_TIMEZONE

ScanTrigger = Callable[[FastAPI, dict, str, bool], Awaitable[bool]]


def _parse_hhmm(value: str) -> int:
    hour_str, minute_str = value.split(":", maxsplit=1)
    hour = int(hour_str)
    minute = int(minute_str)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Invalid time value: {value}")
    return (hour * 60) + minute


def _window_contains(now_minutes: int, start: int, end: int) -> tuple[bool, int | None]:
    """Return whether *now_minutes* falls inside the window and its minute offset from start."""
    if start == end:
        return False, None
    if start < end:
        if start <= now_minutes < end:
            return True, now_minutes - start
        return False, None

    # Overnight window, e.g. 21:35 -> 04:00
    if now_minutes >= start:
        return True, now_minutes - start
    if now_minutes < end:
        return True, (1440 - start) + now_minutes
    return False, None


def should_run_now(schedule: dict, now_est: datetime) -> bool:
    """Return True when the current EST minute matches any enabled schedule rule."""
    if now_est.weekday() >= 5:  # skip weekends
        return False

    now_minutes = (now_est.hour * 60) + now_est.minute

    for window in schedule.get("windows", []):
        if not window.get("enabled", True):
            continue
        try:
            start = _parse_hhmm(str(window["start"]))
            end = _parse_hhmm(str(window["end"]))
            interval = int(window["interval_minutes"])
        except (KeyError, TypeError, ValueError):
            continue

        if interval <= 0:
            continue

        is_active, minute_offset = _window_contains(now_minutes, start, end)
        if is_active and minute_offset is not None and minute_offset % interval == 0:
            return True

    after_hours = schedule.get("after_hours", {})
    if after_hours.get("enabled", True):
        try:
            run_time = _parse_hhmm(str(after_hours.get("run_time", "16:15")))
            close_time = _parse_hhmm(str(after_hours.get("close", "20:00")))
            if run_time <= now_minutes < close_time:
                return now_minutes == run_time
        except (TypeError, ValueError):
            return False
    return False


class ScanScheduler:
    """Background scheduler that evaluates schedule rules and triggers scans."""

    def __init__(self, app: FastAPI, trigger_scan: ScanTrigger, tick_seconds: int = 20) -> None:
        """Initialize the background scheduler."""
        self._app = app
        self._trigger_scan = trigger_scan
        self._tick_seconds = tick_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the background scheduler."""
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        LOGGER.info("Background scheduler started.")

    async def stop(self) -> None:
        """Stop the background scheduler."""
        self._stop_event.set()
        if self._task:
            await self._task
        LOGGER.info("Background scheduler stopped.")

    async def _run_loop(self) -> None:
        """Run the background scheduler."""
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Scheduler tick failed: %s", exc)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._tick_seconds)
            except TimeoutError:
                pass

    async def _tick(self) -> None:
        """Tick the scheduler."""
        schedule = getattr(self._app.state, "schedule_config", None)
        if not isinstance(schedule, dict) or not schedule.get("enabled", True):
            return

        now_est = datetime.now(MARKET_TIMEZONE)
        if not should_run_now(schedule, now_est):
            return

        minute_key = now_est.strftime("%Y-%m-%d %H:%M")
        if getattr(self._app.state, "last_scheduler_minute", None) == minute_key:
            return

        filters = dict(getattr(self._app.state, "current_filters", {}))
        started = await self._trigger_scan(self._app, filters, "scheduler", True)
        if started:
            self._app.state.last_scheduler_minute = minute_key
