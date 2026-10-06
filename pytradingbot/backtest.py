import json
import math
import os
from datetime import datetime, timedelta
from multiprocessing.pool import ThreadPool
from typing import List

import matplotlib.pyplot as plt
import pandas as pd

from pytradingbot.constants import LOGGER
from pytradingbot.main import (
    _jinja_env,
    compute_atr,
    compute_trade_levels,
    get_candle_signal,
    normalize_change,
    score_stock,
)
from pytradingbot.resilience import fetch_ohlcv

# ---------------- CONFIG ----------------
TODAY = datetime.now()
FORWARD_DAYS = [1, 3, 5]
INITIAL_CAPITAL = 10_000
END_DATE = (TODAY - timedelta(days=5)).strftime("%Y-%m-%d")
START_DATE = TODAY.replace(year=TODAY.year - 3).strftime("%Y-%m-%d")

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
    df["ATR"] = compute_atr(df)  # Wilder's True Range ATR from main.py
    df["Change"] = df["Close"].pct_change() * 100
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Walk forward through the DataFrame generating signals and forward returns.

    For each row from index 50 onward, use a 30-candle window before it to
    generate candle signals (enough bars for EMA21 crossover to be meaningful).
    Rows failing price, volume, or macro-trend filters are skipped before
    scoring so only high-quality setups reach the report.

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

            # Pull real computed indicator values — Change is already real %
            row["Volume"] = volume
            row["RSI"] = float(df.iloc[idx]["RSI"])
            row["Change"] = float(df.iloc[idx]["Change"])
            row["ATR"] = float(df.iloc[idx]["ATR"])
            row["Price"] = price
            # Map EMA50/EMA200 into column names score_stock expects
            row["SMA20"] = ema50
            row["SMA50"] = ema200

            row["Date"] = df.index[idx].strftime("%Y-%m-%d")
            row["Score"] = score_stock(row)

            # Compute trade levels per row so win-rate analysis works
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
    """Download, indicator-enrich and signal-compute one ticker."""
    LOGGER.info("Processing %s", ticker)
    df = fetch_ohlcv(ticker, start=start, end=end)
    if df.empty:
        LOGGER.info("No data for %s, skipping.", ticker)
        return df

    df = compute_indicators(df)
    df = df.dropna()  # drop NaN rows from rolling windows

    res = compute_signals(df)
    if res.empty:
        LOGGER.warning("No signals for %s, skipping.", ticker)
    return res


