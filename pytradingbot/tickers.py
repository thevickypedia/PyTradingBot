import json
import logging
import os
from http import HTTPStatus
from typing import List

import yfinance
from fastapi.exceptions import HTTPException
from pydantic import BaseModel

from pytradingbot.constants import env, config

logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def is_valid_ticker(ticker: str) -> bool:
    """Check if a ticker symbol is valid by attempting to fetch its data.

    Args:
        ticker: Ticker symbol to validate.

    Returns:
        bool:
        True if the ticker is valid, False otherwise.
    """
    try:
        data = yfinance.Ticker(ticker).history(period="1d")
        return not data.empty
    except Exception:
        return False


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

    def add(self, ticker: str):
        """Add a ticker to the subscription list if it's not already present."""
        tickers = self.get_all()
        if ticker not in tickers:
            tickers.append(ticker)
            self._save(tickers)

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

    ticker: str


async def get_tickers() -> List[str]:
    """Get the list of subscribed tickers.

    Returns:
        List[str]:
        A list of subscribed ticker symbols.
    """
    return ticker_manager.get_all()


async def add_ticker(payload: TickerSubscription) -> None:
    """Add a ticker to the subscription list.

    Args:
        payload: TickerSubscription object containing the ticker symbol to add.

    Raises:
        HTTPException:
        If the ticker symbol is empty or invalid.
    """
    if not payload.ticker:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Ticker symbol cannot be empty")
    if is_valid_ticker(payload.ticker):
        ticker_manager.add(payload.ticker)
    else:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"Invalid ticker symbol: {payload.ticker!r}")


async def remove_ticker(ticker: str):
    """Remove a ticker from the subscription list.

    Args:
        ticker: Ticker symbol to remove.
    """
    ticker_manager.remove(ticker)
