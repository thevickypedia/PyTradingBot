import math
from collections.abc import Generator
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from finvizfinance.quote import finvizfinance
from finvizfinance.screener.overview import Overview
from finvizfinance.screener.technical import Technical

from pytradingbot.constants import LOGGER, config
from pytradingbot.tickers import ticker_manager

FILTERED_COLUMNS = [
    "Source",
    "Ticker",
    "Price",
    "Change",
    "Volume",
    "RSI",
    "ATR",
    "TD_Signal",
    "TD_Trend",
    "YF_Signal",
    "EMA_Cross",
    "Score",
    "Latest_News",
    "Insider_Action",
]


def enrich_ticker(ticker: str) -> pd.Series:
    """Enrich ticker with latest candle data.

    Args:
        ticker: Ticker to enrich.

    Returns:
        pd.Series:
        Series with latest news and insider action.
    """
    try:
        stock = finvizfinance(ticker)
        news = stock.ticker_news()
        insider = stock.ticker_inside_trader()
        latest_news = news["Title"].iloc[0] if news is not None and not news.empty else "No news"
        insider_action = (
            insider["Transaction"].iloc[0] if insider is not None and not insider.empty else "No insider data"
        )
        return pd.Series({"Latest_News": latest_news, "Insider_Action": insider_action})
    except Exception as err:
        LOGGER.error(f"Error enriching ticker {ticker}: {err}")
        return pd.Series({"Latest_News": "N/A", "Insider_Action": "N/A"})


def get_candle_signal(ticker: str = None, df: pd.DataFrame = None) -> pd.Series:
    """Uses yfinance 5min candles for full signal analysis.

    See Also:
        Technical Analysis - EMA Crossover: Strategy based on short-term vs long-term EMA crossovers.
        Candlestick Analysis: Price action method using OHLC data to determine trend and momentum.
        Volume Analysis: Confirms strength of price moves using volume spikes.

    Args:
        ticker: Ticker to use.
        df: Pandas DataFrame to use.

    Returns:
        pd.Series:
        Series with latest candle data.
    """
    try:
        if df is None or df.empty:
            assert ticker is not None, "No ticker provided."
            df = yf.download(ticker, period="1d", interval="5m", progress=False)

        if df.empty:
            return pd.Series(
                {"TD_Signal": "No data", "TD_Trend": "Unknown", "YF_Signal": "No data", "EMA_Cross": "Unknown"}
            )

        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # ---- Candle Direction Analysis ----
        close = df["Close"].values
        open_ = df["Open"].values
        high = df["High"].values
        low = df["Low"].values

        bullish = close > open_
        bullish_count = int(np.sum(bullish))

        higher_high = float(high[-1]) > float(high[-2])
        higher_low = float(low[-1]) > float(low[-2])

        # ---- TD SIGNAL ----
        if bullish_count >= 4 and higher_high and higher_low:
            td_signal = "STRONG BUY"
        elif bullish_count >= 3 and higher_high:
            td_signal = "BUY"
        elif bullish_count <= 1:
            td_signal = "SELL"
        elif bullish_count == 2:
            td_signal = "WEAK - WAIT"
        else:
            td_signal = "NEUTRAL"

        if higher_high and higher_low:
            td_trend = "UPTREND"
        elif not higher_high and not higher_low:
            td_trend = "DOWNTREND"
        else:
            td_trend = "SIDEWAYS"

        # ---- EMA Crossover Analysis ----
        df["EMA9"] = df["Close"].ewm(span=9).mean()
        df["EMA21"] = df["Close"].ewm(span=21).mean()

        last_ema9 = df["EMA9"].iloc[-1].item()
        last_ema21 = df["EMA21"].iloc[-1].item()
        prev_ema9 = df["EMA9"].iloc[-2].item()
        prev_ema21 = df["EMA21"].iloc[-2].item()
        last_volume = df["Volume"].iloc[-1].item()
        avg_volume = df["Volume"].mean().item()

        ema_cross_up = prev_ema9 < prev_ema21 and last_ema9 > last_ema21
        ema_cross_down = prev_ema9 > prev_ema21 and last_ema9 < last_ema21
        ema_above = last_ema9 > last_ema21
        volume_spike = last_volume > avg_volume * 1.5

        if ema_cross_up and volume_spike:
            yf_signal = "STRONG BUY"
        elif ema_above and volume_spike:
            yf_signal = "BUY"
        elif ema_cross_down:
            yf_signal = "SELL"
        elif not ema_above:
            yf_signal = "WEAK - WAIT"
        else:
            yf_signal = "NEUTRAL"

        ema_cross = "CROSS UP" if ema_cross_up else "CROSS DOWN" if ema_cross_down else "NO CROSS"

        return pd.Series({"TD_Signal": td_signal, "TD_Trend": td_trend, "YF_Signal": yf_signal, "EMA_Cross": ema_cross})

    except Exception as e:
        LOGGER.error(f"Error fetching candle data for {ticker} : {e}")
        return pd.Series({"TD_Signal": "Error", "TD_Trend": "Error", "YF_Signal": "Error", "EMA_Cross": "Error"})