# ---------------- BACKTEST ----------------
def run_backtest(tickers: List[str], start_date: str, end_date: str) -> pd.DataFrame:
    """Download data, compute indicators and signals for all tickers.

    Args:
        tickers: List of ticker symbols.
        start_date: Start date string (YYYY-MM-DD).
        end_date: End date string (YYYY-MM-DD).

    Returns:
        pd.DataFrame: Combined results across all tickers.
    """
    all_results = []
    processes = {
        ticker: ThreadPool(processes=1).apply_async(
            func=worker,
            args=(ticker, start_date, end_date),
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
    LOGGER.info("Win Rate : %.1f%%", win_rate)
    LOGGER.info("Wins     : %d", wins)
    LOGGER.info("Losses   : %d", losses)
    LOGGER.info("Open     : %d", still_open)
    if losses > 0:
        LOGGER.info("W/L Ratio: %.2f", wins / losses)


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
    LOGGER.info("Score range  : %s – %s", df["Score"].min(), df["Score"].max())
    LOGGER.info("Mean Score   : %.1f", df["Score"].mean())
    LOGGER.info("Mean RSI     : %.1f", df["RSI"].mean())
    LOGGER.info("Mean Change  : %.2f%%", df["Change"].apply(normalize_change).mean())

    analyze_with_levels(df)

    LOGGER.info("--- Score vs Forward Return Correlation ---")
    for d in FORWARD_DAYS:
        corr = df["Score"].corr(df[f"FWD_{d}D"])
        LOGGER.info("Score vs %dD Return: %.3f", d, corr)

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


# ---------------- HTML REPORT (Jinja2) ----------------
def _safe(v):
    """Convert a value to a JSON-safe scalar (NaN/Inf → None, numpy scalars → Python)."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, float):
        return round(v, 4)
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return None
    if hasattr(v, "item"):  # numpy scalar
        return v.item()
    return v


def generate_html(df: pd.DataFrame) -> None:
    """Render the Bootstrap backtest_report.html template via Jinja2 and write to disk.

    Replaces the placeholder JS constants (SUMMARY_STATS, BUCKET_DATA, BT_DATA)
    with live Python data by injecting them as Jinja2 variables.

    Args:
        df: Backtest results DataFrame (output of run_backtest).
    """
    # ── SUMMARY_STATS ──────────────────────────────────────────────────────
    stat_cols = ["Score", "RSI", "ATR", "Change", "FWD_1D", "FWD_3D", "FWD_5D"]
    available_stat_cols = [c for c in stat_cols if c in df.columns]
    summary_stats = df[available_stat_cols].describe().round(3).to_dict()
    # Flip to { stat_name: { ColA: val, … } } format expected by the template
    summary_stats_flipped: dict = {}
    for col, stat_dict in summary_stats.items():
        for stat, val in stat_dict.items():
            summary_stats_flipped.setdefault(stat, {})[col] = _safe(val)

    # ── BUCKET_DATA ────────────────────────────────────────────────────────
    bucket_data = []
    try:
        df_tmp = df.copy()
        df_tmp["ScoreBucket"] = pd.qcut(df_tmp["Score"], 5, duplicates="drop")
        for bucket, avg in df_tmp.groupby("ScoreBucket", observed=True)["FWD_5D"].mean().items():
            label = f"{bucket.left:.1f} to {bucket.right:.1f}" if hasattr(bucket, "left") else str(bucket)
            bucket_data.append({"range": label, "avg5d": _safe(avg)})
    except Exception as err:
        LOGGER.warning("Bucket data generation failed: %s", err)

    # ── BT_DATA (top 50 by score) ──────────────────────────────────────────
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
    available_cols = [c for c in wanted_cols if c in df.columns]
    bt_data = []
    for _, row in df.sort_values("Score", ascending=False).head(50)[available_cols].iterrows():
        d = {c: _safe(row[c]) for c in available_cols}
        fwd5 = d.get("FWD_5D")
        d["Result"] = "WIN" if (fwd5 is not None and fwd5 > 0) else "LOSS"
        bt_data.append(d)

    # ── KPI stats for header cards ─────────────────────────────────────────
    wins = sum(
        1
        for _, r in df.iterrows()
        if r.get("Entry")
        and r.get("Stop_Loss")
        and r.get("Take_Profit")
        and float(r.get("Entry", 0)) * (1 + float(r.get("FWD_5D", 0)) / 100) >= float(r.get("Take_Profit", 0))
    )
    losses = sum(
        1
        for _, r in df.iterrows()
        if r.get("Entry")
        and r.get("Stop_Loss")
        and r.get("Take_Profit")
        and float(r.get("Entry", 0)) * (1 + float(r.get("FWD_5D", 0)) / 100) <= float(r.get("Stop_Loss", 0))
    )
    total_traded = wins + losses
    win_rate = round(wins / total_traded * 100, 1) if total_traded > 0 else 0.0

    kpi = {
        "total_signals": len(df),
        "win_rate": win_rate,
        "wins": wins,
        "losses": losses,
        "avg_fwd5d": round(float(df["FWD_5D"].mean()), 2) if "FWD_5D" in df.columns else 0,
        "avg_score": round(float(df["Score"].mean()), 1),
        "max_score": int(df["Score"].max()),
        "avg_rsi": round(float(df["RSI"].mean()), 1) if "RSI" in df.columns else 0,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # ── Render ──────────────────────────────────────────────────────────────
    template = _jinja_env.get_template("backtest_report.html")
    html = template.render(
        SUMMARY_STATS=json.dumps(summary_stats_flipped),
        BUCKET_DATA=json.dumps(bucket_data),
        BT_DATA=json.dumps(bt_data),
        kpi=kpi,
    )

    path = f"{OUTPUT_DIR}/report.html"
    with open(path, "w") as fh:
        fh.write(html)
    LOGGER.info("Backtest report saved to %s", path)


# ---------------- Back Tester ----------------
def backtester(tickers: List[str], start_date: str = START_DATE, end_date: str = END_DATE) -> None:
    """Run full backtest pipeline: download, signal, analyze, plot, report.

    Args:
        tickers: List of ticker symbols.
        start_date: Start date string (YYYY-MM-DD).
        end_date: End date string (YYYY-MM-DD).
    """
    df = run_backtest(tickers, start_date, end_date)

    if df.empty:
        LOGGER.warning("Backtest produced no results. Check tickers and date range.")
        return

    analyze(df)
    plot_results(df)
    generate_html(df)
