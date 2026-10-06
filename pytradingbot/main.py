import math
import pathlib
from collections.abc import Generator
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from finvizfinance.quote import finvizfinance
from finvizfinance.screener.overview import Overview
from finvizfinance.screener.technical import Technical
from jinja2 import Environment, FileSystemLoader, select_autoescape

from pytradingbot.constants import LOGGER, config
from pytradingbot.resilience import (
    FINVIZ_OVERVIEW,
    FINVIZ_TECHNICAL,
    clean_ohlcv,
    fetch_ohlcv,
    first_value,
    num,
    rename_aliases,
    retry,
    safe_call,
)
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


# TODO: Move this to module level
#   Most functions can become asynchronous
# Jinja2 environment — points at pytradingbot/templates/
_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape([]),  # HTML handled by template itself
    keep_trailing_newline=True,
)


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ATR using Wilder's True Range smoothing (ewm com=period-1).

    Matches the Finviz ATR display more closely than span-based ewm.
    """
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def normalize_change(raw: float) -> float:
    """Normalize Change value to percentage regardless of source.

    Finviz returns decimal (0.23 = 23%).
    Backtest / yfinance returns real % (2.3 = 2.3%).
    Threshold of 2.0 safely separates the two without false positives
    since a 200% daily move is essentially impossible on liquid stocks.
    """
    try:
        val = float(raw)
        return val * 100 if abs(val) < 2.0 else val
    except (TypeError, ValueError):
        return 0.0


def enrich_ticker(ticker: str) -> pd.Series:
    """Enrich ticker with latest news and insider action.

    Args:
        ticker: Ticker to enrich.

    Returns:
        pd.Series: Series with latest news and insider action.
    """
    stock = safe_call(lambda: finvizfinance(ticker))
    news = safe_call(stock.ticker_news) if stock else None
    insider = safe_call(stock.ticker_inside_trader) if stock else None
    return pd.Series(
        {
            "Latest_News": first_value(news, ["Title", "Headline"], "No news"),
            "Insider_Action": first_value(insider, ["Transaction", "Type"], "No insider data"),
        }
    )


def get_candle_signal(ticker: str = None, df: pd.DataFrame = None) -> pd.Series:
    """Uses yfinance 5min candles for full signal analysis.

    See Also:
        Technical Analysis - EMA Crossover: Strategy based on short-term vs long-term EMA crossovers.
        Candlestick Analysis: Price action method using OHLC data to determine trend and momentum.
        Volume Analysis: Confirms strength of price moves using volume spikes.

    Args:
        ticker: Ticker symbol to download data for.
        df: Pre-built DataFrame to use instead of downloading.

    Returns:
        pd.Series: TD_Signal, TD_Trend, YF_Signal, EMA_Cross.
    """
    try:
        if df is None or df.empty:
            assert ticker is not None, "No ticker provided."
            df = fetch_ohlcv(ticker, period="1d", interval="5m")
        else:
            df = clean_ohlcv(df)

        # Need at least 3 rows for meaningful comparison
        if len(df) < 3:
            return pd.Series(
                {"TD_Signal": "No data", "TD_Trend": "Unknown", "YF_Signal": "No data", "EMA_Cross": "Unknown"}
            )

        # ---- Candle Direction Analysis (last 5 candles) ----
        window = df.tail(5)
        close = window["Close"].values.astype(float)
        open_ = window["Open"].values.astype(float)
        high = window["High"].values.astype(float)
        low = window["Low"].values.astype(float)

        bullish = close > open_
        bullish_count = int(np.sum(bullish))

        higher_high = float(high[-1]) > float(high[-2])
        higher_low = float(low[-1]) > float(low[-2])

        # ---- TD Signal ----
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

        # ---- EMA Crossover Analysis (full df for accurate EMA) ----
        df = df.copy()
        df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
        df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()

        last_ema9 = float(df["EMA9"].iloc[-1])
        last_ema21 = float(df["EMA21"].iloc[-1])
        prev_ema9 = float(df["EMA9"].iloc[-2])
        prev_ema21 = float(df["EMA21"].iloc[-2])
        last_volume = float(df["Volume"].iloc[-1])
        avg_volume = float(df["Volume"].mean())

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
        LOGGER.error(f"Error fetching candle data for {ticker}: {e}")
        return pd.Series({"TD_Signal": "Error", "TD_Trend": "Error", "YF_Signal": "Error", "EMA_Cross": "Error"})


def _f(v, default=0.0) -> float:
    x = pd.to_numeric(v, errors="coerce")
    return default if pd.isna(x) else float(x)


def compute_trade_levels(row: pd.Series) -> pd.Series:
    """Compute entry, stop loss and take profit based on ATR.

    Uses 1.5x ATR stop and 3x ATR target = 2:1 risk reward minimum.

    Args:
        row: DataFrame row with Price and ATR columns.

    Returns:
        pd.Series: Entry, Stop_Loss, Take_Profit, Risk_Reward.
    """
    # compute_trade_levels
    price = _f(row.get("Price", row.get("Close")))
    atr = _f(row.get("ATR"))

    if price == 0 or atr == 0:
        return pd.Series({"Entry": price, "Stop_Loss": None, "Take_Profit": None, "Risk_Reward": None})

    stop_loss = round(max(price * 0.85, price - (1.5 * atr)), 2)
    take_profit = round(price + (3.0 * atr), 2)
    risk = price - stop_loss
    reward = take_profit - price
    risk_reward = round(reward / risk, 2) if risk > 0 else 0.0

    return pd.Series({"Entry": price, "Stop_Loss": stop_loss, "Take_Profit": take_profit, "Risk_Reward": risk_reward})


def score_stock(row: pd.Series) -> int:
    """Score a stock from 0-100 based on momentum, volume, RSI, ATR, candles and insider action.

    Args:
        row: DataFrame row with all enriched columns.

    Returns:
        int: Score between -100 and 100.
    """
    score = 0

    # Normalize change to real percentage regardless of source
    change = normalize_change(row.get("Change", 0))

    volume = _f(row.get("Volume"))
    rsi = _f(row.get("RSI"), 50)
    atr = _f(row.get("ATR"))
    price = _f(row.get("Price", row.get("Close")), 1)

    # ---- VOLUME CONVICTION (max 25 pts) ----
    if volume > 5_000_000:
        score += 25
    elif volume > 2_000_000:
        score += 15
    elif volume > 500_000:
        score += 10

    # ---- MOMENTUM (max 20 pts) ----
    # Reward early moves (3-8%), penalize extended (>15%) and negative
    if 3 <= change <= 8:
        score += 20
    elif 8 < change <= 15:
        score += 10
    elif change > 15:
        score += 0  # likely a top, no reward
    elif change < 0:
        score -= 10

    # ---- RSI ENTRY ZONE (max 25 pts) ----
    # Best entries are RSI 45-58: momentum building, not exhausted
    if 45 <= rsi <= 58:
        score += 25
    elif 58 < rsi <= 65:
        score += 15
    elif 65 < rsi <= 70:
        score += 5
    elif rsi > 70:
        score -= 20  # overbought
    elif rsi < 40:
        score -= 10  # weak, no momentum

    # ---- ATR QUALITY (max 15 pts) ----
    # Reward stocks with 2-5% ATR relative to price: enough to profit, not too wild
    atr_pct = (atr / price * 100) if price > 0 else 0
    if 2 <= atr_pct <= 5:
        score += 15
    elif 1 <= atr_pct < 2:
        score += 8
    elif 5 < atr_pct <= 15:
        score += 0  # too volatile to score positively
    elif atr_pct > 15:
        score -= 10  # extreme volatility — penny-stock behavior

    # ---- CANDLE CONFLUENCE (max 20 pts) ----
    td = str(row.get("TD_Signal", ""))
    yf_sig = str(row.get("YF_Signal", ""))
    trend = str(row.get("TD_Trend", ""))
    ema = str(row.get("EMA_Cross", ""))

    if td == "STRONG BUY" and yf_sig == "STRONG BUY" and ema == "CROSS UP":
        score += 20
    elif td in ["STRONG BUY", "BUY"] and yf_sig in ["STRONG BUY", "BUY"]:
        score += 12
    elif td == "BUY" and trend == "UPTREND":
        score += 8
    elif td == "SELL" or yf_sig == "SELL":
        score -= 20
    elif td == "WEAK - WAIT" and yf_sig == "WEAK - WAIT":
        score -= 5

    # ---- INSIDER ACTION (max 15 pts) ----
    insider = str(row.get("Insider_Action", ""))
    if "Buy" in insider and "Proposed" not in insider:
        score += 15  # genuine buy = strong signal
    elif "Proposed" in insider and "Sale" not in insider:
        score += 5  # scheduled buy, mild positive
    elif "Proposed Sale" in insider:
        score -= 5  # scheduled sale, mild negative
    elif "Sale" in insider and "Proposed" not in insider:
        score -= 15  # genuine sale = red flag

    # ---- TREND CONFIRMATION (max 10 pts) ----
    # SMA20/SMA50 from Finviz; EMA50/EMA200 proxies from backtest — both handled here
    _sma20 = pd.to_numeric(row.get("SMA20", None), errors="coerce")
    _sma50 = pd.to_numeric(row.get("SMA50", None), errors="coerce")
    sma20 = float(_sma20) if pd.notna(_sma20) else 0.0
    sma50 = float(_sma50) if pd.notna(_sma50) else 0.0
    if sma20 > 0 and sma50 > 0:
        if sma20 > sma50 and price > sma20:
            score += 10  # price above both MAs, short above long — strong uptrend
        elif sma20 > sma50:
            score += 5  # MAs bullish aligned but price hasn't broken above yet
        elif sma20 < sma50:
            score -= 10  # short MA below long MA — underlying downtrend

    return score


def get_signals(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, bool]:
    """Derive strong buy/sell signals from the enriched dataframe.

    Falls back to top/bottom 2 scored stocks if no strong signals exist.

    Args:
        df: Enriched DataFrame with Score column.

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame, bool]:
        strong_buy df, strong_sell df, and fallback flag (True = fallback used).
    """
    strong_buy = df[
        (df["TD_Signal"] == "STRONG BUY")
        & (df["YF_Signal"].isin(["STRONG BUY", "BUY"]))
        & (df["TD_Trend"] == "UPTREND")
        & (df["EMA_Cross"] == "CROSS UP")
        & (df["RSI"].between(45, 65))
        & (df["Score"] >= 60)
        & (~df["Insider_Action"].str.contains("Sale", na=False))
    ]

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
    """Convert dataframe to JSON-safe list of dicts with NaN replaced by None.

    Args:
        df: Enriched DataFrame.

    Returns:
        List[Dict[str, Any]]: JSON-safe records.
    """
    records = df.to_dict(orient="records")

    def _clean(v):
        try:
            return None if (isinstance(v, float) and math.isnan(v)) else v
        except (TypeError, ValueError):
            return v

    return [{k: _clean(v) for k, v in row.items()} for row in records]


def custom_tickers_builder(tickers: List[str]) -> Generator[Dict[str, Any], None, None]:
    """Generate base metrics for manually tracked tickers via yfinance.

    Uses 2-day daily history to compute Change, RSI approximation, and ATR.

    Args:
        tickers: List of ticker symbols.

    Yields:
        Dict[str, Any]: Metric dict per ticker.
    """
    for ticker in tickers:
        price, change, volume, rsi, atr = "N/A", "N/A", "N/A", "N/A", "N/A"
        try:
            hist = fetch_ohlcv(ticker, history=True, period="30d", interval="1d")

            if hist.empty or len(hist) < 2:
                continue

            latest = hist.iloc[-1]
            prev = hist.iloc[-2]

            price = float(latest["Close"])
            change = ((float(latest["Close"]) - float(prev["Close"])) / float(prev["Close"])) * 100
            volume = float(latest["Volume"])
            atr = float(compute_atr(hist).iloc[-1])

            # Proper RSI-14 requires 14 periods minimum
            if len(hist) >= 15:
                delta = hist["Close"].diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = -delta.clip(upper=0).rolling(14).mean()
                rs = gain / loss
                rsi_val = 100 - (100 / (1 + rs.iloc[-1]))
                rsi = float(rsi_val) if not math.isnan(float(rsi_val)) else 50.0
            else:
                rsi = 50.0

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


@retry(times=3, delay=2, default=pd.DataFrame)
def _screen(cls, filters):
    s = cls()
    s.set_filter(filters_dict=filters)
    return s.screener_view()


def builder(filepath: str = None, filters: dict | None = None, jinja_template: bool = True) -> pd.DataFrame:
    """Build enriched trading signal dataframe from Finviz scan + custom tickers.

    Args:
        filepath: Optional path to save output (.csv, .xlsx, .json, .html).
        filters: Finviz filter dict. Falls back to config.DEFAULT_FILTERS.

    Returns:
        pd.DataFrame: Enriched, scored, and trade-leveled DataFrame.
    """
    _filters = filters or config.DEFAULT_FILTERS
    LOGGER.info(f"Starting scan with filters: {_filters}")

    scan_df = _screen(Overview, _filters)
    if scan_df is None or scan_df.empty:
        LOGGER.warning("Overview screener returned no results — check filter values: %s", _filters)
        return pd.DataFrame(columns=FILTERED_COLUMNS)
    scan_df = rename_aliases(scan_df, FINVIZ_OVERVIEW)
    if scan_df["Ticker"].isna().all():
        LOGGER.error("Finviz overview has no ticker column — aborting scan")
        return pd.DataFrame(columns=FILTERED_COLUMNS)

    tech_cols = [c for c in FINVIZ_TECHNICAL if c != "Ticker"]
    tech_df = _screen(Technical, _filters)
    if tech_df is None or tech_df.empty:  # recover: continue with overview only
        LOGGER.warning("Technical screener unavailable — continuing without it")
        merged_df = scan_df.assign(**{c: np.nan for c in tech_cols})
    else:
        tech_df = rename_aliases(tech_df, FINVIZ_TECHNICAL)
        merged_df = scan_df.merge(tech_df[["Ticker"] + tech_cols], on="Ticker", how="left")

    enriched = merged_df["Ticker"].apply(enrich_ticker)
    merged_df = pd.concat([merged_df, enriched], axis=1)

    signals = merged_df["Ticker"].apply(get_candle_signal)
    merged_df = pd.concat([merged_df, signals], axis=1)

    for col in ("Price", "Change", "Volume", "ATR", "RSI"):
        merged_df[col] = num(merged_df[col])

    merged_df = merged_df[merged_df["RSI"].isna() | (merged_df["RSI"] < 70)]
    merged_df["Score"] = merged_df.apply(score_stock, axis=1)
    merged_df["Source"] = "Finviz"

    # Custom tickers not already in scan
    custom_tickers = [t for t in ticker_manager.get_all() if t not in set(merged_df["Ticker"].astype(str))]
    custom_df = pd.DataFrame(list(custom_tickers_builder(custom_tickers)))

    if not custom_df.empty:
        LOGGER.info(f"Processing {len(custom_df)} custom tickers")
        enriched = custom_df["Ticker"].apply(enrich_ticker)
        custom_df = pd.concat([custom_df, enriched], axis=1)
        signals = custom_df["Ticker"].apply(get_candle_signal)
        custom_df = pd.concat([custom_df, signals], axis=1)
        custom_df["Score"] = custom_df.apply(score_stock, axis=1)
        custom_df["Source"] = "Manual"
        # Add missing columns as NaN so concat doesn't fail
        for col in FILTERED_COLUMNS:
            if col not in custom_df.columns:
                custom_df[col] = None
        custom_df = custom_df[FILTERED_COLUMNS]

    filtered_df = merged_df.reindex(columns=FILTERED_COLUMNS)
    final_df = pd.concat([filtered_df, custom_df], ignore_index=True) if not custom_df.empty else filtered_df
    final_df = final_df.drop_duplicates(subset=["Ticker"])

    # Compute and attach trade levels
    trade_levels = final_df.apply(compute_trade_levels, axis=1)
    final_df = pd.concat([final_df, trade_levels], axis=1)

    # Only keep trades with acceptable risk/reward
    final_df = final_df[final_df["Risk_Reward"] >= 2.0]
    final_df = final_df.sort_values("Score", ascending=False).reset_index(drop=True)

    if filepath:
        ext = filepath.split(".")[-1]
        match ext:
            case "csv":
                final_df.to_csv(filepath, index=False)
            case "xlsx":
                final_df.to_excel(filepath, index=False)
            case "json":
                final_df.to_json(filepath, orient="records", lines=True)
            case "html":
                final_df.to_html(filepath, index=False)
            case _:
                raise ValueError(f"Unsupported file format: .{ext}. Use .csv, .xlsx, .json, or .html")

    if jinja_template:
        # ── Render ──────────────────────────────────────────────────────────────
        template = _jinja_env.get_template("main.html")
        html = template.render(RAW_DATA=final_df.to_json(orient="records"))

        path = "enriched.html"
        with open(path, "w") as fh:
            fh.write(html)
        LOGGER.info("Backtest report saved to %s", path)

    return final_df


if __name__ == "__main__":
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    print(builder(filepath="main.html"))
