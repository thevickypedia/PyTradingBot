import os
from datetime import datetime, timedelta
from multiprocessing.pool import ThreadPool
from typing import List

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

from pytradingbot.constants import LOGGER
from pytradingbot.main import (
    compute_atr,
    compute_trade_levels,
    get_candle_signal,
    normalize_change,
    score_stock,
)

# ---------------- CONFIG ----------------
TODAY = datetime.now()
FORWARD_DAYS = [1, 3, 5]
INITIAL_CAPITAL = 10_000
END_DATE = (TODAY - timedelta(days=5)).strftime("%Y-%m-%d")
START_DATE = TODAY.replace(TODAY.year - 3).strftime("%Y-%m-%d")

OUTPUT_DIR = "backtest_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
plt.style.use("dark_background")


# ---------------- HELPERS ----------------
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI for a given price series."""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute RSI, true ATR, Change, EMA and SMA indicators on a daily OHLCV DataFrame."""
    df = df.copy()
    df["RSI"] = compute_rsi(df["Close"])
    df["ATR"] = compute_atr(df)  # Wilder's True Range ATR — replaces single-bar range
    df["Change"] = df["Close"].pct_change() * 100
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Walk forward through the DataFrame generating signals and forward returns.

    For each row from index 200 onward, use the 30-candle window before it
    to generate candle signals (enough bars for EMA21 and EMA crossover to be
    meaningful). Rows failing price, volume, or macro-trend filters are skipped
    before scoring so only high-quality setups reach the report.

    Args:
        df: Indicator-enriched OHLCV DataFrame with EMA50/EMA200 columns.

    Returns:
        pd.DataFrame: Rows with signals, scores, trade levels and forward returns.
    """
    results = []
    for idx in range(50, len(df) - max(FORWARD_DAYS)):
        try:
            price = float(df.iloc[idx]["Close"])
            volume = float(df.iloc[idx]["Volume"])
            ema50 = float(df.iloc[idx]["EMA50"])
            ema200 = float(df.iloc[idx]["EMA200"])

            row = df.iloc[idx].copy()
            window = df.iloc[max(0, idx - 30) : idx]  # noqa: E203

            if len(window) < 21:
                continue

            signal = get_candle_signal(df=window)
            row["TD_Signal"] = signal["TD_Signal"]
            row["TD_Trend"] = signal["TD_Trend"]
            row["YF_Signal"] = signal["YF_Signal"]
            row["EMA_Cross"] = signal["EMA_Cross"]
            row["Insider_Action"] = "N/A"

            # Pull real computed indicator values — these are already real %
            row["Volume"] = volume
            row["RSI"] = float(df.iloc[idx]["RSI"])
            row["Change"] = float(df.iloc[idx]["Change"])
            row["ATR"] = float(df.iloc[idx]["ATR"])
            row["Price"] = price
            # Map EMA50/EMA200 into SMA20/SMA50 column names that score_stock expects
            row["SMA20"] = ema50
            row["SMA50"] = ema200

            row["Date"] = df.index[idx].strftime("%Y-%m-%d")
            row["Score"] = score_stock(row)

            # Compute trade levels per row
            levels = compute_trade_levels(row)
            row["Entry"] = levels["Entry"]
            row["Stop_Loss"] = levels["Stop_Loss"]
            row["Take_Profit"] = levels["Take_Profit"]
            row["Risk_Reward"] = levels["Risk_Reward"]

            # Forward returns
            for d in FORWARD_DAYS:
                future_price = float(df.iloc[idx + d]["Close"])
                row[f"FWD_{d}D"] = (future_price - price) / price * 100

            results.append(row)

        except Exception as error:
            LOGGER.error("Error at index %d: %s", idx, error)
            continue

    return pd.DataFrame(results)


# ----------------- WORKER -----------------
def worker(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Worker function to extract the dataframe for each ticker."""
    LOGGER.info("Processing %s", ticker)
    df = yf.download(ticker, start=start, end=end, progress=False)

    if df.empty:
        LOGGER.info("No data for %s, skipping.", ticker)
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df = df.apply(pd.to_numeric, errors="coerce").dropna()

    df = compute_indicators(df)
    df = df.dropna()  # drops NaN rows from rolling windows

    res = compute_signals(df)

    if res.empty:
        LOGGER.warning("No signals for %s, skipping.", ticker)

    return res


# ---------------- BACKTEST ----------------
def run_backtest(tickers: List[str], start_date: str, end_date: str) -> pd.DataFrame:
    """Download data, compute indicators and signals for all tickers.

    Returns:
        pd.DataFrame: Combined results across all tickers.
    """
    all_results = []
    processes = {
        ticker: ThreadPool(processes=1).apply_async(
            func=worker,
            args=(
                ticker,
                start_date,
                end_date,
            ),
        )
        for ticker in tickers
    }

    for ticker, process in processes.items():
        result = process.get()
        if result.empty:
            continue
        result["Ticker"] = ticker
        all_results.append(result)
    if not all_results:
        LOGGER.warning("No results found across all tickers.")
        return pd.DataFrame()

    return pd.concat(all_results, ignore_index=True).dropna(subset=["Score"])


# ---------------- WIN RATE ANALYSIS ----------------
def analyze_with_levels(df: pd.DataFrame) -> None:
    """Simulate trade outcomes using stop loss and take profit levels.

    Args:
        df: Backtest DataFrame with Entry, Stop_Loss, Take_Profit and FWD_5D columns.
    """
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

    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0
    LOGGER.info(f"Win Rate : {win_rate:.1f}%")
    LOGGER.info(f"Wins     : {wins}")
    LOGGER.info(f"Losses   : {losses}")
    LOGGER.info(f"Open     : {still_open}")
    if losses > 0:
        LOGGER.info(f"W/L Ratio: {wins / losses:.2f}")