def score_stock(row: pd.Series) -> int:
    """Assign scoring based on volume, momentum, RSI, insider action and candles.

    Args:
        row: DataFrame row with necessary columns for scoring.

    Returns:
        int:
        Score based on volume, momentum, RSI, insider action.
    """
    score = 0

    # Volume conviction (max 30 pts)
    if row["Volume"] > 5000000:
        score += 30
    elif row["Volume"] > 2000000:
        score += 20
    elif row["Volume"] > 1000000:
        score += 10

    # Momentum via Change % (max 25 pts)
    if row["Change"] > 20:
        score += 25
    elif row["Change"] > 10:
        score += 15
    elif row["Change"] > 5:
        score += 10

    # RSI sweet spot 50-65 = trending but not exhausted (max 25 pts)
    if 50 <= row["RSI"] <= 65:
        score += 25
    elif 40 <= row["RSI"] < 50:
        score += 15
    elif 65 < row["RSI"] < 70:
        score += 10

    # Insider buying bonus (max 20 pts)
    if "Buy" in str(row["Insider_Action"]):
        score += 20
    elif "Sale" in str(row["Insider_Action"]):
        score -= 10

    # Candle signal bonus (max 20 pts)
    if row["TD_Signal"] == "STRONG BUY" and row["YF_Signal"] == "STRONG BUY":
        score += 20  # both agree = high confidence
    elif row["TD_Signal"] == "BUY" or row["YF_Signal"] == "BUY":
        score += 10
    elif row["TD_Signal"] == "SELL" or row["YF_Signal"] == "SELL":
        score -= 15  # penalize conflicting signals hard

    return score


def get_signals(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, bool]:
    """Derive strong buy/sell signals from the enriched dataframe.

    See Also:
        If there are no strong buy/sell signals, a fallback is returned with the top 2 highest and lowest scored stocks.

    Args:
        df: DataFrame with enriched data.

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame, bool]:
        Tuple of dataframes with strong buy/sell signals, and a fallback boolean flag.
    """
    # Strong Buy
    strong_buy = df[
        (df["TD_Signal"] == "STRONG BUY")
        & (df["YF_Signal"].isin(["STRONG BUY", "BUY"]))
        & (df["TD_Trend"] == "UPTREND")
        & (df["EMA_Cross"] == "CROSS UP")
        & (df["RSI"].between(50, 65))
        & (df["Score"] >= 60)
        & (~df["Insider_Action"].str.contains("Sale", na=False))
    ]

    # Strong Sell
    strong_sell = df[
        (df["TD_Signal"] == "SELL")
        & (df["YF_Signal"].isin(["SELL", "WEAK - WAIT"]))
        & (df["TD_Trend"] == "DOWNTREND")
        & (df["EMA_Cross"] == "CROSS DOWN")
        & (df["RSI"] > 65)
        & (df["Score"] < 30)
    ]

    if strong_buy.empty and strong_sell.empty:
        return df.nlargest(2, "Score"), df.nsmallest(2, "Score"), True

    return strong_buy, strong_sell, False


