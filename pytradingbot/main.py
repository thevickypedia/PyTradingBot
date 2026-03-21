import math
from typing import Any, Dict, List

import pandas as pd
import yfinance as yf
from finvizfinance.quote import finvizfinance
from finvizfinance.screener.overview import Overview
from finvizfinance.screener.technical import Technical

from pytradingbot.constants import DEFAULT_FILTERS, LOGGER


def enrich_ticker(ticker: str) -> pd.Series:
    """Enrich ticker with latest candle data."""
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


def get_candle_signal(ticker: str) -> pd.Series:
    """Uses yfinance 5min candles for full signal analysis."""
    try:
        df = yf.download(ticker, period="1d", interval="5m", progress=False)

        if df.empty:
            return pd.Series(
                {"TD_Signal": "No data", "TD_Trend": "Unknown", "YF_Signal": "No data", "EMA_Cross": "Unknown"}
            )

        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # ---- Candle Direction Analysis ----
        last_5 = df.tail(5).copy()
        last_5["bullish"] = last_5["Close"] > last_5["Open"]
        bullish_count = last_5["bullish"].sum()

        last_candle = last_5.iloc[-1]
        prev_candle = last_5.iloc[-2]

        higher_high = last_candle["High"].item() > prev_candle["High"].item()
        higher_low = last_candle["Low"].item() > prev_candle["Low"].item()

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
    """Assign scoring based on volume, momentum, RSI, insider action and candles."""
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


def builder(
    filepath: str = None, to_dict: bool = False, filters: dict | None = None
) -> pd.DataFrame | List[Dict[str, Any]]:
    """Build a dataframe from the raw data."""
    # Use caller-supplied filters or fall back to module-level defaults
    _filters = filters or DEFAULT_FILTERS

    LOGGER.info(f"Starting scan with filters: {_filters}")

    # Run screeners
    foverview = Overview()
    foverview.set_filter(filters_dict=_filters)
    scan_df = foverview.screener_view()
    if scan_df is None or scan_df.empty:
        LOGGER.warning("Overview screener returned no results — check filter values: %s", _filters)
        return (
            []
            if to_dict
            else pd.DataFrame(
                columns=[
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
            )
        )

    ftech = Technical()
    ftech.set_filter(filters_dict=_filters)
    tech_df = ftech.screener_view()
    if tech_df is None or tech_df.empty:
        LOGGER.warning("Technical screener returned no results — check filter values: %s", _filters)
        return (
            []
            if to_dict
            else pd.DataFrame(
                columns=[
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
            )
        )

    # Build final dataframe
    final_df = scan_df.merge(tech_df[["Ticker", "Beta", "ATR", "SMA20", "SMA50", "RSI", "Gap"]], on="Ticker")
    enriched = final_df["Ticker"].apply(enrich_ticker)
    final_df = pd.concat([final_df, enriched], axis=1)

    # Candle signals
    signals = final_df["Ticker"].apply(get_candle_signal)
    final_df = pd.concat([final_df, signals], axis=1)

    # Numeric conversions
    final_df["Volume"] = pd.to_numeric(final_df["Volume"].astype(str).str.replace(",", ""), errors="coerce")
    final_df["ATR"] = pd.to_numeric(final_df["ATR"], errors="coerce")
    final_df["RSI"] = pd.to_numeric(final_df["RSI"], errors="coerce")
    final_df["Change"] = pd.to_numeric(final_df["Change"].astype(str).str.replace("%", ""), errors="coerce")

    final_df = final_df[final_df["RSI"] < 70]
    final_df["Score"] = final_df.apply(score_stock, axis=1)
    final_df = final_df.sort_values("Score", ascending=False)

    filtered_df = final_df[
        [
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
    ]
    if filepath:
        match filepath.split(".")[-1]:
            case "csv":
                filtered_df.to_csv(filepath, index=False)
            case "xlsx":
                filtered_df.to_excel(filepath, index=False)
            case "json":
                filtered_df.to_json(filepath, orient="records", lines=True)
            case "html":
                filtered_df.to_html(filepath, index=False)
            case _:
                raise ValueError("Unsupported file format. Use .csv, .xlsx, .json, or .html")

    if to_dict:
        records = filtered_df.to_dict(orient="records")

        # Replace float NaN with None for safe Jinja2 / JSON rendering.
        # df.where() cannot guarantee None for numeric columns, so we check each value.
        def _clean(v):
            """Convert NaN to None, leave other values unchanged."""
            try:
                return None if (isinstance(v, float) and math.isnan(v)) else v
            except (TypeError, ValueError):
                return v

        return [{k: _clean(v) for k, v in row.items()} for row in records]

    return filtered_df


if __name__ == "__main__":
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    print(builder(filepath="index.html"))
