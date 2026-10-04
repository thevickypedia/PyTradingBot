import functools
import math
import time

import numpy as np
import pandas as pd
import yfinance as yf

from pytradingbot.constants import LOGGER

OHLCV = ["Open", "High", "Low", "Close", "Volume"]

# canonical name -> provider names we've seen / might see (priority order)
FINVIZ_OVERVIEW = {
    "Ticker": ["Ticker", "Symbol"],
    "Price": ["Price", "Last"],
    "Change": ["Change %", "Change", "Chg %"],
    "Volume": ["Volume", "Vol"],
}
FINVIZ_TECHNICAL = {
    "Ticker": ["Ticker", "Symbol"],
    "Beta": ["Beta"],
    "ATR": ["ATR", "ATR (14)", "Average True Range"],
    "SMA20": ["SMA20", "20-Day Simple Moving Average"],
    "SMA50": ["SMA50", "50-Day Simple Moving Average"],
    "RSI": ["RSI", "RSI (14)", "Relative Strength Index (14)"],
    "Gap": ["Gap"],
}


def retry(times=3, delay=1.0, default=None):
    """Retry a function call on exception, with exponential backoff."""

    def deco(fn):
        """Decorator to retry a function call on exception, with exponential backoff."""

        @functools.wraps(fn)
        def wrap(*a, **kw):
            """Wrapper function to retry a function call on exception, with exponential backoff."""
            for i in range(times):
                try:
                    return fn(*a, **kw)
                except Exception as err:
                    LOGGER.warning("%s failed (%d/%d): %s", fn.__name__, i + 1, times, err)
                    if i < times - 1:
                        time.sleep(delay * 2**i)
            return default() if callable(default) else default

        return wrap

    return deco


def safe_call(fn, default=None):
    """Call a function and return a default value on exception."""
    try:
        return fn()
    except Exception as err:
        LOGGER.warning("%s failed: %s", getattr(fn, "__name__", "call"), err)
        return default


def rename_aliases(df, aliases):
    """Keep all columns, add canonical ones from the first alias found (NaN if none)."""
    out = pd.DataFrame() if df is None else df.copy()
    lookup = {str(c).strip().lower(): c for c in out.columns}
    for canon, names in aliases.items():
        src = next((lookup[n.lower()] for n in names if n.lower() in lookup), None)
        if src is None:
            LOGGER.warning("Provider field '%s' not found (tried %s)", canon, names)
            out[canon] = np.nan
        else:
            out[canon] = out[src]
    return out


def first_value(df, names, default="N/A"):
    """Return the first non-empty value from the first column found in names, or default."""
    if df is None or df.empty:
        return default
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lookup:
            v = df[lookup[n.lower()]].iloc[0]
            if pd.notna(v) and str(v).strip():
                return v
    return default


def num(s):
    """'1,234' / '2.5%' / '1.2M' / '-' -> float (NaN if unparseable)."""
    t = pd.Series(s).astype(str).str.strip().str.replace(r"[,%$]", "", regex=True)
    suffix = t.str[-1:]
    mult = suffix.map({"K": 1e3, "M": 1e6, "B": 1e9}).fillna(1.0)
    t = t.where(~suffix.isin(["K", "M", "B"]), t.str[:-1])
    return pd.to_numeric(t, errors="coerce") * mult.values


def clean_ohlcv(df):
    """Flatten MultiIndex, coerce numerics. Close is required; O/H/L fall back to Close, Volume to 0."""
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLCV)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=lambda c: str(c).strip().title())
    if "Close" not in df and "Adj Close" in df:
        df["Close"] = df["Adj Close"]
    missing = [c for c in OHLCV if c not in df]
    if missing:
        LOGGER.warning("yfinance fields missing: %s", missing)
    out = pd.DataFrame(index=df.index)
    for c in OHLCV:
        out[c] = pd.to_numeric(df[c], errors="coerce") if c in df else np.nan
    out = out.dropna(subset=["Close"])
    for c in ("Open", "High", "Low"):
        out[c] = out[c].fillna(out["Close"])
    out["Volume"] = out["Volume"].fillna(0.0)
    return out


@retry(times=2, delay=0.5, default=pd.DataFrame)
def fetch_ohlcv(ticker, history=False, **kw):
    """Fetch OHLCV data for a ticker using yfinance, with optional history mode."""
    raw = yf.Ticker(ticker).history(**kw) if history else yf.download(ticker, progress=False, **kw)
    df = clean_ohlcv(raw)
    if df.empty:
        raise ValueError(f"no usable data for {ticker}")
    return df


def fast_price(ticker) -> float:
    """Get the last price of a ticker using fast_info, falling back to 5-day history if needed."""
    try:
        fi = yf.Ticker(ticker).fast_info
        for key in ("last_price", "lastPrice", "regular_market_price"):
            try:
                v = float(fi[key])
                if v > 0 and not math.isnan(v):
                    return v
            except Exception:
                continue
    except Exception as err:
        LOGGER.warning("fast_info failed for %s: %s", ticker, err)
    df = fetch_ohlcv(ticker, history=True, period="5d", interval="1d")
    return float(df["Close"].iloc[-1]) if not df.empty else 0.0
