import os

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

from pytradingbot.main import get_candle_signal, score_stock

# ---------------- CONFIG ----------------
TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META"]
START_DATE = "2026-01-01"
END_DATE = "2026-03-10"
FORWARD_DAYS = [1, 3, 5]  # forward return windows
INITIAL_CAPITAL = 10000

OUTPUT_DIR = "backtest_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------- HELPERS ----------------
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI for a given price series.

    Args:
        series: Series to compute RSI for.
        period: Period to compute RSI for.

    Returns:
        pd.Series:
        Series with RSI value.
    """
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute indicators for a given dataframe."""
    df["RSI"] = compute_rsi(df["Close"])
    df["ATR"] = df["High"] - df["Low"]
    df["Change"] = df["Close"].pct_change() * 100
    df["Volume"] = df["Volume"]

    # EMA
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA21"] = df["Close"].ewm(span=21).mean()

    return df


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute signals for a given dataframe."""
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
            # Ensure numeric safety
            row["Volume"] = float(row.get("Volume", 0))
            row["RSI"] = float(row.get("RSI", 50))
            row["Change"] = float(row.get("Change", 0))
            row["Score"] = score_stock(row)
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
    """Runs backtest and returns final dataframe."""
    all_results = []
    for ticker in TICKERS:
        print(f"Processing {ticker}...")
        df = yf.download(ticker, start=START_DATE, end=END_DATE, progress=False)

        if df.empty:
            continue

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

        df["Open"] = pd.to_numeric(df["Open"], errors="coerce")
        df["High"] = pd.to_numeric(df["High"], errors="coerce")
        df["Low"] = pd.to_numeric(df["Low"], errors="coerce")
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")

        df = df.dropna()

        res = compute_signals(df)
        res["Ticker"] = ticker

        all_results.append(res)

    final_df = pd.concat(all_results).dropna()

    return final_df


# ---------------- ANALYSIS ----------------
def analyze(df: pd.DataFrame) -> pd.DataFrame:
    """Analyzes backtest and returns final dataframe."""
    print("\n===== ANALYSIS =====")

    # Correlation between score and returns
    for d in FORWARD_DAYS:
        corr = df["Score"].corr(df[f"FWD_{d}D"])
        print(f"Score vs {d}D Return Correlation: {corr:.3f}")

    # Bucket performance
    df["ScoreBucket"] = pd.qcut(df["Score"], 5, duplicates="drop")

    bucket_perf = df.groupby("ScoreBucket")["FWD_5D"].mean()
    print("\nScore Bucket vs 5D Return:")
    print(bucket_perf)

    return bucket_perf


# ---------------- PLOTS ----------------
def plot_results(df: pd.DataFrame) -> None:
    """Plots results of backtest and returns final dataframe."""
    plt.figure(figsize=(10, 5))
    plt.scatter(df["Score"], df["FWD_5D"], alpha=0.3)
    plt.xlabel("Score")
    plt.ylabel("5D Return (%)")
    plt.title("Score vs Forward Returns")
    plt.savefig(f"{OUTPUT_DIR}/scatter.png")
    plt.close()

    # Equity curve (top 10% scores)
    df["Rank"] = df["Score"].rank(pct=True)
    top = df[df["Rank"] > 0.9]

    equity = (1 + top["FWD_5D"] / 100).cumprod()

    plt.figure(figsize=(10, 5))
    plt.plot(equity)
    plt.title("Top Score Strategy Equity Curve")
    plt.savefig(f"{OUTPUT_DIR}/equity.png")
    plt.close()


# ---------------- HTML REPORT ----------------
def generate_html(df: pd.DataFrame) -> None:
    """Generates the HTML report."""
    html = f"""
    <html>
    <head>
        <title>Backtest Report</title>
    </head>
    <body>
        <h1>Backtest Report</h1>

        <h2>Summary</h2>
        {df.describe().to_html()}

        <h2>Charts</h2>
        <img src="scatter.png" width="600"/>
        <img src="equity.png" width="600"/>

        <h2>Top Signals</h2>
        {df.sort_values("Score", ascending=False).head(20).to_html()}

    </body>
    </html>
    """

    with open(f"{OUTPUT_DIR}/report.html", "w") as f:
        f.write(html)


# ---------------- MAIN ----------------
def main() -> None:
    """Runs backtest, analyzes and plot results, and generates report."""
    df = run_backtest()
    analyze(df)
    plot_results(df)
    generate_html(df)

    print(f"\nReport saved to {OUTPUT_DIR}/report.html")


if __name__ == "__main__":
    main()