def jsonify_scan_data(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert dataframe to list of dicts with NaN as None for JSON rendering.

    Args:
        df: DataFrame with enriched data.

    Returns:
        List[Dict[str, Any]]:
        A list of dicts with NaN as None for JSON rendering.
    """
    records = df.to_dict(orient="records")

    # Replace float NaN with None for safe Jinja2 / JSON rendering.
    # df.where() cannot guarantee None for numeric columns, so we check each value.
    def _clean(v):
        """Convert NaN to None, leave other values unchanged."""
        try:
            return None if (isinstance(v, float) and math.isnan(v)) else v
        except (TypeError, ValueError):
            return v

    return [{k: _clean(v) for k, v in row.items()} for row in records]


def custom_tickers_builder(tickers: List[str]) -> Generator[Dict[str, Any]]:
    """Generate metrics for custom tickers.

    Args:
        tickers: List of ticker symbols.

    Yields:
        Dict[str, Any]:
        Yields a key-value pair with metrics.
    """
    price, change, volume, rsi, atr = "N/A", "N/A", "N/A", "N/A", "N/A"
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker)

            hist = data.history(period="2d", interval="1d")
            if hist.empty or len(hist) < 2:
                continue

            latest = hist.iloc[-1]
            prev = hist.iloc[-2]

            price = latest["Close"]
            change = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100
            volume = latest["Volume"]

            delta = hist["Close"].diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = -delta.clip(upper=0).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1])) if not rs.empty else 50

            atr = latest["High"] - latest["Low"]

            yield {
                "Ticker": ticker,
                "Price": price,
                "Change": change,
                "Volume": volume,
                "RSI": rsi,
                "ATR": atr,
            }
        except Exception as err:
            LOGGER.error(f"Error fetching base data for custom {ticker}: {err}")
            yield {
                "Ticker": ticker,
                "Price": price,
                "Change": change,
                "Volume": volume,
                "RSI": rsi,
                "ATR": atr,
            }


def builder(filepath: str = None, filters: dict | None = None) -> pd.DataFrame:
    """Build a dataframe from the raw data.

    Args:
        filepath: Filepath to store the enriched data.
        filters: Filters to apply for finviz.

    Returns:
        pd.DataFrame:
        DataFrame with enriched data.
    """
    # Use caller-supplied filters or fall back to module-level defaults
    _filters = filters or config.DEFAULT_FILTERS

    LOGGER.info(f"Starting scan with filters: {_filters}")

    # Run screeners
    foverview = Overview()
    foverview.set_filter(filters_dict=_filters)
    scan_df = foverview.screener_view()
    if scan_df is None or scan_df.empty:
        LOGGER.warning("Overview screener returned no results — check filter values: %s", _filters)
        return pd.DataFrame(columns=FILTERED_COLUMNS)

    ftech = Technical()
    ftech.set_filter(filters_dict=_filters)
    tech_df = ftech.screener_view()
    if tech_df is None or tech_df.empty:
        LOGGER.warning("Technical screener returned no results — check filter values: %s", _filters)
        return pd.DataFrame(columns=FILTERED_COLUMNS)

    # Build merger dataframe
    merged_df = scan_df.merge(tech_df[["Ticker", "Beta", "ATR", "SMA20", "SMA50", "RSI", "Gap"]], on="Ticker")
    enriched = merged_df["Ticker"].apply(enrich_ticker)
    merged_df = pd.concat([merged_df, enriched], axis=1)

    # Candle signals
    signals = merged_df["Ticker"].apply(get_candle_signal)
    merged_df = pd.concat([merged_df, signals], axis=1)

    # Numeric conversions
    merged_df["Volume"] = pd.to_numeric(merged_df["Volume"].astype(str).str.replace(",", ""), errors="coerce")
    merged_df["ATR"] = pd.to_numeric(merged_df["ATR"], errors="coerce")
    merged_df["RSI"] = pd.to_numeric(merged_df["RSI"], errors="coerce")
    merged_df["Change"] = pd.to_numeric(merged_df["Change"].astype(str).str.replace("%", ""), errors="coerce")

    merged_df = merged_df[merged_df["RSI"] < 70]
    merged_df["Score"] = merged_df.apply(score_stock, axis=1)
    merged_df["Source"] = "Finviz"
    custom_tickers = [
        ticker for ticker in ticker_manager.get_all() if ticker not in set(merged_df["Ticker"].astype(str))
    ]

    custom_df = pd.DataFrame(list(custom_tickers_builder(custom_tickers)))
    if not custom_df.empty:
        LOGGER.info(f"Processing {len(custom_df)} custom tickers")

        enriched = custom_df["Ticker"].apply(enrich_ticker)
        custom_df = pd.concat([custom_df, enriched], axis=1)

        signals = custom_df["Ticker"].apply(get_candle_signal)
        custom_df = pd.concat([custom_df, signals], axis=1)

        custom_df["Score"] = custom_df.apply(score_stock, axis=1)
        custom_df["Source"] = "Manual"
        custom_df = custom_df[FILTERED_COLUMNS]

    filtered_df = merged_df[FILTERED_COLUMNS]
    final_df = pd.concat([filtered_df, custom_df], ignore_index=True)
    final_df = final_df.drop_duplicates(subset=["Ticker"])
    final_df = final_df.sort_values("Score", ascending=False)

    if filepath:
        match filepath.split(".")[-1]:
            case "csv":
                final_df.to_csv(filepath, index=False)
            case "xlsx":
                final_df.to_excel(filepath, index=False)
            case "json":
                final_df.to_json(filepath, orient="records", lines=True)
            case "html":
                final_df.to_html(filepath, index=False)
            case _:
                raise ValueError("Unsupported file format. Use .csv, .xlsx, .json, or .html")

    return final_df


if __name__ == "__main__":
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    print(builder(filepath="index.html"))
