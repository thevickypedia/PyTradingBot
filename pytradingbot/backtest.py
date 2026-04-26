import os

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

from pytradingbot.main import (
    compute_trade_levels,
    get_candle_signal,
    normalize_change,
    score_stock,
)

# ---------------- CONFIG ----------------
TICKERS = ["NOWL", "NXXT", "CTNT"]
START_DATE = "2026-01-01"
END_DATE = "2026-04-24"
FORWARD_DAYS = [1, 3, 5]
INITIAL_CAPITAL = 10_000

OUTPUT_DIR = "backtest_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------- HELPERS ----------------
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI for a given price series.

    Args:
        series: Close price series.
        period: Lookback period (default 14).

    Returns:
        pd.Series: RSI values.
    """
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute RSI, ATR, Change and EMA indicators on a daily OHLCV DataFrame.

    Args:
        df: Raw OHLCV DataFrame.

    Returns:
        pd.DataFrame: DataFrame with indicator columns added.
    """
    df = df.copy()
    df["RSI"] = compute_rsi(df["Close"])
    df["ATR"] = df["High"] - df["Low"]
    df["Change"] = df["Close"].pct_change() * 100  # real % for backtest
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    return df


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Walk forward through the DataFrame generating signals and forward returns.

    For each row from index 25 onward, use the 5-candle window before it
    to generate candle signals, then score the row using real indicator values.

    Args:
        df: Indicator-enriched OHLCV DataFrame.

    Returns:
        pd.DataFrame: Rows with signals, scores, trade levels and forward returns.
    """
    results = []
    for i in range(25, len(df) - max(FORWARD_DAYS)):
        try:
            row = df.iloc[i].copy()
            window = df.iloc[i - 5 : i]  # noqa: E203

            if len(window) < 5:
                continue

            signal = get_candle_signal(df=window)
            row["TD_Signal"] = signal["TD_Signal"]
            row["TD_Trend"] = signal["TD_Trend"]
            row["YF_Signal"] = signal["YF_Signal"]
            row["EMA_Cross"] = signal["EMA_Cross"]
            row["Insider_Action"] = "N/A"

            # Pull real computed indicator values — these are already real %
            row["Volume"] = float(df.iloc[i]["Volume"])
            row["RSI"] = float(df.iloc[i]["RSI"])
            row["Change"] = float(df.iloc[i]["Change"])
            row["ATR"] = float(df.iloc[i]["ATR"])
            row["Price"] = float(df.iloc[i]["Close"])  # needed for trade levels + ATR%

            row["Score"] = score_stock(row)

            # Compute trade levels per row
            levels = compute_trade_levels(row)
            row["Entry"] = levels["Entry"]
            row["Stop_Loss"] = levels["Stop_Loss"]
            row["Take_Profit"] = levels["Take_Profit"]
            row["Risk_Reward"] = levels["Risk_Reward"]

            # Forward returns
            for d in FORWARD_DAYS:
                future_price = float(df.iloc[i + d]["Close"])
                current_price = float(row["Close"])
                row[f"FWD_{d}D"] = (future_price - current_price) / current_price * 100

            results.append(row)

        except Exception as e:
            print(f"Error at index {i}: {e}")
            continue

    return pd.DataFrame(results)


# ---------------- BACKTEST ----------------
def run_backtest() -> pd.DataFrame:
    """Download data, compute indicators and signals for all tickers.

    Returns:
        pd.DataFrame: Combined results across all tickers.
    """
    all_results = []
    for ticker in TICKERS:
        print(f"Processing {ticker}...")
        df = yf.download(ticker, start=START_DATE, end=END_DATE, progress=False)

        if df.empty:
            print(f"  No data for {ticker}, skipping.")
            continue

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df = df.apply(pd.to_numeric, errors="coerce").dropna()

        df = compute_indicators(df)
        df = df.dropna()  # drops NaN rows from rolling windows

        res = compute_signals(df)
        if res.empty:
            print(f"  No signals for {ticker}, skipping.")
            continue

        res["Ticker"] = ticker
        all_results.append(res)

    if not all_results:
        print("No results found across all tickers.")
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
    print(f"\nWin Rate : {win_rate:.1f}%")
    print(f"Wins     : {wins}")
    print(f"Losses   : {losses}")
    print(f"Open     : {still_open}")
    if losses > 0:
        print(f"W/L Ratio: {wins / losses:.2f}")


# ---------------- FULL ANALYSIS ----------------
def analyze(df: pd.DataFrame) -> pd.DataFrame:
    """Run full statistical analysis on backtest results.

    Args:
        df: Backtest results DataFrame.

    Returns:
        pd.DataFrame: Score bucket performance.
    """
    print("\n===== ANALYSIS =====")
    print(f"Total signals: {len(df)}")
    print(f"Score range  : {df['Score'].min()} – {df['Score'].max()}")
    print(f"Mean Score   : {df['Score'].mean():.1f}")
    print(f"Mean RSI     : {df['RSI'].mean():.1f}")
    print(f"Mean Change  : {df['Change'].apply(normalize_change).mean():.2f}%")

    analyze_with_levels(df)

    print("\n--- Score vs Forward Return Correlation ---")
    for d in FORWARD_DAYS:
        corr = df["Score"].corr(df[f"FWD_{d}D"])
        print(f"  Score vs {d}D Return: {corr:.3f}")

    df["ScoreBucket"] = pd.qcut(df["Score"], 5, duplicates="drop")
    bucket_perf = df.groupby("ScoreBucket", observed=True)["FWD_5D"].mean()
    print("\n--- Score Bucket vs Avg 5D Return ---")
    print(bucket_perf)

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
        print("No top-ranked signals for equity curve.")
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
        </style>
    </head>
    <body>
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
    print(f"Report saved to {path}")


# ---------------- MAIN ----------------
def main() -> None:
    """Run full backtest pipeline: download, signal, analyze, plot, report."""
    df = run_backtest()

    if df.empty:
        print("Backtest produced no results. Check tickers and date range.")
        return

    analyze(df)
    plot_results(df)
    generate_html(df)


if __name__ == "__main__":
    main()