# ---------------- FULL ANALYSIS ----------------
def analyze(df: pd.DataFrame) -> pd.DataFrame:
    """Run full statistical analysis on backtest results.

    Args:
        df: Backtest results DataFrame.

    Returns:
        pd.DataFrame: Score bucket performance.
    """
    LOGGER.info("===== ANALYSIS =====")
    LOGGER.info("Total signals: %d", len(df))
    LOGGER.info(f"Score range  : {df['Score'].min()} – {df['Score'].max()}")
    LOGGER.info(f"Mean Score   : {df['Score'].mean():.1f}")
    LOGGER.info(f"Mean RSI     : {df['RSI'].mean():.1f}")
    LOGGER.info(f"Mean Change  : {df['Change'].apply(normalize_change).mean():.2f}%")

    analyze_with_levels(df)

    LOGGER.info("--- Score vs Forward Return Correlation ---")
    for d in FORWARD_DAYS:
        corr = df["Score"].corr(df[f"FWD_{d}D"])
        LOGGER.info(f"Score vs {d}D Return: {corr:.3f}")

    df["ScoreBucket"] = pd.qcut(df["Score"], 5, duplicates="drop")
    bucket_perf = df.groupby("ScoreBucket", observed=True)["FWD_5D"].mean()
    LOGGER.info("--- Score Bucket vs Avg 5D Return ---")
    LOGGER.info(bucket_perf)

    return bucket_perf


# ---------------- PLOTS ----------------
def plot_results(df: pd.DataFrame) -> None:
    """Generate scatter plot and equity curve charts.

    Args:
        df: Backtest results DataFrame.
    """
    # Score vs 5D return scatter
    plt.figure(figsize=(10, 5))
    plt.scatter(df["Score"], df["FWD_5D"], alpha=0.4, c=df["Score"], cmap="RdYlGn")
    plt.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    plt.xlabel("Score")
    plt.ylabel("5D Return (%)")
    plt.title("Score vs 5-Day Forward Returns")
    plt.colorbar(label="Score")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/scatter.png")
    plt.close()

    # Equity curve — top 10% scored signals
    df = df.copy()
    df["Rank"] = df["Score"].rank(pct=True)
    top = df[df["Rank"] > 0.9].copy()

    if top.empty:
        LOGGER.warning("No top-ranked signals for equity curve.")
        return

    equity = (1 + top["FWD_5D"] / 100).cumprod()
    final_return = (equity.iloc[-1] - 1) * 100

    plt.figure(figsize=(10, 5))
    plt.plot(equity.values, color="green" if final_return > 0 else "red")
    plt.axhline(1.0, color="gray", linestyle="--", linewidth=0.8)
    plt.title(f"Top Score Strategy Equity Curve (Final: {final_return:+.1f}%)")
    plt.xlabel("Trade #")
    plt.ylabel("Cumulative Return")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/equity.png")
    plt.close()


# ---------------- HTML REPORT ----------------
def generate_html(df: pd.DataFrame) -> None:
    """Generate HTML report with summary, charts and top signals.

    Args:
        df: Backtest results DataFrame.
    """
    top_signals = df.sort_values("Score", ascending=False).head(20)

    # Flag rows where score >= 60 and 5D return was positive
    top_signals = top_signals.copy()
    top_signals["Result"] = top_signals.apply(lambda r: "✅ WIN" if r["FWD_5D"] > 0 else "❌ LOSS", axis=1)

    html = f"""
<html>
<head>
    <title>Backtest Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 20px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
        table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
        th {{ background: #333; color: white; padding: 6px; }}
        td {{ padding: 5px; border: 1px solid #ddd; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
        tbody tr:nth-child(even) td {{ background: #f9f9f9; }}
        body.night tbody tr:nth-child(even) td {{ background: #2a2a2a; }}
    </style>
    <!-- CSS and JS for night mode -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/2.2.2/jquery.min.js"></script>
    <script type="text/javascript" src="https://thevickypedia.github.io/open-source/nightmode/night.js" defer></script>
    <link rel="stylesheet" type="text/css" href="https://thevickypedia.github.io/open-source/nightmode/night.css">
</head>
<body translate="no">
    <div class="toggler fa fa-moon-o"></div>
    <h1>Backtest Report</h1>

    <h2>Summary Statistics</h2>
    {df[["Score", "RSI", "Change", "FWD_1D", "FWD_3D", "FWD_5D"]].describe().round(3).to_html()}

    <h2>Charts</h2>
    <img src="scatter.png" width="700"/>
    <img src="equity.png" width="700"/>

    <h2>Top 20 Signals by Score</h2>
    {top_signals[["Ticker", "Score", "TD_Signal", "TD_Trend", "YF_Signal",
                    "EMA_Cross", "RSI", "Change", "ATR", "Volume",
                    "Entry", "Stop_Loss", "Take_Profit", "Risk_Reward",
                    "FWD_1D", "FWD_3D", "FWD_5D", "Result"]].to_html(index=True)}
</body>
</html>
    """

    path = f"{OUTPUT_DIR}/report.html"
    with open(path, "w") as f:
        f.write(html)
    LOGGER.info(f"Report saved to {path}")


# ---------------- Back Tester ----------------
def backtester(tickers: List[str], start_date: str = START_DATE, end_date: str = END_DATE) -> None:
    """Run full backtest pipeline: download, signal, analyze, plot, report."""
    df = run_backtest(tickers, start_date, end_date)

    if df.empty:
        LOGGER.warning("Backtest produced no results. Check tickers and date range.")
        return

    analyze(df)
    plot_results(df)
    generate_html(df)
