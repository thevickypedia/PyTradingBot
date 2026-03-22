import json
import logging
import os
from http import HTTPStatus
from typing import Dict, List

import yfinance as yf
from fastapi.exceptions import HTTPException
from pydantic import BaseModel

from pytradingbot.constants import LOGGER, config

logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def check_validity(tickers: str) -> Dict[str, bool]:
    """Check if a ticker symbol is valid by attempting to fetch its data.

    Args:
        tickers: Ticker symbol(s) to validate.

    Returns:
        Dict[str, bool]:
        Dictionary of ticker symbols and their validity status (True if valid, False if invalid).
    """
    tickers_list = tickers.split()
    data = yf.download(tickers_list, period="1d", group_by="ticker", auto_adjust=False, progress=False)

    results = {}
    for ticker in tickers_list:
        try:
            results[ticker] = not data[ticker].empty
        except Exception as warn:
            LOGGER.warning(warn)
            results[ticker] = False
    return results


class TickerManager:
    """Manages ticker subscriptions for real-time updates.

    >>> TickerManager

    """

    def __init__(self):
        """Initialize the TickerManager and ensure the storage file exists."""
        self.filepath = config.TICKERS_PATH
        self._ensure_file()

    def _ensure_file(self):
        """Ensure the ticker storage file exists, creating it if necessary."""
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w") as f:
                json.dump([], f)

    def get_all(self) -> List[str]:
        """Get the list of all subscribed tickers."""
        with open(self.filepath) as f:
            return json.load(f)

    def add(self, tickers: List[str]):
        """Add ticker symbols to the subscription list if not already present."""
        base_tickers = self.get_all()
        updated_tickers = list(dict.fromkeys([*base_tickers, *tickers]))
        self._save(updated_tickers)

    def remove(self, ticker: str):
        """Remove a ticker from the subscription list if it exists."""
        tickers = self.get_all()
        tickers = [t for t in tickers if t != ticker]
        self._save(tickers)

    def _save(self, tickers: List[str]):
        """Save the list of tickers to the storage file."""
        with open(self.filepath, "w") as f:
            json.dump(tickers, f, indent=2)


ticker_manager = TickerManager()


class TickerSubscription(BaseModel):
    """Represents a ticker subscription for real-time updates."""

    tickers: str


async def get_tickers() -> List[str]:
    """Get the list of subscribed tickers.

    Returns:
        List[str]:
        A list of subscribed ticker symbols.
    """
    return ticker_manager.get_all()


async def add_ticker(payload: TickerSubscription):
    """Add a ticker to the subscription list.

    Args:
        payload: TickerSubscription object containing the ticker symbol to add.
    """
    if not payload.tickers:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Ticker symbol cannot be empty")
    existing = ticker_manager.get_all()
    filtered = [ticker for ticker in payload.tickers.split() if ticker not in existing]
    if not filtered:
        raise HTTPException(
            status_code=HTTPStatus.OK, detail=f"Ticker symbol(s) {', '.join(payload.tickers)} already exists"
        )
    status_flags = check_validity(" ".join(filtered))
    if valid := [ticker for ticker, valid in status_flags.items() if valid]:
        ticker_manager.add(valid)
    if invalid := [ticker for ticker, valid in status_flags.items() if not valid]:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=f"Invalid ticker symbol(s): {', '.join(invalid)}"
        )


async def remove_ticker(ticker: str):
    """Remove a ticker from the subscription list.

    Args:
        ticker: Ticker symbol to remove.
    """
    ticker_manager.remove(ticker)
